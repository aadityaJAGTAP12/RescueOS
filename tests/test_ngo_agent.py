"""
Tests for NGO Main Agent — Phase 7F

Tests:
1. Private context isolation
2. Need analysis with available resources
3. Need analysis with no resources
4. Need analysis with commitment conflicts
5. Situation summary
6. Publication boundary
7. Network cannot access private state
"""

import pytest
from agent.agents.ngo_main_agent import (
    NGOMainAgent,
    PrivateOrganizationContext,
    SharedNetworkContext,
    analyze_need_for_org,
    get_org_situation,
)


# ---------------------------------------------------------------------------
# Private Context Tests
# ---------------------------------------------------------------------------

class TestPrivateContext:
    def test_available_resources(self):
        ctx = PrivateOrganizationContext(
            org_id="org_test",
            resources=[
                {"id": "r1", "type": "boat", "quantity": 2, "status": "available"},
                {"id": "r2", "type": "boat", "quantity": 1, "status": "committed"},
                {"id": "r3", "type": "water", "quantity": 100, "status": "available"},
            ],
        )
        available = ctx.get_available_resources("boat")
        assert len(available) == 1
        assert available[0]["id"] == "r1"

    def test_available_teams(self):
        ctx = PrivateOrganizationContext(
            org_id="org_test",
            teams=[
                {"id": "t1", "name": "Alpha", "status": "available"},
                {"id": "t2", "name": "Bravo", "status": "assigned"},
            ],
        )
        available = ctx.get_available_teams()
        assert len(available) == 1
        assert available[0]["name"] == "Alpha"

    def test_active_missions(self):
        ctx = PrivateOrganizationContext(
            org_id="org_test",
            missions=[
                {"id": "m1", "name": "Mission 1", "status": "ACTIVE"},
                {"id": "m2", "name": "Mission 2", "status": "COMPLETED"},
            ],
        )
        active = ctx.get_active_missions()
        assert len(active) == 1
        assert active[0]["name"] == "Mission 1"

    def test_resource_conflict(self):
        ctx = PrivateOrganizationContext(
            org_id="org_test",
            resources=[
                {"id": "r1", "type": "boat", "quantity": 1, "status": "available"},
            ],
            missions=[
                {"id": "m1", "name": "Mission 1", "status": "ACTIVE", "assigned_resources": [{"type": "boat"}]},
            ],
        )
        has_conflict, reason = ctx.has_resource_conflict("boat", 1)
        assert has_conflict is True
        assert "Mission 1" in reason

    def test_no_conflict(self):
        ctx = PrivateOrganizationContext(
            org_id="org_test",
            resources=[
                {"id": "r1", "type": "boat", "quantity": 2, "status": "available"},
            ],
            missions=[],
        )
        has_conflict, reason = ctx.has_resource_conflict("boat", 1)
        assert has_conflict is False


# ---------------------------------------------------------------------------
# Need Analysis Tests
# ---------------------------------------------------------------------------

class TestNeedAnalysis:
    def test_analyze_with_available_resources(self):
        need = {
            "id": "need_1",
            "need_type": "boat",
            "title": "Rescue boats needed",
            "status": "OPEN",
            "urgency": "high",
            "requested_resources": [{"type": "boat", "quantity": 2}],
        }
        result = analyze_need_for_org(
            org_id="org_test",
            need=need,
            private_resources=[
                {"id": "r1", "type": "boat", "quantity": 3, "status": "available", "unit": "units"},
            ],
            private_teams=[
                {"id": "t1", "name": "Alpha", "status": "available"},
            ],
        )
        assert "provide" in result["recommendation"].lower() or "can" in result["recommendation"].lower()
        assert result["proposed_publication"] is not None
        assert result["proposed_publication"]["resource_type"] == "boat"
        assert result["proposed_publication"]["quantity"] == 2

    def test_analyze_with_no_resources(self):
        need = {
            "id": "need_2",
            "need_type": "boat",
            "title": "Rescue boats needed",
            "status": "OPEN",
            "urgency": "high",
            "requested_resources": [{"type": "boat", "quantity": 2}],
        }
        result = analyze_need_for_org(
            org_id="org_test",
            need=need,
            private_resources=[],
            private_teams=[],
        )
        assert "cannot" in result["recommendation"].lower() or "no" in result["recommendation"].lower()
        assert result["proposed_publication"] is None

    def test_analyze_with_conflict(self):
        need = {
            "id": "need_3",
            "need_type": "boat",
            "title": "Rescue boats needed",
            "status": "OPEN",
            "urgency": "high",
            "requested_resources": [{"type": "boat", "quantity": 1}],
        }
        result = analyze_need_for_org(
            org_id="org_test",
            need=need,
            private_resources=[
                {"id": "r1", "type": "boat", "quantity": 1, "status": "available"},
            ],
            private_teams=[
                {"id": "t1", "name": "Alpha", "status": "available"},
            ],
            private_missions=[
                {"id": "m1", "name": "Mission 1", "status": "ACTIVE", "assigned_resources": [{"type": "boat"}]},
            ],
        )
        assert "conflict" in result["recommendation"].lower()


# ---------------------------------------------------------------------------
# Situation Summary Tests
# ---------------------------------------------------------------------------

class TestSituationSummary:
    def test_situation_summary(self):
        result = get_org_situation(
            org_id="org_test",
            private_resources=[
                {"id": "r1", "type": "boat", "quantity": 2, "status": "available"},
            ],
            private_teams=[
                {"id": "t1", "name": "Alpha", "status": "available"},
            ],
            private_missions=[],
            network_needs=[
                {"id": "need_1", "need_type": "boat", "status": "OPEN"},
            ],
        )
        assert result["org_id"] == "org_test"
        assert result["private_summary"]["available_resources"] == 1
        assert result["private_summary"]["available_teams"] == 1
        assert result["network_summary"]["open_needs"] == 1

    def test_attention_items(self):
        result = get_org_situation(
            org_id="org_test",
            private_resources=[
                {"id": "r1", "type": "boat", "quantity": 2, "status": "available"},
            ],
            network_needs=[
                {"id": "need_1", "need_type": "boat", "status": "OPEN"},
            ],
        )
        # Should have attention item about matching need
        attention_types = [a["type"] for a in result["attention"]]
        assert "opportunity" in attention_types


# ---------------------------------------------------------------------------
# Privacy Boundary Tests
# ---------------------------------------------------------------------------

class TestPrivacyBoundary:
    def test_private_context_not_in_shared(self):
        """Verify that private context is separate from shared context."""
        private = PrivateOrganizationContext(
            org_id="org_test",
            resources=[{"id": "r1", "type": "boat", "quantity": 5, "status": "available"}],
        )
        shared = SharedNetworkContext(
            open_needs=[{"id": "need_1", "need_type": "boat"}],
        )
        # Private context should not appear in shared
        shared_dict = shared.to_dict()
        assert "resources" not in shared_dict  # No private resources in shared
        assert "r1" not in str(shared_dict)  # Private resource ID not in shared

    def test_proposed_publication_is_subset(self):
        """Verify that proposed publication is a subset of private state."""
        need = {
            "id": "need_1",
            "need_type": "boat",
            "title": "Rescue boats",
            "status": "OPEN",
            "urgency": "high",
            "requested_resources": [{"type": "boat", "quantity": 2}],
        }
        result = analyze_need_for_org(
            org_id="org_test",
            need=need,
            private_resources=[
                {"id": "r1", "type": "boat", "quantity": 5, "status": "available", "unit": "units", "location": "Jorhat"},
            ],
            private_teams=[{"id": "t1", "status": "available"}],
        )
        pub = result["proposed_publication"]
        assert pub is not None
        # Publication should only expose what was explicitly chosen
        assert pub["quantity"] <= 5  # Not exposing full inventory
        assert pub["resource_type"] == "boat"

    def test_audit_log_recorded(self):
        agent = NGOMainAgent("org_test")
        need = {"id": "need_1", "need_type": "boat", "title": "Test", "status": "OPEN"}
        private = PrivateOrganizationContext(org_id="org_test")
        shared = SharedNetworkContext()
        agent.analyze_need(need, private, shared)
        assert len(agent.audit_log) == 1
        assert agent.audit_log[0]["action"] == "analyze_need"
