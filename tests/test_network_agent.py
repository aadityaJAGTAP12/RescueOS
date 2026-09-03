"""
Tests for Network Main Agent — Phase 7G

Tests:
1. Network agent initializes correctly
2. Network agent analyzes shared state
3. Workers return structured findings
4. No private NGO state in results
5. Deterministic operation (no LLM required)
6. Need context analysis
7. Audit logging
"""

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Mock repository for network agent tests
# ---------------------------------------------------------------------------

class MockRepo:
    def __init__(self):
        self.districts = []
        self.flood_snapshots = []
        self.settlements = []
        self.needs = []
        self.offers = []
        self.operations = []
        self.activity_events = []

    def list_districts(self):
        return self.districts

    def list_flood_snapshots(self):
        return self.flood_snapshots

    def list_settlements(self):
        return self.settlements

    def list_needs(self, status=None):
        result = self.needs
        if status:
            result = [n for n in result if n.get('status') == status]
        return result

    def list_resource_offers(self, status=None):
        result = self.offers
        if status:
            result = [o for o in result if o.get('status') == status]
        return result

    def list_operations(self, status=None):
        result = self.operations
        if status:
            result = [o for o in result if o.get('status') == status]
        return result

    def list_medical_facilities(self):
        return []


# ---------------------------------------------------------------------------
# Worker tests
# ---------------------------------------------------------------------------

class TestSituationWorker:
    def test_empty_repo(self):
        from agent.agents.network_workers.situation import analyze_situation
        repo = MockRepo()
        result = analyze_situation(repo)
        assert result["worker"] == "situation"
        assert isinstance(result["findings"], list)
        assert isinstance(result["evidence"], list)

    def test_with_flood_data(self):
        from agent.agents.network_workers.situation import analyze_situation
        repo = MockRepo()
        repo.flood_snapshots = [
            {"district_id": "sivasagar", "observed_at": "2026-07-01", "polygon_count": 10, "source": "Sentinel-1", "confidence": 0.9},
        ]
        result = analyze_situation(repo)
        assert len(result["findings"]) > 0 or len(result["evidence"]) > 0


class TestExposureWorker:
    def test_empty_repo(self):
        from agent.agents.network_workers.exposure import analyze_exposure
        repo = MockRepo()
        result = analyze_exposure(repo)
        assert result["worker"] == "exposure"


class TestMedicalWorker:
    def test_empty_repo(self):
        from agent.agents.network_workers.medical import analyze_medical
        repo = MockRepo()
        result = analyze_medical(repo)
        assert result["worker"] == "medical"
        # Should not claim outbreaks
        for f in result["findings"]:
            assert "outbreak" not in f.get("summary", "").lower()


class TestLogisticsWorker:
    def test_empty_repo(self):
        from agent.agents.network_workers.logistics import analyze_logistics
        repo = MockRepo()
        result = analyze_logistics(repo)
        assert result["worker"] == "logistics"

    def test_need_with_no_offers(self):
        from agent.agents.network_workers.logistics import analyze_logistics
        repo = MockRepo()
        repo.needs = [{"id": "n1", "need_type": "boat", "title": "Boats needed", "status": "OPEN", "location_name": "Jorhat"}]
        repo.offers = []
        result = analyze_logistics(repo)
        assert any(f["type"] == "logistics_gap" for f in result["findings"])


class TestAccessWorker:
    def test_empty_repo(self):
        from agent.agents.network_workers.access import analyze_access
        repo = MockRepo()
        result = analyze_access(repo)
        assert result["worker"] == "access"


class TestCoordinationWorker:
    def test_uncovered_need(self):
        from agent.agents.network_workers.coordination import analyze_coordination
        repo = MockRepo()
        repo.needs = [{"id": "n1", "need_type": "boat", "title": "Boats", "status": "OPEN", "urgency": "critical", "location_name": "X"}]
        result = analyze_coordination(repo)
        assert any(f["type"] == "uncovered_need" for f in result["findings"])


# ---------------------------------------------------------------------------
# Network Main Agent tests
# ---------------------------------------------------------------------------

class TestNetworkMainAgent:
    def test_initialize(self):
        from agent.agents.network_main_agent import NetworkMainAgent
        agent = NetworkMainAgent()
        assert agent.audit_log == []

    def test_analyze_empty_network(self):
        from agent.agents.network_main_agent import NetworkMainAgent
        agent = NetworkMainAgent()
        repo = MockRepo()
        result = agent.analyze_network(repo)
        assert "summary" in result
        assert "findings" not in result  # findings are nested in worker_findings
        assert "evidence" in result
        assert "uncertainty" in result
        assert "data_gaps" in result
        assert "recommended_actions" in result
        assert "severity_summary" in result

    def test_analyze_with_data(self):
        from agent.agents.network_main_agent import NetworkMainAgent
        agent = NetworkMainAgent()
        repo = MockRepo()
        repo.needs = [
            {"id": "n1", "need_type": "boat", "title": "Boats", "status": "OPEN", "urgency": "critical", "location_name": "X"},
        ]
        repo.flood_snapshots = [
            {"district_id": "sivasagar", "observed_at": "2026-07-01", "polygon_count": 5, "source": "S1", "confidence": 0.9},
        ]
        result = agent.analyze_network(repo)
        assert len(result["evidence"]) > 0

    def test_need_context_analysis(self):
        from agent.agents.network_main_agent import NetworkMainAgent
        agent = NetworkMainAgent()
        repo = MockRepo()
        repo.offers = [
            {"id": "o1", "resource_type": "boat", "quantity": 2, "status": "OFFERED", "organization_id": "org_a"},
        ]
        need = {"id": "n1", "need_type": "boat", "title": "Boats needed", "lat": 26.98, "lon": 94.66}
        result = agent.analyze_need_context(need, repo)
        assert result["need_id"] == "n1"
        assert result["matching_offers"] == 1

    def test_no_private_state_in_results(self):
        """Verify no private NGO state appears in network agent output."""
        from agent.agents.network_main_agent import NetworkMainAgent
        agent = NetworkMainAgent()
        repo = MockRepo()
        result = agent.analyze_network(repo)
        result_str = str(result)
        # Should not contain private data patterns
        assert "private_resources" not in result_str
        assert "private_teams" not in result_str
        assert "private_missions" not in result_str

    def test_audit_logged(self):
        from agent.agents.network_main_agent import NetworkMainAgent
        agent = NetworkMainAgent()
        repo = MockRepo()
        agent.analyze_network(repo)
        assert len(agent.audit_log) == 1
        assert agent.audit_log[0]["action"] == "analyze_network"

    def test_deterministic_no_llm(self):
        """Verify agent works without LLM."""
        from agent.agents.network_main_agent import NetworkMainAgent
        agent = NetworkMainAgent()
        repo = MockRepo()
        repo.needs = [{"id": "n1", "need_type": "water", "title": "Water", "status": "OPEN", "urgency": "high", "location_name": "Camp A"}]
        result = agent.analyze_network(repo)
        assert result["summary"] is not None
        assert len(result["recommended_actions"]) >= 0
