"""
Tests for ReliefOS Delta Engine — Phase 7D

Tests:
1. Delta computation with mock repository
2. Report deduplication grouping
3. Evidence synthesis
4. Temporal proximity check
5. Text normalization
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Mock repository for delta tests
# ---------------------------------------------------------------------------

class MockRepo:
    """Minimal mock repository for delta engine testing."""

    def __init__(self):
        self.needs = []
        self.operations = []
        self.offers = []
        self.activity_events = []
        self.flood_snapshots = []

    def list_needs(self, status=None, district_id=None, urgency=None):
        result = self.needs
        if status:
            result = [n for n in result if n.status == status]
        return result

    def get_need(self, need_id):
        for n in self.needs:
            if n.id == need_id:
                return n
        return None

    def list_operations(self, status=None, district_id=None, lead_organization_id=None):
        result = self.operations
        if status:
            result = [o for o in result if o.status == status]
        return result

    def get_operation(self, op_id):
        for o in self.operations:
            if o.id == op_id:
                return o
        return None

    def list_resource_offers(self, status=None, district_id=None, organization_id=None, resource_type=None):
        result = self.offers
        if status:
            result = [o for o in result if o.status == status]
        return result

    def list_activity_events(self):
        return self.activity_events

    def list_flood_snapshots(self):
        return self.flood_snapshots


class MockNeed:
    def __init__(self, id, status="OPEN", urgency="medium", need_type="water",
                 title="Test Need", lat=26.98, lon=94.66, district_id="sivasagar",
                 location_name="Test Location", created_at=None, updated_at=None):
        self.id = id
        self.status = status
        self.urgency = urgency
        self.need_type = need_type
        self.title = title
        self.lat = lat
        self.lon = lon
        self.district_id = district_id
        self.location_name = location_name
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        self.requested_resources = []
        self.reporter_id = "test"
        self.reporter_type = "coordinator"
        self.confidence = 0.5
        self.metadata = {}

    def to_dict(self):
        return {
            "id": self.id, "status": self.status, "urgency": self.urgency,
            "need_type": self.need_type, "title": self.title,
            "lat": self.lat, "lon": self.lon, "district_id": self.district_id,
            "location_name": self.location_name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class MockOperation:
    def __init__(self, id, status="PLANNING", name="Test Op",
                 operation_type="collaboration", need_id=None,
                 lead_organization_id="org_a", lat=26.98, lon=94.66,
                 district_id="sivasagar", location_name="Test Location",
                 created_at=None):
        self.id = id
        self.status = status
        self.name = name
        self.operation_type = operation_type
        self.need_id = need_id
        self.lead_organization_id = lead_organization_id
        self.lat = lat
        self.lon = lon
        self.district_id = district_id
        self.location_name = location_name
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = self.created_at
        self.description = ""
        self.metadata = {}

    def to_dict(self):
        return {"id": self.id, "status": self.status, "name": self.name}


class MockActivityEvent:
    def __init__(self, id, entity_type, entity_id, event_type, actor="system",
                 detail="", created_at=None):
        self.id = id
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.event_type = event_type
        self.actor = actor
        self.detail = detail
        self.created_at = created_at or datetime.now(timezone.utc)
        self.metadata = {}


# ---------------------------------------------------------------------------
# Delta computation tests
# ---------------------------------------------------------------------------

class TestDeltaComputation:
    def test_empty_repository(self):
        from agent.delta import compute_delta
        repo = MockRepo()
        result = compute_delta(repo)
        assert result["summary"]["new_needs"] == 0
        assert result["summary"]["total_active_needs"] == 0
        assert result["directional"]["resource_gap"] == "stable"

    def test_new_needs_counted(self):
        from agent.delta import compute_delta
        repo = MockRepo()
        now = datetime.now(timezone.utc)
        repo.needs = [
            MockNeed("n1", status="OPEN", created_at=now - timedelta(hours=1)),
            MockNeed("n2", status="OPEN", created_at=now - timedelta(hours=2)),
        ]
        repo.activity_events = [
            MockActivityEvent("e1", "need", "n1", "need_created", created_at=now - timedelta(hours=1)),
            MockActivityEvent("e2", "need", "n2", "need_created", created_at=now - timedelta(hours=2)),
        ]
        result = compute_delta(repo)
        assert result["summary"]["new_needs"] == 2
        assert result["summary"]["total_active_needs"] == 2

    def test_resolved_needs_counted(self):
        from agent.delta import compute_delta
        repo = MockRepo()
        now = datetime.now(timezone.utc)
        repo.needs = [
            MockNeed("n1", status="OPEN"),
            MockNeed("n2", status="RESOLVED"),
        ]
        repo.activity_events = [
            MockActivityEvent("e1", "need", "n2", "need_resolved", created_at=now - timedelta(hours=1)),
        ]
        result = compute_delta(repo)
        assert result["summary"]["resolved_needs"] == 1
        assert result["summary"]["total_active_needs"] == 1

    def test_directional_resource_gap_up(self):
        from agent.delta import compute_delta
        repo = MockRepo()
        now = datetime.now(timezone.utc)
        repo.activity_events = [
            MockActivityEvent("e1", "need", "n1", "need_created", created_at=now - timedelta(hours=1)),
            MockActivityEvent("e2", "need", "n2", "need_created", created_at=now - timedelta(hours=2)),
            MockActivityEvent("e3", "resource_offer", "o1", "resource_offered", created_at=now - timedelta(hours=3)),
        ]
        result = compute_delta(repo)
        assert result["directional"]["resource_gap"] == "up"

    def test_directional_stable(self):
        from agent.delta import compute_delta
        repo = MockRepo()
        now = datetime.now(timezone.utc)
        repo.activity_events = [
            MockActivityEvent("e1", "need", "n1", "need_created", created_at=now - timedelta(hours=1)),
            MockActivityEvent("e2", "resource_offer", "o1", "resource_offered", created_at=now - timedelta(hours=2)),
        ]
        result = compute_delta(repo)
        assert result["directional"]["resource_gap"] == "stable"


# ---------------------------------------------------------------------------
# Report deduplication tests
# ---------------------------------------------------------------------------

class TestReportDeduplication:
    def test_empty_reports(self):
        from agent.delta import deduplicate_reports
        result = deduplicate_reports([])
        assert result == []

    def test_single_report_no_grouping(self):
        from agent.delta import deduplicate_reports
        reports = [{
            "id": "r1",
            "lat": 26.98,
            "lon": 94.66,
            "timestamp": "2026-08-31T10:00:00Z",
            "note": "Road blocked near school",
            "needs": ["water"],
            "source": "community_report",
            "verified": False,
            "people_count": 10,
            "location_description": "near school",
            "extraction_confidence": "medium",
            "raw_text": "Road blocked near school",
        }]
        result = deduplicate_reports(reports)
        assert len(result) == 1
        assert result[0]["report_count"] == 1

    def test_identical_reports_grouped(self):
        from agent.delta import deduplicate_reports
        now = datetime.now(timezone.utc)
        reports = []
        for i in range(5):
            reports.append({
                "id": f"r{i}",
                "lat": None,
                "lon": None,
                "timestamp": (now - timedelta(minutes=i * 10)).isoformat(),
                "note": "Road blocked near Jorhat due to flooding",
                "needs": [],
                "source": "field_intelligence_text",
                "verified": False,
                "people_count": 0,
                "location_description": None,
                "extraction_confidence": "low",
                "raw_text": "Road blocked near Jorhat due to flooding",
            })
        result = deduplicate_reports(reports)
        assert len(result) == 1
        assert result[0]["report_count"] == 5
        assert result[0]["verified_count"] == 0

    def test_different_reports_not_grouped(self):
        from agent.delta import deduplicate_reports
        now = datetime.now(timezone.utc)
        reports = [
            {
                "id": "r1",
                "lat": 26.98,
                "lon": 94.66,
                "timestamp": now.isoformat(),
                "note": "Water shortage at camp",
                "needs": ["water"],
                "source": "community_report",
                "verified": False,
                "people_count": 20,
                "location_description": "camp A",
                "extraction_confidence": "medium",
                "raw_text": "Water shortage at camp",
            },
            {
                "id": "r2",
                "lat": 27.5,
                "lon": 95.0,
                "timestamp": now.isoformat(),
                "note": "Medical emergency at hospital",
                "needs": ["medical"],
                "source": "community_report",
                "verified": False,
                "people_count": 5,
                "location_description": "hospital B",
                "extraction_confidence": "high",
                "raw_text": "Medical emergency at hospital",
            },
        ]
        result = deduplicate_reports(reports)
        assert len(result) == 2

    def test_verified_count(self):
        from agent.delta import deduplicate_reports
        now = datetime.now(timezone.utc)
        reports = [
            {
                "id": "r1",
                "lat": None,
                "lon": None,
                "timestamp": now.isoformat(),
                "note": "Bridge collapsed",
                "needs": ["transport"],
                "source": "field_intelligence_text",
                "verified": True,
                "people_count": 0,
                "location_description": "bridge X",
                "extraction_confidence": "high",
                "raw_text": "Bridge collapsed",
            },
            {
                "id": "r2",
                "lat": None,
                "lon": None,
                "timestamp": (now - timedelta(minutes=5)).isoformat(),
                "note": "Bridge collapsed",
                "needs": ["transport"],
                "source": "community_report",
                "verified": False,
                "people_count": 0,
                "location_description": "bridge X",
                "extraction_confidence": "low",
                "raw_text": "Bridge collapsed",
            },
        ]
        result = deduplicate_reports(reports)
        assert len(result) == 1
        assert result[0]["verified_count"] == 1
        assert result[0]["report_count"] == 2


# ---------------------------------------------------------------------------
# Evidence synthesis tests
# ---------------------------------------------------------------------------

class TestEvidenceSynthesis:
    def test_need_with_no_data(self):
        from agent.delta import synthesize_evidence
        repo = MockRepo()
        result = synthesize_evidence("need", "nonexistent", repo)
        assert result["entity_type"] == "need"
        assert result["confidence"] == "low"

    def test_operation_evidence(self):
        from agent.delta import synthesize_evidence
        repo = MockRepo()
        now = datetime.now(timezone.utc)
        repo.needs = [MockNeed("n1", title="Water shortage")]
        repo.operations = [
            MockOperation("op1", need_id="n1", name="Water delivery", created_at=now)
        ]
        result = synthesize_evidence("operation", "op1", repo)
        assert result["entity_type"] == "operation"
        assert len(result["evidence_items"]) > 0


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_normalize_text(self):
        from agent.delta import _normalize_text
        assert _normalize_text("  Hello   World  ") == "hello world"
        assert _normalize_text("") == ""
        assert _normalize_text(None) == ""

    def test_temporal_proximity(self):
        from agent.delta import _temporal_proximity
        now = datetime.now(timezone.utc)
        t1 = now.isoformat()
        t2 = (now - timedelta(hours=2)).isoformat()
        t3 = (now - timedelta(hours=8)).isoformat()
        assert _temporal_proximity(t1, t2) is True
        assert _temporal_proximity(t1, t3) is False

    def test_categorize_needs(self):
        from agent.delta import _categorize_needs
        assert _categorize_needs([]) == "general"
        assert _categorize_needs(["water"]) == "water"
        assert _categorize_needs(["medical"]) == "medical"
        assert "supplies" in _categorize_needs(["water", "food"])
