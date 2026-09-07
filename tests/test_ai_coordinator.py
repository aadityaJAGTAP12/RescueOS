"""
Tests for AI Coordinator — Phase 7B v1 Read-Only Operational Findings

Tests cover:
- Coordination gap detection
- Duplicate response detection
- Consequence alert detection
- No finding when conditions are absent
- Severity calculation
- Evidence generation
- Uncertainty/data-gap handling
- No writes
- No district hardcoding
"""

# Repository selection: fresh_repo below explicitly sets an
# InMemoryRepository per test (coordinator analysis is an in-memory unit
# test). No RELIEFOS_MEMORY env forcing — the import-time override poisoned
# the whole pytest process and silently downgraded DATABASE_URL runs to
# memory mode (Item 5B finding).

import pytest
from datetime import datetime, timezone, timedelta

from agent.data.models import (
    Organization, Need, ResourceOffer, Operation, ActivityEvent, Road,
    Provenance,
)
from agent.data.repository import get_repository, reset_repository
from agent.ai_coordinator import (
    detect_coordination_gaps,
    detect_duplicate_responses,
    detect_consequence_alerts,
    run_coordinator_analysis,
    _severity_from_urgency,
    _format_age,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_repo():
    """Provide a fresh InMemoryRepository for each test.

    Explicitly selected (not env-forced) so the repository identity is
    provable regardless of the ambient DATABASE_URL (Item 5B).
    """
    reset_repository()
    from agent.data.repository import InMemoryRepository, set_repository
    repo = InMemoryRepository()
    set_repository(repo)
    yield repo
    reset_repository()


@pytest.fixture
def sample_org_a():
    return Organization(
        id="org_a",
        name="Relief Organization A",
        organization_type="ngo",
        published_capabilities=["medical", "transport"],
    )


@pytest.fixture
def sample_org_b():
    return Organization(
        id="org_b",
        name="Relief Organization B",
        organization_type="ngo",
        published_capabilities=["food", "shelter"],
    )


# ---------------------------------------------------------------------------
# 1. Coordination Gap Detection
# ---------------------------------------------------------------------------

class TestCoordinationGapDetection:
    def test_detects_old_open_need_with_no_response(self, fresh_repo):
        """An OPEN need older than threshold with no offers/ops → gap."""
        need = Need(
            id="need_1",
            need_type="water",
            title="Water shortage",
            district_id="district_a",
            location_name="Town A",
            urgency="high",
            status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        fresh_repo.create_need(need)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        assert len(findings) == 1
        assert findings[0]["type"] == "coordination_gap"
        assert findings[0]["severity"] == "high"
        assert findings[0]["evidence"]["need_id"] == "need_1"
        assert findings[0]["evidence"]["need_age_hours"] >= 5.0
        assert findings[0]["evidence"]["offers"] == 0
        assert findings[0]["evidence"]["operations"] == 0

    def test_no_finding_when_need_is_young(self, fresh_repo):
        """A need created recently (below threshold) → no gap."""
        need = Need(
            id="need_2",
            need_type="food",
            title="Food needed",
            district_id="district_a",
            status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        fresh_repo.create_need(need)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        assert len(findings) == 0

    def test_no_finding_when_need_has_offer(self, fresh_repo):
        """An old need with an active offer → no gap."""
        org = Organization(id="org1", name="Org 1")
        fresh_repo.create_organization(org)

        need = Need(
            id="need_3",
            need_type="medical",
            title="Medical need",
            district_id="district_a",
            status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        fresh_repo.create_need(need)

        offer = ResourceOffer(
            id="offer_1",
            organization_id="org1",
            resource_type="medical_team",
            quantity=1,
            district_id="district_a",
            status="OFFERED",
        )
        fresh_repo.create_resource_offer(offer)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        assert len(findings) == 0

    def test_no_finding_when_need_has_operation(self, fresh_repo):
        """An old need with an active operation → no gap."""
        org = Organization(id="org1", name="Org 1")
        fresh_repo.create_organization(org)

        need = Need(
            id="need_4",
            need_type="rescue",
            title="Rescue needed",
            district_id="district_a",
            status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=4),
        )
        fresh_repo.create_need(need)

        op = Operation(
            id="op_1",
            name="Rescue Op",
            need_id="need_4",
            lead_organization_id="org1",
            district_id="district_a",
            status="ACTIVE",
        )
        fresh_repo.create_operation(op)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        assert len(findings) == 0

    def test_no_finding_for_non_open_needs(self, fresh_repo):
        """Resolved/closed needs should not trigger gaps."""
        need = Need(
            id="need_5",
            need_type="food",
            title="Old resolved need",
            district_id="district_a",
            status="RESOLVED",
            created_at=datetime.now(timezone.utc) - timedelta(hours=10),
        )
        fresh_repo.create_need(need)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# 2. Duplicate Response Detection
# ---------------------------------------------------------------------------

class TestDuplicateResponseDetection:
    def test_detects_multiple_operations_on_same_need(self, fresh_repo, sample_org_a, sample_org_b):
        """Two operations on the same need → duplicate."""
        fresh_repo.create_organization(sample_org_a)
        fresh_repo.create_organization(sample_org_b)

        need = Need(
            id="need_dup",
            need_type="food",
            title="Food shortage",
            district_id="district_a",
            status="OPEN",
        )
        fresh_repo.create_need(need)

        op1 = Operation(
            id="op_1", name="Op A", need_id="need_dup",
            lead_organization_id="org_a", district_id="district_a",
            status="ACTIVE",
        )
        op2 = Operation(
            id="op_2", name="Op B", need_id="need_dup",
            lead_organization_id="org_b", district_id="district_a",
            status="PLANNING",
        )
        fresh_repo.create_operation(op1)
        fresh_repo.create_operation(op2)

        findings = detect_duplicate_responses(fresh_repo)
        assert len(findings) >= 1
        dup_findings = [f for f in findings if f["type"] == "duplicate_response"]
        assert len(dup_findings) == 1
        assert "op_1" in dup_findings[0]["evidence"]["operation_ids"]
        assert "op_2" in dup_findings[0]["evidence"]["operation_ids"]
        assert len(dup_findings[0]["evidence"]["organizations"]) == 2

    def test_no_finding_with_single_operation(self, fresh_repo, sample_org_a):
        """One operation per need → no duplicate."""
        fresh_repo.create_organization(sample_org_a)

        need = Need(
            id="need_single", need_type="water", title="Water",
            district_id="district_a", status="OPEN",
        )
        fresh_repo.create_need(need)

        op = Operation(
            id="op_1", name="Op", need_id="need_single",
            lead_organization_id="org_a", district_id="district_a",
            status="ACTIVE",
        )
        fresh_repo.create_operation(op)

        findings = detect_duplicate_responses(fresh_repo)
        dup_findings = [f for f in findings if f["type"] == "duplicate_response"]
        assert len(dup_findings) == 0

    def test_detects_multiple_organizations_with_accepted_offers(self, fresh_repo, sample_org_a, sample_org_b):
        """Two orgs with accepted offers for same resource type + district + need → dup."""
        fresh_repo.create_organization(sample_org_a)
        fresh_repo.create_organization(sample_org_b)

        need = Need(
            id="need_offers", need_type="food", title="Food",
            district_id="district_a", status="OPEN",
        )
        fresh_repo.create_need(need)

        offer1 = ResourceOffer(
            id="offer_a", organization_id="org_a", resource_type="food",
            quantity=100, unit="kg", district_id="district_a", status="ACCEPTED",
        )
        offer2 = ResourceOffer(
            id="offer_b", organization_id="org_b", resource_type="food",
            quantity=200, unit="kg", district_id="district_a", status="ACCEPTED",
        )
        fresh_repo.create_resource_offer(offer1)
        fresh_repo.create_resource_offer(offer2)

        findings = detect_duplicate_responses(fresh_repo)
        dup_findings = [f for f in findings if f["type"] == "duplicate_response"]
        assert len(dup_findings) >= 1

    def test_no_finding_with_different_resource_types(self, fresh_repo, sample_org_a, sample_org_b):
        """Two orgs offering different resource types → no duplicate."""
        fresh_repo.create_organization(sample_org_a)
        fresh_repo.create_organization(sample_org_b)

        need = Need(
            id="need_diff", need_type="food", title="Food",
            district_id="district_a", status="OPEN",
        )
        fresh_repo.create_need(need)

        offer1 = ResourceOffer(
            id="offer_a", organization_id="org_a", resource_type="food",
            quantity=100, unit="kg", district_id="district_a", status="ACCEPTED",
        )
        offer2 = ResourceOffer(
            id="offer_b", organization_id="org_b", resource_type="water",
            quantity=50, unit="liters", district_id="district_a", status="ACCEPTED",
        )
        fresh_repo.create_resource_offer(offer1)
        fresh_repo.create_resource_offer(offer2)

        findings = detect_duplicate_responses(fresh_repo)
        # Should not flag as duplicate since resource types differ
        dup_findings_for_food = [
            f for f in findings
            if f["type"] == "duplicate_response"
            and f["evidence"].get("resource_type") == "food"
        ]
        assert len(dup_findings_for_food) == 0


# ---------------------------------------------------------------------------
# 3. Consequence Alert Detection
# ---------------------------------------------------------------------------

class TestConsequenceAlertDetection:
    def test_detects_blocked_road_in_operation_district(self, fresh_repo, sample_org_a):
        """Blocked road override in same district as active operation → alert."""
        fresh_repo.create_organization(sample_org_a)

        # Add a road to the repository
        road = Road(
            id="road_1",
            district_id="district_a",
            name="Main Bridge Road",
            highway_type="primary",
            is_bridge=True,
            geometry_coords=[[94.0, 26.0], [94.1, 26.1]],
        )
        fresh_repo.upsert_roads([road])

        op = Operation(
            id="op_active", name="Active Rescue",
            lead_organization_id="org_a", district_id="district_a",
            lat=26.05, lon=94.05, location_name="Town A",
            status="ACTIVE",
        )
        fresh_repo.create_operation(op)

        # Apply a road override via the overrides module
        from agent.overrides import apply_override
        apply_override(
            target_type="road",
            target_id="Main Bridge Road",
            new_status="blocked",
            reason="Bridge collapsed",
            actor="field_coordinator",
        )

        findings = detect_consequence_alerts(fresh_repo)
        # Should find at least one consequence alert
        alert_findings = [f for f in findings if f["type"] == "consequence_alert"]
        assert len(alert_findings) >= 1
        assert alert_findings[0]["severity"] == "critical"
        assert alert_findings[0]["evidence"]["blocked_road"] == "Main Bridge Road"
        assert alert_findings[0]["evidence"]["route_valid"] is False

    def test_no_finding_when_no_blocked_roads(self, fresh_repo, sample_org_a):
        """No blocked road overrides → no consequence alert."""
        fresh_repo.create_organization(sample_org_a)

        op = Operation(
            id="op_safe", name="Safe Operation",
            lead_organization_id="org_a", district_id="district_a",
            lat=26.05, lon=94.05, status="ACTIVE",
        )
        fresh_repo.create_operation(op)

        findings = detect_consequence_alerts(fresh_repo)
        alert_findings = [f for f in findings if f["type"] == "consequence_alert"]
        assert len(alert_findings) == 0

    def test_no_finding_when_operation_has_no_coordinates(self, fresh_repo, sample_org_a):
        """Operation without lat/lon → skip (can't assess route)."""
        fresh_repo.create_organization(sample_org_a)

        road = Road(
            id="road_2", district_id="district_a",
            name="Blocked Road", highway_type="secondary",
            geometry_coords=[[94.0, 26.0], [94.1, 26.1]],
        )
        fresh_repo.upsert_roads([road])

        op = Operation(
            id="op_noloc", name="No Location Op",
            lead_organization_id="org_a", district_id="district_a",
            status="ACTIVE",
        )
        fresh_repo.create_operation(op)

        from agent.overrides import apply_override
        apply_override(
            target_type="road", target_id="Blocked Road",
            new_status="blocked", reason="Flood",
        )

        findings = detect_consequence_alerts(fresh_repo)
        alert_findings = [f for f in findings if f["type"] == "consequence_alert"]
        # Should skip the operation without coordinates
        for f in alert_findings:
            assert f["evidence"]["operation_id"] != "op_noloc"


# ---------------------------------------------------------------------------
# 4. Severity Calculation
# ---------------------------------------------------------------------------

class TestSeverityCalculation:
    def test_critical_urgency_maps_to_critical(self):
        assert _severity_from_urgency("critical") == "critical"

    def test_high_urgency_maps_to_high(self):
        assert _severity_from_urgency("high") == "high"

    def test_medium_urgency_maps_to_medium(self):
        assert _severity_from_urgency("medium") == "medium"

    def test_low_urgency_maps_to_low(self):
        assert _severity_from_urgency("low") == "low"

    def test_unknown_urgency_defaults_to_medium(self):
        assert _severity_from_urgency("unknown") == "medium"


# ---------------------------------------------------------------------------
# 5. Age Formatting
# ---------------------------------------------------------------------------

class TestFormatAge:
    def test_minutes(self):
        assert _format_age(0.5) == "30m"

    def test_one_hour(self):
        result = _format_age(1.0)
        assert "1h" in result

    def test_multiple_hours(self):
        result = _format_age(3.25)
        assert "3h" in result


# ---------------------------------------------------------------------------
# 6. Evidence Generation
# ---------------------------------------------------------------------------

class TestEvidenceGeneration:
    def test_gap_finding_has_complete_evidence(self, fresh_repo):
        """Coordination gap finding contains all required evidence fields."""
        need = Need(
            id="need_ev", need_type="water", title="Water needed",
            district_id="district_a", location_name="Town A",
            urgency="critical", status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        fresh_repo.create_need(need)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        assert len(findings) == 1
        evidence = findings[0]["evidence"]
        assert "need_id" in evidence
        assert "need_title" in evidence
        assert "need_type" in evidence
        assert "need_age_hours" in evidence
        assert "created_at" in evidence
        assert "district_id" in evidence
        assert "offers" in evidence
        assert "operations" in evidence

    def test_finding_has_suggested_action(self, fresh_repo):
        """Every finding has a suggested_action dict."""
        need = Need(
            id="need_action", need_type="food", title="Food",
            district_id="district_a", status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        fresh_repo.create_need(need)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        assert len(findings) == 1
        action = findings[0]["suggested_action"]
        assert "label" in action
        assert "action" in action


# ---------------------------------------------------------------------------
# 7. Uncertainty / Data Gaps
# ---------------------------------------------------------------------------

class TestUncertaintyDataGaps:
    def test_run_analysis_returns_data_gaps(self, fresh_repo):
        """The full analysis includes data_gaps in the response."""
        result = run_coordinator_analysis(fresh_repo)
        assert "data_gaps" in result
        assert isinstance(result["data_gaps"], list)
        assert len(result["data_gaps"]) > 0

    def test_consequence_alert_has_uncertainty(self, fresh_repo, sample_org_a):
        """Consequence alerts include uncertainty notes."""
        fresh_repo.create_organization(sample_org_a)

        road = Road(
            id="road_unc", district_id="district_a",
            name="Uncertain Road", highway_type="tertiary",
            geometry_coords=[[94.0, 26.0], [94.1, 26.1]],
        )
        fresh_repo.upsert_roads([road])

        op = Operation(
            id="op_unc", name="Unc Op",
            lead_organization_id="org_a", district_id="district_a",
            lat=26.05, lon=94.05, status="ACTIVE",
        )
        fresh_repo.create_operation(op)

        from agent.overrides import apply_override
        apply_override(
            target_type="road", target_id="Uncertain Road",
            new_status="blocked", reason="Reported closure",
        )

        findings = detect_consequence_alerts(fresh_repo)
        alert_findings = [f for f in findings if f["type"] == "consequence_alert"]
        if alert_findings:
            assert len(alert_findings[0]["uncertainty"]) > 0


# ---------------------------------------------------------------------------
# 8. No Writes
# ---------------------------------------------------------------------------

class TestNoWrites:
    def test_analysis_does_not_create_needs(self, fresh_repo):
        """Running analysis should not create any new needs."""
        before_needs = len(fresh_repo.list_needs())
        run_coordinator_analysis(fresh_repo)
        after_needs = len(fresh_repo.list_needs())
        assert after_needs == before_needs

    def test_analysis_does_not_create_operations(self, fresh_repo):
        """Running analysis should not create any new operations."""
        before_ops = len(fresh_repo.list_operations())
        run_coordinator_analysis(fresh_repo)
        after_ops = len(fresh_repo.list_operations())
        assert after_ops == before_ops

    def test_analysis_does_not_create_offers(self, fresh_repo):
        """Running analysis should not create any new offers."""
        before_offers = len(fresh_repo.list_resource_offers())
        run_coordinator_analysis(fresh_repo)
        after_offers = len(fresh_repo.list_resource_offers())
        assert after_offers == before_offers


# ---------------------------------------------------------------------------
# 9. No District Hardcoding
# ---------------------------------------------------------------------------

class TestNoDistrictHardcoding:
    def test_works_with_arbitrary_district(self, fresh_repo):
        """Coordinator logic works with any district name — no hardcoded branches."""
        need = Need(
            id="need_custom", need_type="shelter", title="Shelter needed",
            district_id="custom_district_xyz",
            location_name="Village Alpha",
            urgency="high", status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        fresh_repo.create_need(need)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        assert len(findings) == 1
        assert findings[0]["evidence"]["district_id"] == "custom_district_xyz"
        assert findings[0]["location"] == "Village Alpha"

    def test_works_with_unknown_district(self, fresh_repo):
        """No district (None) should still work."""
        need = Need(
            id="need_nodist", need_type="other", title="General need",
            district_id=None, status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        fresh_repo.create_need(need)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        assert len(findings) == 1

    def test_all_four_assam_districts(self, fresh_repo):
        """Test with the four actual Assam districts — still no hardcoding."""
        districts = ["sivasagar", "jorhat", "charaideo", "golaghat"]
        for d in districts:
            fresh_repo.create_need(Need(
                id=f"need_{d}", need_type="food", title=f"Need in {d}",
                district_id=d, status="OPEN",
                created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            ))

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        assert len(findings) == 4
        found_districts = {f["evidence"]["district_id"] for f in findings}
        assert found_districts == set(districts)


# ---------------------------------------------------------------------------
# 10. Full Analysis Integration
# ---------------------------------------------------------------------------

class TestFullAnalysis:
    def test_returns_correct_structure(self, fresh_repo):
        """run_coordinator_analysis returns the expected response shape."""
        result = run_coordinator_analysis(fresh_repo)
        assert "generated_at" in result
        assert "findings" in result
        assert "summary" in result
        assert "data_gaps" in result
        assert isinstance(result["findings"], list)
        assert isinstance(result["summary"], dict)
        assert "total" in result["summary"]
        assert "critical" in result["summary"]
        assert "high" in result["summary"]
        assert "medium" in result["summary"]
        assert "low" in result["summary"]

    def test_summary_matches_findings(self, fresh_repo):
        """Summary counts match actual findings."""
        need = Need(
            id="need_sum", need_type="water", title="Water",
            district_id="district_a", urgency="critical", status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        fresh_repo.create_need(need)

        result = run_coordinator_analysis(fresh_repo)
        assert result["summary"]["total"] == len(result["findings"])
        sev_count = sum(
            1 for f in result["findings"] if f["severity"] == "critical"
        )
        assert result["summary"]["critical"] == sev_count

    def test_empty_database_returns_no_findings(self, fresh_repo):
        """Empty database → no findings, valid structure."""
        result = run_coordinator_analysis(fresh_repo)
        assert result["summary"]["total"] == 0
        assert len(result["findings"]) == 0


# ---------------------------------------------------------------------------
# Phase 7C: Review Targets
# ---------------------------------------------------------------------------

class TestReviewTargets:
    """Phase 7C: Every finding must have a valid review_target."""

    def test_all_findings_have_review_target(self, fresh_repo, sample_org_a, sample_org_b):
        """Every finding returned by the analysis has a review_target dict."""
        fresh_repo.create_organization(sample_org_a)
        fresh_repo.create_organization(sample_org_b)

        # Create a coordination gap
        need = Need(
            id="need_rt", need_type="water", title="Water needed",
            district_id="district_a", location_name="Town A",
            lat=26.5, lon=94.2,
            urgency="high", status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        fresh_repo.create_need(need)

        result = run_coordinator_analysis(fresh_repo)
        for f in result["findings"]:
            assert "review_target" in f, f"Finding {f['type']} missing review_target"
            rt = f["review_target"]
            assert isinstance(rt, dict)
            assert "panel_type" in rt
            assert "entity_id" in rt

    def test_coordination_gap_review_target_opens_need(self, fresh_repo):
        """Coordination gap review_target points to the need object."""
        need = Need(
            id="need_cg", need_type="food", title="Food shortage",
            district_id="district_x", location_name="Village X",
            lat=27.0, lon=94.5,
            urgency="critical", status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=4),
        )
        fresh_repo.create_need(need)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        assert len(findings) == 1
        rt = findings[0]["review_target"]
        assert rt["panel_type"] == "need"
        assert rt["entity_id"] == "need_cg"
        assert rt["entity_data"] is not None
        assert rt["entity_data"]["id"] == "need_cg"
        assert rt["entity_data"]["title"] == "Food shortage"
        assert rt["map_center"] == [27.0, 94.5]
        assert rt["district_id"] == "district_x"

    def test_coordination_gap_no_coords_map_center_is_none(self, fresh_repo):
        """Need without lat/lon → map_center is None."""
        need = Need(
            id="need_nocoord", need_type="shelter", title="Shelter",
            district_id="district_y", status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        fresh_repo.create_need(need)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        assert len(findings) == 1
        rt = findings[0]["review_target"]
        assert rt["map_center"] is None

    def test_duplicate_response_review_target_opens_need(self, fresh_repo, sample_org_a, sample_org_b):
        """Duplicate response review_target points to the duplicated need."""
        fresh_repo.create_organization(sample_org_a)
        fresh_repo.create_organization(sample_org_b)

        need = Need(
            id="need_dup_rt", need_type="food", title="Food",
            district_id="district_a", lat=26.1, lon=94.3,
            status="OPEN",
        )
        fresh_repo.create_need(need)

        op1 = Operation(
            id="op_dup1", name="Op A", need_id="need_dup_rt",
            lead_organization_id="org_a", district_id="district_a",
            status="ACTIVE",
        )
        op2 = Operation(
            id="op_dup2", name="Op B", need_id="need_dup_rt",
            lead_organization_id="org_b", district_id="district_a",
            status="PLANNING",
        )
        fresh_repo.create_operation(op1)
        fresh_repo.create_operation(op2)

        findings = detect_duplicate_responses(fresh_repo)
        dup = [f for f in findings if f["type"] == "duplicate_response"]
        assert len(dup) >= 1
        rt = dup[0]["review_target"]
        assert rt["panel_type"] == "need"
        assert rt["entity_id"] == "need_dup_rt"
        assert rt["entity_data"]["id"] == "need_dup_rt"

    def test_consequence_alert_review_target_opens_operation(self, fresh_repo, sample_org_a):
        """Consequence alert review_target points to the affected operation."""
        fresh_repo.create_organization(sample_org_a)

        road = Road(
            id="road_cr", district_id="district_a",
            name="Blocked Bridge", highway_type="primary",
            is_bridge=True,
            geometry_coords=[[94.0, 26.0], [94.1, 26.1]],
        )
        fresh_repo.upsert_roads([road])

        op = Operation(
            id="op_cr", name="Rescue Op",
            lead_organization_id="org_a", district_id="district_a",
            lat=26.05, lon=94.05, location_name="Town A",
            status="ACTIVE",
        )
        fresh_repo.create_operation(op)

        from agent.overrides import apply_override
        apply_override(
            target_type="road", target_id="Blocked Bridge",
            new_status="blocked", reason="Collapsed",
        )

        findings = detect_consequence_alerts(fresh_repo)
        alerts = [f for f in findings if f["type"] == "consequence_alert"]
        assert len(alerts) >= 1
        rt = alerts[0]["review_target"]
        assert rt["panel_type"] == "operation"
        assert rt["entity_id"] == "op_cr"
        assert rt["entity_data"]["id"] == "op_cr"
        assert rt["entity_data"]["name"] == "Rescue Op"
        assert rt["map_center"] == [26.05, 94.05]
        assert rt["district_id"] == "district_a"

    def test_review_target_ids_are_real_objects(self, fresh_repo, sample_org_a):
        """review_target.entity_id always corresponds to a real database object."""
        fresh_repo.create_organization(sample_org_a)

        need = Need(
            id="need_real", need_type="water", title="Water",
            district_id="district_a", status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        fresh_repo.create_need(need)

        result = run_coordinator_analysis(fresh_repo)
        for f in result["findings"]:
            rt = f["review_target"]
            if rt["panel_type"] == "need":
                assert fresh_repo.get_need(rt["entity_id"]) is not None, \
                    f"Need {rt['entity_id']} does not exist in repository"
            elif rt["panel_type"] == "operation":
                assert fresh_repo.get_operation(rt["entity_id"]) is not None, \
                    f"Operation {rt['entity_id']} does not exist in repository"

    def test_no_fabricated_ids(self, fresh_repo):
        """review_target.entity_id must not be empty or None."""
        need = Need(
            id="need_fab", need_type="medical", title="Medical",
            district_id="district_a", status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        fresh_repo.create_need(need)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        for f in findings:
            rt = f["review_target"]
            assert rt["entity_id"], "entity_id must not be empty"
            assert isinstance(rt["entity_id"], str)
            assert len(rt["entity_id"]) > 0

    def test_suggested_action_labels_are_review_not_autonomous(self, fresh_repo):
        """All suggested actions are review-oriented, not autonomous."""
        need = Need(
            id="need_label", need_type="food", title="Food",
            district_id="district_a", status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        fresh_repo.create_need(need)

        findings = detect_coordination_gaps(fresh_repo, threshold_hours=1.0)
        for f in findings:
            action = f["suggested_action"]
            assert action is not None
            assert "disabled" not in action, "Action should not be disabled"
            label_lower = action["label"].lower()
            assert "review" in label_lower, \
                f"Action label '{action['label']}' should contain 'review'"

    def test_review_target_has_panel_type_and_entity_id(self, fresh_repo):
        """Every review_target has the required fields."""
        need = Need(
            id="need_req", need_type="other", title="General",
            district_id="district_a", status="OPEN",
            created_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        fresh_repo.create_need(need)

        result = run_coordinator_analysis(fresh_repo)
        for f in result["findings"]:
            rt = f["review_target"]
            assert "panel_type" in rt
            assert "entity_id" in rt
            assert rt["panel_type"] in ("need", "operation", "offer", "road")
            assert isinstance(rt["entity_id"], str) and len(rt["entity_id"]) > 0
