"""
Tests for ReliefOS Phase 2B — Server-Side Proactive Intelligence Runtime

Validates:
1. ProactiveScan and ProactiveFinding models & deterministic fingerprints.
2. Repository persistence (InMemory & PostgreSQL).
3. Deterministic detector execution (Exposure, Access, Medical, Logistics, Coordination, Field).
4. Selective detector and specialist domain filtering.
5. Finding lifecycle state transitions (NEW -> ACTIVE -> RESOLVED -> NEW).
6. Alert deduplication and material severity escalation.
7. Human-in-the-loop safeguard: zero autonomous domain mutations during proactive scans.
8. Privacy boundary: Network proactive scans never touch NGO private operational state.
9. Proactive scheduler background thread lifecycle.
10. REST API endpoints for scans, findings, triggers, and scheduler controls.
"""

import os
import time
import uuid
import pytest
from datetime import datetime, timezone, timedelta

from agent.proactive.models import (
    ProactiveScan,
    ProactiveFinding,
    ScanStatus,
    FindingLifecycleStatus,
    generate_finding_fingerprint,
)
from agent.proactive.detectors import (
    ExposureRiskDetector,
    AccessRiskDetector,
    MedicalGapDetector,
    LogisticsGapDetector,
    CoordinationGapDetector,
    FieldConflictDetector,
    select_relevant_detectors,
    list_detectors,
)
from agent.proactive.detectors.base import ProactiveContext
from agent.proactive.runtime import ProactiveRuntime
from agent.proactive.scheduler import ProactiveScheduler
from agent.data.repository import InMemoryRepository
from agent.data.models import (
    District,
    Settlement,
    FloodSnapshot,
    Need,
    ResourceOffer,
    Operation,
    FieldReport,
    Override,
)


# ---------------------------------------------------------------------------
# 1. Models & Fingerprints
# ---------------------------------------------------------------------------

def test_proactive_models_and_fingerprint_generation():
    fp1 = generate_finding_fingerprint("exposure", "exposure_risk", "settlement", "set_1", "Inundation Risk")
    fp2 = generate_finding_fingerprint("exposure", "exposure_risk", "settlement", "set_1", "Inundation Risk")
    fp3 = generate_finding_fingerprint("exposure", "exposure_risk", "settlement", "set_2", "Inundation Risk")

    assert fp1 == fp2
    assert fp1 != fp3
    assert len(fp1) == 24

    finding = ProactiveFinding(
        domain="medical",
        detector_id="medical_gap",
        entity_type="need",
        entity_id="need_99",
        title="Unassigned Medical Emergency",
        summary="Urgent medical supplies required",
        severity="critical",
        evidence={"urgency": "critical"},
    )
    assert finding.fingerprint != ""
    assert finding.status == FindingLifecycleStatus.NEW.value

    data = finding.to_dict()
    reconstructed = ProactiveFinding.from_dict(data)
    assert reconstructed.id == finding.id
    assert reconstructed.fingerprint == finding.fingerprint
    assert reconstructed.severity == "critical"
    assert reconstructed.status == FindingLifecycleStatus.NEW.value

    scan = ProactiveScan(
        trigger="manual_api",
        detectors_run=["exposure_risk", "medical_gap"],
        findings_count=3,
    )
    scan_dict = scan.to_dict()
    scan_recon = ProactiveScan.from_dict(scan_dict)
    assert scan_recon.id == scan.id
    assert scan_recon.trigger == "manual_api"
    assert scan_recon.findings_count == 3


# ---------------------------------------------------------------------------
# 2. InMemory Repository Proactive CRUD
# ---------------------------------------------------------------------------

def test_in_memory_repository_proactive_crud():
    repo = InMemoryRepository()

    scan = ProactiveScan(trigger="scheduled", status=ScanStatus.RUNNING.value)
    repo.create_proactive_scan(scan)
    assert repo.get_proactive_scan(scan.id) is not None

    repo.update_proactive_scan(
        scan.id,
        status=ScanStatus.SUCCESS.value,
        findings_count=5,
        summary="Scan finished successfully",
    )
    updated_scan = repo.get_proactive_scan(scan.id)
    assert updated_scan.status == ScanStatus.SUCCESS.value
    assert updated_scan.findings_count == 5

    finding = ProactiveFinding(
        scan_id=scan.id,
        domain="access",
        detector_id="access_risk",
        title="Road Blocked",
        summary="Bridge washed out",
        severity="high",
    )
    repo.upsert_proactive_finding(finding)

    assert repo.get_proactive_finding(finding.id) is not None
    assert repo.get_proactive_finding_by_fingerprint(finding.fingerprint) is not None

    findings_list = repo.list_proactive_findings(domain="access")
    assert len(findings_list) == 1
    assert findings_list[0].id == finding.id


# ---------------------------------------------------------------------------
# 3. PostgreSQL Repository Persistence
# ---------------------------------------------------------------------------

def test_postgres_repository_proactive_crud():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url or os.environ.get("RELIEFOS_MEMORY") in ("1", "true"):
        pytest.skip("PostgreSQL test skipped when in memory-only mode")

    from agent.data.postgres_repository import PostgresRepository
    repo = PostgresRepository(database_url=db_url)

    scan_id = f"scan_test_{str(uuid.uuid4())[:8]}"
    scan = ProactiveScan(id=scan_id, trigger="manual_api", status=ScanStatus.RUNNING.value)
    repo.create_proactive_scan(scan)

    fetched = repo.get_proactive_scan(scan_id)
    assert fetched is not None
    assert fetched.id == scan_id

    uid = str(uuid.uuid4())[:8]
    finding_id = f"fnd_test_{uid}"
    finding = ProactiveFinding(
        id=finding_id,
        scan_id=scan_id,
        domain="exposure",
        detector_id="exposure_risk",
        entity_id=f"set_{uid}",
        title=f"Postgres Inundation Risk {uid}",
        summary="Test settlement flooded",
        severity="urgent",
    )
    saved = repo.upsert_proactive_finding(finding)

    # Re-fetch from fresh repo instance
    repo2 = PostgresRepository(database_url=db_url)
    fetched_finding = repo2.get_proactive_finding(saved.id)
    assert fetched_finding is not None
    assert fetched_finding.id == saved.id
    assert fetched_finding.title == f"Postgres Inundation Risk {uid}"
    assert fetched_finding.severity == "urgent"


# ---------------------------------------------------------------------------
# 4. Individual Detector Execution
# ---------------------------------------------------------------------------

def test_proactive_detectors_execution():
    repo = InMemoryRepository()

    # Seed operational data
    d = District(id="sivasagar", name="Sivasagar")
    repo.upsert_district(d)

    snap = FloodSnapshot(
        id="snap_1",
        district_id="sivasagar",
        observed_at=datetime.now(timezone.utc),
        source="satellite",
        polygon_count=12,
        metadata={"flood_area_sqkm": 75.5},
    )
    repo.upsert_flood_snapshot(snap)

    settlement = Settlement(
        id="set_1",
        district_id="sivasagar",
        name="Nazira Town",
        lat=26.91,
        lon=94.73,
        metadata={"in_flood_zone": True, "population": 12000},
    )
    repo.upsert_settlement(settlement)

    need = Need(
        id="need_med_1",
        district_id="sivasagar",
        title="Emergency Insulin",
        need_type="medical",
        urgency="critical",
        status="OPEN",
        lat=26.91,
        lon=94.73,
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    repo.create_need(need)

    override = Override(
        id="ovr_1",
        target_type="road",
        target_id="NH-715",
        override_status="blocked",
        reason="Waterlogging 3 feet deep",
        active=True,
    )
    repo.upsert_override(override)

    report = FieldReport(
        id="rep_1",
        district_id="sivasagar",
        people_count=25,
        needs=["rescue", "first_aid"],
        location_description="Near Nazira Railway Station",
        verification_state="UNVERIFIED",
    )
    repo.upsert_field_report(report)

    context = ProactiveContext(repo=repo, now=datetime.now(timezone.utc))

    # Test ExposureRiskDetector
    exp_detector = ExposureRiskDetector()
    exp_findings = exp_detector.detect(context)
    assert len(exp_findings) >= 1
    assert any(f.entity_id == "set_1" for f in exp_findings)
    assert all(f.domain == "exposure" for f in exp_findings)

    # Test MedicalGapDetector
    med_detector = MedicalGapDetector()
    med_findings = med_detector.detect(context)
    assert len(med_findings) >= 1
    assert any(f.entity_id == "need_med_1" for f in med_findings)
    assert med_findings[0].severity in ("critical", "high")

    # Test AccessRiskDetector
    access_detector = AccessRiskDetector()
    access_findings = access_detector.detect(context)
    assert len(access_findings) >= 1
    assert any("NH-715" in f.title for f in access_findings)

    # Test CoordinationGapDetector
    coord_detector = CoordinationGapDetector()
    coord_findings = coord_detector.detect(context)
    assert len(coord_findings) >= 1
    assert any(f.entity_id == "need_med_1" for f in coord_findings)

    # Test FieldConflictDetector
    field_detector = FieldConflictDetector()
    field_findings = field_detector.detect(context)
    assert len(field_findings) >= 1
    assert any(f.entity_id == "rep_1" for f in field_findings)


# ---------------------------------------------------------------------------
# 5. Selective Detector and Domain Filtering
# ---------------------------------------------------------------------------

def test_selective_detector_and_specialist_resolution():
    repo = InMemoryRepository()

    # Scope: domain="exposure"
    context_exp = ProactiveContext(repo=repo, scope={"domain": "exposure"})
    detectors = select_relevant_detectors(context_exp)
    assert len(detectors) == 1
    assert detectors[0].detector_id == "exposure_risk"

    # Scope: specific detector IDs
    context_specific = ProactiveContext(repo=repo, scope={"detector_ids": ["medical_gap", "logistics_gap"]})
    detectors_spec = select_relevant_detectors(context_specific)
    assert len(detectors_spec) == 2
    assert {d.detector_id for d in detectors_spec} == {"medical_gap", "logistics_gap"}


# ---------------------------------------------------------------------------
# 6. Finding Lifecycle Transitions (NEW -> ACTIVE -> RESOLVED -> NEW)
# ---------------------------------------------------------------------------

def test_finding_lifecycle_state_transitions():
    repo = InMemoryRepository()
    runtime = ProactiveRuntime(repo=repo)

    d = District(id="jorhat", name="Jorhat")
    repo.upsert_district(d)

    need = Need(
        id="need_life_1",
        district_id="jorhat",
        title="Rescue Boats Required",
        need_type="rescue",
        urgency="critical",
        status="OPEN",
        created_at=datetime.now(timezone.utc) - timedelta(hours=3),
    )
    repo.create_need(need)

    # --- SCAN 1: First time detection -> Status: NEW ---
    scan1 = runtime.run_once(scope={"domain": "coordination"}, repo=repo)
    assert scan1.status == ScanStatus.SUCCESS.value
    assert scan1.findings_count >= 1

    findings1 = repo.list_proactive_findings(domain="coordination")
    assert len(findings1) >= 1
    target = findings1[0]
    assert target.status == FindingLifecycleStatus.NEW.value
    fingerprint = target.fingerprint

    # --- SCAN 2: Second run while condition persists -> Status: ACTIVE ---
    scan2 = runtime.run_once(scope={"domain": "coordination"}, repo=repo)
    target_active = repo.get_proactive_finding_by_fingerprint(fingerprint)
    assert target_active is not None
    assert target_active.status == FindingLifecycleStatus.ACTIVE.value
    assert target_active.last_detected_at >= target.first_detected_at

    # --- MUTATION: Need is fulfilled / closed ---
    need.status = "FULFILLED"
    repo.update_need(need)

    # --- SCAN 3: Condition resolved -> Status: RESOLVED ---
    scan3 = runtime.run_once(scope={"domain": "coordination"}, repo=repo)
    target_resolved = repo.get_proactive_finding_by_fingerprint(fingerprint)
    assert target_resolved is not None
    assert target_resolved.status == FindingLifecycleStatus.RESOLVED.value
    assert target_resolved.resolved_at is not None

    # --- MUTATION: Need reopens ---
    need.status = "OPEN"
    need.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    repo.update_need(need)

    # --- SCAN 4: Condition reappears -> Status transitions back to NEW ---
    scan4 = runtime.run_once(scope={"domain": "coordination"}, repo=repo)
    target_reopened = repo.get_proactive_finding_by_fingerprint(fingerprint)
    assert target_reopened is not None
    assert target_reopened.status == FindingLifecycleStatus.NEW.value
    assert target_reopened.resolved_at is None


# ---------------------------------------------------------------------------
# 7. Notification Deduplication & Severity Escalation
# ---------------------------------------------------------------------------

def test_notification_deduplication_and_severity_escalation():
    repo = InMemoryRepository()
    runtime = ProactiveRuntime(repo=repo)

    d = District(id="golaghat", name="Golaghat")
    repo.upsert_district(d)

    need = Need(
        id="need_escalate_1",
        district_id="golaghat",
        title="Water Purification Tablets",
        need_type="logistics",
        urgency="medium",
        requested_resources=[{"resource_type": "logistics", "quantity": 20}],
        status="OPEN",
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    repo.create_need(need)

    # SCAN 1: Medium finding -> Logistics deficit
    scan1 = runtime.run_once(scope={"domain": "logistics"}, repo=repo)
    notifs1 = repo.list_notifications(recipient_id="all")
    initial_notifs_count = len(notifs1)

    # SCAN 2: Same unchanged finding -> Zero new notifications emitted
    scan2 = runtime.run_once(scope={"domain": "logistics"}, repo=repo)
    notifs2 = repo.list_notifications(recipient_id="all")
    assert len(notifs2) == initial_notifs_count

    # ESCALATION: Urgency jumps to critical
    need.urgency = "critical"
    need.requested_resources = [{"resource_type": "logistics", "quantity": 100}]
    repo.update_need(need)

    # SCAN 3: Severity escalated to critical -> Emits new notification & logs severity history
    scan3 = runtime.run_once(scope={"domain": "logistics"}, repo=repo)
    notifs3 = repo.list_notifications(recipient_id="all")
    assert len(notifs3) > initial_notifs_count

    findings = repo.list_proactive_findings(domain="logistics")
    assert len(findings) >= 1
    assert len(findings[0].severity_history) >= 1


# ---------------------------------------------------------------------------
# 8. Human-In-The-Loop Safeguard: Zero Domain Mutations
# ---------------------------------------------------------------------------

def test_hitl_safeguard_zero_domain_writes_during_proactive_scan():
    repo = InMemoryRepository()
    runtime = ProactiveRuntime(repo=repo)

    d = District(id="charaideo", name="Charaideo")
    repo.upsert_district(d)

    need = Need(
        id="need_safe_1",
        district_id="charaideo",
        title="Blankets and Shelter Kits",
        need_type="shelter",
        urgency="high",
        status="OPEN",
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    repo.create_need(need)

    # Snapshot domain tables before scan
    needs_before = [n.to_dict() for n in repo.list_needs()]
    offers_before = [o.to_dict() for o in repo.list_resource_offers()]
    ops_before = [op.to_dict() for op in repo.list_operations()]

    # Execute full scan across all detectors
    scan = runtime.run_once(repo=repo)
    assert scan.status == ScanStatus.SUCCESS.value

    # Snapshot domain tables after scan
    needs_after = [n.to_dict() for n in repo.list_needs()]
    offers_after = [o.to_dict() for o in repo.list_resource_offers()]
    ops_after = [op.to_dict() for op in repo.list_operations()]

    # Assert zero domain mutations
    assert needs_before == needs_after
    assert offers_before == offers_after
    assert ops_before == ops_after


# ---------------------------------------------------------------------------
# 9. Privacy Boundary: Network Proactive Scans Never Access Private NGO State
# ---------------------------------------------------------------------------

def test_privacy_boundary_network_proactive_no_ngo_private_access():
    from agent.agents.network_main_agent import NetworkMainAgent

    net_agent = NetworkMainAgent()
    assert "shared_state" in net_agent.allowed_context
    assert "ngo_private" not in net_agent.allowed_context

    # Ensure detector context only contains shared repository
    repo = InMemoryRepository()
    context = ProactiveContext(repo=repo)
    assert not hasattr(context, "ngo_private_workspace")
    assert not hasattr(context, "org_session")


# ---------------------------------------------------------------------------
# 10. Proactive Scheduler Lifecycle
# ---------------------------------------------------------------------------

def test_proactive_scheduler_lifecycle():
    repo = InMemoryRepository()
    runtime = ProactiveRuntime(repo=repo)
    scheduler = ProactiveScheduler(runtime=runtime)

    assert not scheduler.is_running
    status_init = scheduler.get_status()
    assert status_init["is_running"] is False
    assert status_init["total_runs"] == 0

    # Trigger synchronous run via scheduler
    scan = scheduler.trigger_now()
    assert scan is not None
    assert scheduler.get_status()["total_runs"] == 1

    # Start background scheduler with short interval
    scheduler.start(interval_seconds=10.0)
    assert scheduler.is_running
    assert scheduler.get_status()["is_running"] is True

    # Stop scheduler
    scheduler.stop(timeout=2.0)
    assert not scheduler.is_running


# ---------------------------------------------------------------------------
# 11. REST API Proactive Endpoints
# ---------------------------------------------------------------------------

def test_api_proactive_endpoints():
    from agent.api import app
    client = app.test_client()

    # 1. GET status
    resp = client.get("/api/agent/proactive/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "scheduler" in data
    assert "registered_detectors" in data
    assert len(data["registered_detectors"]) >= 6

    # 2. POST trigger
    resp = client.post("/api/agent/proactive/trigger", json={"scope": {"domain": "exposure"}})
    assert resp.status_code == 200
    trigger_data = resp.get_json()
    assert "scan" in trigger_data
    scan_id = trigger_data["scan"]["id"]

    # 3. GET scan by ID
    resp = client.get(f"/api/agent/proactive/scans/{scan_id}")
    assert resp.status_code == 200
    scan_data = resp.get_json()
    assert scan_data["scan"]["id"] == scan_id

    # 4. GET list scans
    resp = client.get("/api/agent/proactive/scans?limit=10")
    assert resp.status_code == 200
    scans_list = resp.get_json()
    assert "scans" in scans_list
    assert len(scans_list["scans"]) >= 1

    # 5. GET list findings
    resp = client.get("/api/agent/proactive/findings?limit=10")
    assert resp.status_code == 200
    findings_list = resp.get_json()
    assert "findings" in findings_list
