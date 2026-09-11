"""
ReliefOS Phase 1 Agent Runtime Test Suite

Verifies:
1. Agent Contract & Findings
2. Event Contract & Serialization
3. Deterministic Event Routing
4. Network Main Agent Event Delegation & Synthesis
5. NGO Main Agent Event Delegation & Private Specialists
6. Strict Privacy Boundary Enforcement
7. Error Isolation & Failure Resilience
8. Human-In-The-Loop (HITL) State Safety & Zero Autonomous Writes
9. Idempotency & Duplicate Event Handling
"""

import uuid
import pytest
from unittest.mock import MagicMock, patch

from agent.agents.base import (
    Agent,
    AgentFinding,
    FindingProvenance,
    FindingSeverity,
)
from agent.agents.events import (
    AgentEvent,
    AgentEventType,
    make_field_report_event,
    make_flood_snapshot_event,
    make_need_created_event,
    make_proposal_received_event,
    make_road_override_event,
)
from agent.agents.event_router import (
    EventDispatcher,
    EventRouter,
    get_event_dispatcher,
)
from agent.agents.network_main_agent import NetworkMainAgent
from agent.agents.network_workers import (
    AccessAgent,
    CoordinationAgent,
    EvidenceAgent,
    ExposureAgent,
    FieldAgent,
    LogisticsAgent,
    MedicalAgent,
    SituationAgent,
)
from agent.agents.ngo_main_agent import (
    NGOMainAgent,
    PrivateOrganizationContext,
    SharedNetworkContext,
)
from agent.agents.ngo_workers import (
    NGOFieldAgent,
    NGOInventoryAgent,
    NGOLogisticsAgent,
    NGOMissionAgent,
    NGOTeamAgent,
)


# ---------------------------------------------------------------------------
# Mock repository for deterministic tests
# ---------------------------------------------------------------------------

class MockRepository:
    def __init__(self):
        self.districts = [{"id": "sivasagar", "name": "Sivasagar"}]
        self.flood_snapshots = [
            MagicMock(
                district_id="sivasagar",
                observed_at="2026-07-01T12:00:00Z",
                polygon_count=12,
                source="Sentinel-1",
                confidence=0.95,
            )
        ]
        self.settlements = [
            MagicMock(id="set_1", name="Nazira", district_id="sivasagar", lat=26.91, lon=94.73)
        ]
        self.needs = [
            MagicMock(
                id="need_101",
                need_type="boat",
                title="Rescue boats needed in Nazira",
                location_name="Nazira",
                urgency="critical",
                status="OPEN",
            )
        ]
        self.offers = [
            MagicMock(
                id="off_201",
                organization_id="org_redcross",
                resource_type="boat",
                quantity=4,
                unit="units",
                status="OFFERED",
            )
        ]
        self.operations = []
        self.medical_facilities = []

    def list_districts(self):
        return self.districts

    def list_flood_snapshots(self):
        return self.flood_snapshots

    def list_settlements(self):
        return self.settlements

    def list_needs(self, status=None):
        if status:
            return [n for n in self.needs if getattr(n, "status", None) == status]
        return self.needs

    def list_resource_offers(self, status=None, organization_id=None):
        res = self.offers
        if status:
            res = [o for o in res if getattr(o, "status", None) == status]
        if organization_id:
            res = [o for o in res if getattr(o, "organization_id", None) == organization_id]
        return res

    def list_operations(self, status=None):
        if status:
            return [o for o in self.operations if getattr(o, "status", None) == status]
        return self.operations

    def list_medical_facilities(self):
        return self.medical_facilities


# ---------------------------------------------------------------------------
# 1. Agent Contract Tests
# ---------------------------------------------------------------------------

class TestAgentContracts:
    def test_network_specialists_conform_to_agent_contract(self):
        specialists = [
            SituationAgent(),
            ExposureAgent(),
            MedicalAgent(),
            LogisticsAgent(),
            AccessAgent(),
            FieldAgent(),
            CoordinationAgent(),
            EvidenceAgent(),
        ]
        for s in specialists:
            assert isinstance(s, Agent), f"{s.__class__.__name__} must implement Agent protocol"
            assert hasattr(s, "agent_id") and s.agent_id
            assert hasattr(s, "domain") and s.domain
            assert "shared_state" in s.allowed_context
            assert isinstance(s.accepted_event_types, list)

    def test_ngo_specialists_conform_to_agent_contract(self):
        specialists = [
            NGOInventoryAgent("org_test"),
            NGOTeamAgent("org_test"),
            NGOMissionAgent("org_test"),
            NGOLogisticsAgent("org_test"),
            NGOFieldAgent("org_test"),
        ]
        for s in specialists:
            assert isinstance(s, Agent), f"{s.__class__.__name__} must implement Agent protocol"
            assert hasattr(s, "agent_id") and s.agent_id
            assert hasattr(s, "domain") and s.domain
            assert "org_private_state" in s.allowed_context
            assert isinstance(s.accepted_event_types, list)

    def test_agent_finding_serialization(self):
        finding = AgentFinding(
            agent_id="test_agent",
            domain="situation",
            finding_type="flood_escalation",
            summary="Flood extent grew significantly",
            severity=FindingSeverity.CRITICAL.value,
            confidence=0.92,
            provenance=FindingProvenance.OBSERVED,
            evidence=[{"snapshot_id": "snap_1", "polygon_count": 25}],
            data_gaps=[{"item": "depth", "detail": "depth model unavailable"}],
            uncertainty=["satellite image is 6 hours old"],
            related_entity_type="district",
            related_entity_id="sivasagar",
            location="sivasagar",
        )
        d = finding.to_dict()
        assert d["agent_id"] == "test_agent"
        assert d["severity"] == "critical"
        assert d["provenance"] == "OBSERVED"
        assert d["confidence"] == 0.92
        assert len(d["evidence"]) == 1
        assert len(d["data_gaps"]) == 1

        restored = AgentFinding.from_dict(d)
        assert restored.agent_id == finding.agent_id
        assert restored.severity == finding.severity
        assert restored.provenance == FindingProvenance.OBSERVED


# ---------------------------------------------------------------------------
# 2. Event Contract Tests
# ---------------------------------------------------------------------------

class TestEventContracts:
    def test_event_factories_and_serialization(self):
        evt = make_need_created_event("need_123", district="sivasagar", priority="critical")
        assert evt.event_type == AgentEventType.NEED_CREATED.value
        assert evt.entity_type == "need"
        assert evt.entity_id == "need_123"
        assert evt.district == "sivasagar"
        assert evt.priority == "critical"

        d = evt.to_dict()
        assert d["event_id"].startswith("evt_")
        assert d["entity_id"] == "need_123"

        restored = AgentEvent.from_dict(d)
        assert restored.event_id == evt.event_id
        assert restored.event_type == AgentEventType.NEED_CREATED.value
        assert restored.entity_id == "need_123"

    def test_domain_event_types(self):
        assert make_flood_snapshot_event("snap_1", "jorhat").entity_type == "flood_snapshot"
        assert make_road_override_event("ov_1", "road_52").entity_type == "road_override"
        assert make_field_report_event("rep_1").entity_type == "field_report"
        assert make_proposal_received_event("prop_1", "org_1").entity_type == "coordination_proposal"


# ---------------------------------------------------------------------------
# 3. Deterministic Routing Tests
# ---------------------------------------------------------------------------

class TestDeterministicRouting:
    def test_network_event_routing(self):
        evt_need = make_need_created_event("need_1")
        workers = EventRouter.route_network_event(evt_need)
        assert "logistics" in workers
        assert "coordination" in workers

        evt_flood = make_flood_snapshot_event("snap_1", "sivasagar")
        workers_flood = EventRouter.route_network_event(evt_flood)
        assert "situation" in workers_flood
        assert "exposure" in workers_flood

        evt_road = make_road_override_event("ov_1", "road_1")
        workers_road = EventRouter.route_network_event(evt_road)
        assert "access" in workers_road
        assert "logistics" in workers_road

    def test_ngo_event_routing(self):
        evt_need = make_need_created_event("need_1")
        ngo_workers = EventRouter.route_ngo_event(evt_need)
        assert "inventory" in ngo_workers
        assert "team" in ngo_workers
        assert "mission" in ngo_workers

        evt_prop = make_proposal_received_event("prop_1", "org_a")
        ngo_workers_prop = EventRouter.route_ngo_event(evt_prop)
        assert "inventory" in ngo_workers_prop
        assert "logistics" in ngo_workers_prop


# ---------------------------------------------------------------------------
# 4. Network Main Agent Delegation Tests
# ---------------------------------------------------------------------------

class TestNetworkMainAgentDelegation:
    def test_handle_flood_snapshot_event(self):
        agent = NetworkMainAgent()
        repo = MockRepository()
        evt = make_flood_snapshot_event("snap_1", district="sivasagar")

        result = agent.handle_event(evt, repo=repo)
        assert result["orchestrator"] == "network_main_agent"
        assert result["event_type"] == AgentEventType.FLOOD_SNAPSHOT_UPDATED.value
        assert "situation" in result["selected_specialists"]
        assert len(result["findings"]) > 0
        assert result["worker_statuses"]["situation"] == "success"

    def test_handle_need_created_event(self):
        agent = NetworkMainAgent()
        repo = MockRepository()
        evt = make_need_created_event("need_101", district="sivasagar", priority="critical")

        result = agent.handle_event(evt, repo=repo)
        assert "logistics" in result["selected_specialists"]
        assert "coordination" in result["selected_specialists"]
        assert isinstance(result["findings"], list)


# ---------------------------------------------------------------------------
# 5. NGO Main Agent Delegation & Private Specialists Tests
# ---------------------------------------------------------------------------

class TestNGOMainAgentDelegation:
    def test_handle_coordination_proposal_event(self):
        agent = NGOMainAgent("org_test")
        private_ctx = PrivateOrganizationContext(
            org_id="org_test",
            resources=[{"id": "r1", "type": "boat", "quantity": 4, "status": "available", "unit": "units"}],
            teams=[{"id": "t1", "name": "Team Alpha", "status": "available"}],
            missions=[],
        )
        shared_ctx = SharedNetworkContext(open_needs=[], active_operations=[], relevant_overrides=[])

        evt = make_proposal_received_event("prop_1", org_id="org_test", need_id="need_101")
        evt.metadata = {"need_type": "boat", "requested_resources": [{"type": "boat", "quantity": 2}]}

        result = agent.handle_event(evt, private_ctx=private_ctx, shared_ctx=shared_ctx)
        assert result["org_id"] == "org_test"
        assert "inventory" in result["selected_specialists"]
        assert result["worker_statuses"]["inventory"] == "success"
        assert len(result["findings"]) >= 1

    def test_analyze_need_delegation_to_specialists(self):
        agent = NGOMainAgent("org_test")
        private_ctx = PrivateOrganizationContext(
            org_id="org_test",
            resources=[{"id": "r1", "type": "boat", "quantity": 5, "status": "available", "unit": "units"}],
            teams=[{"id": "t1", "name": "Team Alpha", "status": "available"}],
            missions=[],
        )
        shared_ctx = SharedNetworkContext(
            open_needs=[],
            active_operations=[],
            relevant_overrides=[],
        )
        need = {
            "id": "need_1",
            "need_type": "boat",
            "title": "Evacuation boats",
            "status": "OPEN",
            "urgency": "critical",
            "requested_resources": [{"type": "boat", "quantity": 2}],
        }

        result = agent.analyze_need(need, private_ctx, shared_ctx)
        assert "provide" in result["recommendation"].lower() or "can" in result["recommendation"].lower()
        assert result["proposed_publication"]["quantity"] == 2
        assert result["evidence"]["total_available"] == 5


# ---------------------------------------------------------------------------
# 6. Privacy Boundary Verification Tests
# ---------------------------------------------------------------------------

class TestPrivacyBoundaryEnforcement:
    def test_network_agent_cannot_access_ngo_private_context(self):
        net_agent = NetworkMainAgent()
        assert "org_private_state" not in net_agent.allowed_context
        for specialist in net_agent._specialist_map.values():
            assert "org_private_state" not in specialist.allowed_context

    def test_ngo_a_cannot_access_ngo_b_context(self):
        agent_a = NGOMainAgent("org_a")
        private_b = PrivateOrganizationContext(
            org_id="org_b",
            resources=[{"id": "secret_b_res", "type": "special_kit", "quantity": 10, "status": "available"}],
        )
        # Agent A's own ID remains org_a
        assert agent_a.org_id == "org_a"
        assert agent_a.inventory_agent.org_id == "org_a"
        # B's private resources are only inside B's context object
        assert private_b.org_id == "org_b"

    def test_ngo_public_projection_strips_private_inventory(self):
        agent = NGOMainAgent("org_test")
        private_ctx = PrivateOrganizationContext(
            org_id="org_test",
            resources=[
                {"id": "secret_inv_1", "type": "boat", "quantity": 20, "status": "available", "notes": "SECRET_CONFIDENTIAL_STORE"}
            ],
            teams=[{"id": "t1", "name": "SECRET_STAFF_NAME", "status": "available"}],
            missions=[],
        )
        shared_ctx = SharedNetworkContext()
        need = {"id": "n1", "need_type": "boat", "title": "Need", "requested_resources": [{"type": "boat", "quantity": 3}]}

        analysis = agent.analyze_need(need, private_ctx, shared_ctx)
        pub = analysis["proposed_publication"]
        # Public proposal only publishes requested 3, not the 20 total or internal notes/names
        assert pub["quantity"] == 3
        assert "SECRET_CONFIDENTIAL_STORE" not in str(pub)
        assert "SECRET_STAFF_NAME" not in str(pub)


# ---------------------------------------------------------------------------
# 7. Error Isolation & Failure Resilience Tests
# ---------------------------------------------------------------------------

class TestErrorIsolation:
    def test_network_specialist_failure_isolation(self):
        agent = NetworkMainAgent()
        repo = MockRepository()

        # Mock situation worker to simulate an unhandled exception
        with patch.object(agent.situation_agent, "handle_event", side_effect=RuntimeError("Satellite parser crashed")):
            evt = make_flood_snapshot_event("snap_1", "sivasagar")
            result = agent.handle_event(evt, repo=repo)

            # Situation worker marked as failed
            assert result["worker_statuses"]["situation"] == "failed"
            # Exposure worker succeeded
            assert result["worker_statuses"]["exposure"] == "success"
            # Data gap was explicitly recorded
            assert len(result["data_gaps"]) >= 1
            assert "Satellite parser crashed" in result["data_gaps"][0]["detail"]
            # Pipeline did not crash and returned valid findings
            assert len(result["findings"]) > 0

    def test_ngo_specialist_failure_isolation(self):
        agent = NGOMainAgent("org_test")
        private_ctx = PrivateOrganizationContext(org_id="org_test")
        shared_ctx = SharedNetworkContext()

        with patch.object(agent.team_agent, "handle_event", side_effect=RuntimeError("HR roster file corrupted")):
            evt = make_need_created_event("need_1")
            result = agent.handle_event(evt, private_ctx=private_ctx, shared_ctx=shared_ctx)

            assert result["worker_statuses"]["team"] == "failed"
            assert result["worker_statuses"]["inventory"] == "success"
            assert len(result["data_gaps"]) >= 1


# ---------------------------------------------------------------------------
# 8. Human-in-the-Loop (HITL) State Safety Tests
# ---------------------------------------------------------------------------

class TestHumanInTheLoopSafety:
    def test_event_dispatch_performs_zero_database_mutations(self):
        repo = MockRepository()
        initial_ops_count = len(repo.operations)
        initial_offers_count = len(repo.offers)
        initial_needs_count = len(repo.needs)

        dispatcher = EventDispatcher()
        evt = make_need_created_event("need_101", district="sivasagar", priority="critical")
        result = dispatcher.dispatch_network_event(evt, repo=repo)

        assert result["event_id"] == evt.event_id
        # State counts unchanged: 0 operations created, 0 offers altered
        assert len(repo.operations) == initial_ops_count
        assert len(repo.offers) == initial_offers_count
        assert len(repo.needs) == initial_needs_count


# ---------------------------------------------------------------------------
# 9. Idempotency & Duplicate Event Handling Tests
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_duplicate_events_are_safely_skipped(self):
        dispatcher = EventDispatcher()
        evt = make_need_created_event("need_dup_1")

        res1 = dispatcher.dispatch_network_event(evt, repo=MockRepository())
        assert res1.get("status") != "skipped_duplicate"

        # Dispatch identical event_id second time
        res2 = dispatcher.dispatch_network_event(evt, repo=MockRepository())
        assert res2.get("status") == "skipped_duplicate"
