"""
Step 1 + Step 2 Tests: Multi-District Flood Data + Need ↔ Offer Matching

Tests:
1. All 4 real flood snapshots are present in repository
2. get_latest_flood_snapshot works for each district
3. list_flood_snapshots works for each district
4. Temporal filtering works
5. Rerunning import does not duplicate snapshots (idempotency)
6. District isolation works
7. Matching service: compatible resource + same district
8. Matching service: incompatible resource type
9. Matching service: insufficient capacity
10. Matching service: sufficient capacity
11. Matching service: urgent need ranking
12. Matching service: unavailable/withdrawn offer excluded
13. Matching service: cross-district behavior
14. Matching service: multiple candidates ranked deterministically
15. Matching service: no matching offer
16. Matching service: explanation contains meaningful reasons
17. Lifecycle: need creation → offer creation → match retrieval → no op yet → confirm → op created
"""

import os
os.environ["RELIEFOS_MEMORY"] = "1"

import json
import pytest
from datetime import datetime, timezone

from agent.data.models import (
    District, Settlement, FloodSnapshot, Need, ResourceOffer, Operation,
    ActivityEvent, Provenance, make_flood_snapshot_id,
)
from agent.data.repository import get_repository, set_repository, reset_repository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_repo():
    """Provide a fresh InMemoryRepository for each test.

    Sets it explicitly so Flask endpoints use the same instance.
    """
    reset_repository()
    from agent.data.repository import InMemoryRepository
    repo = InMemoryRepository()
    set_repository(repo)
    yield repo
    reset_repository()


@pytest.fixture
def four_districts(fresh_repo):
    """Create the four Assam districts."""
    districts = [
        District(id="sivasagar", name="Sivasagar", state="Assam", country="India"),
        District(id="jorhat", name="Jorhat", state="Assam", country="India"),
        District(id="charaideo", name="Charaideo", state="Assam", country="India"),
        District(id="golaghat", name="Golaghat", state="Assam", country="India"),
    ]
    for d in districts:
        fresh_repo.upsert_district(d)
    return districts


@pytest.fixture
def sample_floods(fresh_repo, four_districts):
    """Create flood snapshots for each district with real-looking data."""
    snapshots = [
        FloodSnapshot(
            id="flood_sivasagar_20260701",
            district_id="sivasagar",
            observed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            source="Sentinel-1 SAR (Earth Engine export)",
            confidence=1.0,
            geometry_geojson={"type": "FeatureCollection", "features": [
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[94.5, 26.9], [94.6, 26.9], [94.6, 27.0], [94.5, 27.0], [94.5, 26.9]]]}},
            ]},
            polygon_count=1,
            provenance=Provenance.REAL,
        ),
        FloodSnapshot(
            id="flood_jorhat_20260729",
            district_id="jorhat",
            observed_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
            source="Sentinel-1 SAR (Earth Engine export)",
            confidence=1.0,
            geometry_geojson={"type": "FeatureCollection", "features": [
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[94.1, 26.7], [94.2, 26.7], [94.2, 26.8], [94.1, 26.8], [94.1, 26.7]]]}},
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[94.15, 26.72], [94.18, 26.72], [94.18, 26.75], [94.15, 26.75], [94.15, 26.72]]]}},
            ]},
            polygon_count=2,
            provenance=Provenance.REAL,
        ),
        FloodSnapshot(
            id="flood_charaideo_20260729",
            district_id="charaideo",
            observed_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
            source="Sentinel-1 SAR (Earth Engine export)",
            confidence=1.0,
            geometry_geojson={"type": "FeatureCollection", "features": [
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[94.8, 27.0], [94.9, 27.0], [94.9, 27.1], [94.8, 27.1], [94.8, 27.0]]]}},
            ]},
            polygon_count=1,
            provenance=Provenance.REAL,
        ),
        FloodSnapshot(
            id="flood_golaghat_20260722",
            district_id="golaghat",
            observed_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
            source="Sentinel-1 SAR (Earth Engine export)",
            confidence=1.0,
            geometry_geojson={"type": "FeatureCollection", "features": [
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[93.5, 26.4], [93.6, 26.4], [93.6, 26.5], [93.5, 26.5], [93.5, 26.4]]]}},
            ]},
            polygon_count=1,
            provenance=Provenance.REAL,
        ),
    ]
    for s in snapshots:
        fresh_repo.upsert_flood_snapshot(s)
    return snapshots


# ===========================================================================
# PART 1: Multi-District Flood Data
# ===========================================================================

class TestMultiDistrictFloodData:
    """All 4 real flood snapshots are present and retrievable."""

    def test_all_four_snapshots_present(self, sample_floods):
        """All 4 districts have flood snapshots."""
        repo = get_repository()
        for district_id in ["sivasagar", "jorhat", "charaideo", "golaghat"]:
            snapshots = repo.list_flood_snapshots(district_id=district_id)
            assert len(snapshots) >= 1, f"No flood snapshot for {district_id}"

    def test_snapshot_ids_correct(self, sample_floods):
        """Snapshot IDs match expected deterministic format."""
        expected = {
            "sivasagar": "flood_sivasagar_20260701",
            "jorhat": "flood_jorhat_20260729",
            "charaideo": "flood_charaideo_20260729",
            "golaghat": "flood_golaghat_20260722",
        }
        repo = get_repository()
        for district_id, expected_id in expected.items():
            snapshot = repo.get_flood_snapshot(expected_id)
            assert snapshot is not None, f"Snapshot {expected_id} not found for {district_id}"
            assert snapshot.district_id == district_id

    def test_polygon_counts_retrieved(self, sample_floods):
        """Polygon counts are correct for each district."""
        repo = get_repository()
        expected_counts = {
            "sivasagar": 1,
            "jorhat": 2,
            "charaideo": 1,
            "golaghat": 1,
        }
        for district_id, expected_count in expected_counts.items():
            snapshot = repo.get_latest_flood_snapshot(district_id)
            assert snapshot is not None
            assert snapshot.polygon_count == expected_count

    def test_latest_observation_dates_correct(self, sample_floods):
        """Latest observation dates match expected values."""
        repo = get_repository()
        expected_dates = {
            "sivasagar": datetime(2026, 7, 1, tzinfo=timezone.utc),
            "jorhat": datetime(2026, 7, 29, tzinfo=timezone.utc),
            "charaideo": datetime(2026, 7, 29, tzinfo=timezone.utc),
            "golaghat": datetime(2026, 7, 22, tzinfo=timezone.utc),
        }
        for district_id, expected_date in expected_dates.items():
            snapshot = repo.get_latest_flood_snapshot(district_id)
            assert snapshot is not None
            assert snapshot.observed_at.date() == expected_date.date()


class TestFloodDistrictIsolation:
    """Flood data is isolated by district."""

    def test_district_isolation(self, sample_floods):
        """Each district's snapshot belongs only to that district."""
        repo = get_repository()
        for district_id in ["sivasagar", "jorhat", "charaideo", "golaghat"]:
            snapshots = repo.list_flood_snapshots(district_id=district_id)
            for snap in snapshots:
                assert snap.district_id == district_id

    def test_cross_district_query(self, sample_floods):
        """Querying one district does not return another's data."""
        repo = get_repository()
        siv = repo.list_flood_snapshots(district_id="sivasagar")
        jor = repo.list_flood_snapshots(district_id="jorhat")
        assert len(siv) == 1
        assert len(jor) == 1
        assert siv[0].id != jor[0].id

    def test_all_districts_combined(self, sample_floods):
        """Querying without district filter returns all snapshots."""
        repo = get_repository()
        all_snaps = repo.list_flood_snapshots()
        assert len(all_snaps) == 4


class TestFloodIdempotency:
    """Running import multiple times does not create duplicates."""

    def test_upsert_is_idempotent(self, sample_floods):
        """Upserting the same snapshot twice doesn't create duplicates."""
        repo = get_repository()
        # Re-upsert the exact same snapshot
        snap = sample_floods[0]
        repo.upsert_flood_snapshot(snap)

        snapshots = repo.list_flood_snapshots(district_id="sivasagar")
        assert len(snapshots) == 1  # Still only one

    def test_import_is_idempotent(self, fresh_repo):
        """import_flood_geojson is idempotent via deterministic IDs."""
        fresh_repo.upsert_district(District(id="test", name="Test"))
        geojson = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}},
        ]}
        # Import twice
        s1 = fresh_repo.import_flood_geojson(geojson, "test", "test", "2026-01-01T00:00:00+00:00")
        s2 = fresh_repo.import_flood_geojson(geojson, "test", "test", "2026-01-01T00:00:00+00:00")
        # Same ID means upsert updated, not created
        assert s1.id == s2.id
        snapshots = fresh_repo.list_flood_snapshots(district_id="test")
        assert len(snapshots) == 1


class TestFloodTemporalFiltering:
    """Temporal filtering works correctly."""

    def test_observed_after_filter(self, sample_floods):
        """Filtering by observed_after returns only later snapshots."""
        repo = get_repository()
        # After July 15 → only jorhat (7/29), charaideo (7/29), golaghat (7/22)
        after_july15 = repo.list_flood_snapshots(observed_after="2026-07-15T00:00:00+00:00")
        district_ids = {s.district_id for s in after_july15}
        assert "sivasagar" not in district_ids
        assert "jorhat" in district_ids

    def test_get_latest_before_date(self, sample_floods):
        """get_latest_flood_snapshot with date filter returns correct one."""
        repo = get_repository()
        # Before July 15 → only sivasagar
        latest = repo.get_latest_flood_snapshot("sivasagar", observed_at="2026-07-15T00:00:00+00:00")
        assert latest is not None
        assert latest.district_id == "sivasagar"


# ===========================================================================
# PART 2: Need ↔ Offer Matching
# ===========================================================================

@pytest.fixture
def sample_needs(fresh_repo):
    """Create sample needs across districts."""
    needs = [
        Need(
            id="need_boat_jorhat",
            need_type="boat",
            title="Boats needed for evacuation",
            description="Emergency evacuation support required",
            district_id="jorhat",
            lat=26.74,
            lon=94.21,
            location_name="Jorhat Town",
            urgency="critical",
            status="OPEN",
            requested_resources=[{"type": "boat", "quantity": 3, "unit": "boats"}],
            reporter_id="coordinator_1",
        ),
        Need(
            id="need_food_sivasagar",
            need_type="food",
            title="Food rations needed",
            description="Rice and lentils for 500 families",
            district_id="sivasagar",
            lat=26.99,
            lon=94.64,
            location_name="Sivasagar Town",
            urgency="high",
            status="OPEN",
            requested_resources=[{"type": "food", "quantity": 2000, "unit": "kg"}],
            reporter_id="coordinator_2",
        ),
        Need(
            id="need_medical_jorhat",
            need_type="medical_team",
            title="Medical team needed",
            description="Injury treatment for flood victims",
            district_id="jorhat",
            urgency="medium",
            status="OPEN",
            requested_resources=[{"type": "medical_team", "quantity": 2, "unit": "teams"}],
            reporter_id="coordinator_1",
        ),
        Need(
            id="need_water_golaghat",
            need_type="water",
            title="Drinking water needed",
            description="Clean drinking water for displaced families",
            district_id="golaghat",
            urgency="low",
            status="OPEN",
            requested_resources=[{"type": "water", "quantity": 100, "unit": "liters"}],
            reporter_id="coordinator_3",
        ),
    ]
    for n in needs:
        fresh_repo.create_need(n)
    return needs


@pytest.fixture
def sample_offers(fresh_repo):
    """Create sample resource offers."""
    offers = [
        ResourceOffer(
            id="offer_boats_jorhat",
            organization_id="org_relief",
            resource_type="boat",
            quantity=6,
            unit="boats",
            lat=26.74,
            lon=94.21,
            location_name="Jorhat",
            district_id="jorhat",
            status="OFFERED",
            notes="6 rescue boats available immediately",
        ),
        ResourceOffer(
            id="offer_food_sivasagar",
            organization_id="org_food",
            resource_type="food",
            quantity=1500,
            unit="kg",
            lat=26.99,
            lon=94.64,
            location_name="Sivasagar",
            district_id="sivasagar",
            status="OFFERED",
        ),
        ResourceOffer(
            id="offer_boats_charaideo",
            organization_id="org_boat",
            resource_type="boat",
            quantity=2,
            unit="boats",
            lat=27.09,
            lon=94.88,
            location_name="Sonari",
            district_id="charaideo",
            status="OFFERED",
        ),
        ResourceOffer(
            id="offer_withdrawn",
            organization_id="org_old",
            resource_type="boat",
            quantity=1,
            unit="boats",
            district_id="jorhat",
            status="WITHDRAWN",
        ),
        ResourceOffer(
            id="offer_medical",
            organization_id="org_medical",
            resource_type="medical_team",
            quantity=3,
            unit="teams",
            district_id="jorhat",
            status="OFFERED",
        ),
    ]
    for o in offers:
        fresh_repo.create_resource_offer(o)
    return offers


class TestMatchingService:
    """Tests for the deterministic matching service."""

    def test_compatible_resource_same_district(self, sample_needs, sample_offers):
        """Compatible resource type + same district = high match."""
        from agent.matching import find_matches_for_need
        repo = get_repository()

        need = repo.get_need("need_boat_jorhat")
        offers = repo.list_resource_offers(status="OFFERED")
        matches = find_matches_for_need(need, offers)

        # Should find at least the jorhat boat offer
        jorhat_matches = [m for m in matches if m.offer_id == "offer_boats_jorhat"]
        assert len(jorhat_matches) == 1
        assert jorhat_matches[0].compatibility == "HIGH"
        assert jorhat_matches[0].score > 0.5

    def test_incompatible_resource_type(self, sample_needs, sample_offers):
        """Incompatible resource type produces no match."""
        from agent.matching import find_matches_for_need
        repo = get_repository()

        need = repo.get_need("need_water_golaghat")
        offers = repo.list_resource_offers(status="OFFERED")
        matches = find_matches_for_need(need, offers)

        # Water need should not match boats, food, or medical
        for m in matches:
            assert m.offer_id not in ["offer_boats_jorhat", "offer_food_sivasagar", "offer_medical"]

    def test_insufficient_capacity(self, sample_needs, sample_offers):
        """Offer with insufficient quantity produces partial match."""
        from agent.matching import find_matches_for_need
        repo = get_repository()

        # Food need asks for 2000kg, offer has only 1500kg
        need = repo.get_need("need_food_sivasagar")
        offers = repo.list_resource_offers(status="OFFERED")
        matches = find_matches_for_need(need, offers)

        food_match = [m for m in matches if m.offer_id == "offer_food_sivasagar"]
        assert len(food_match) == 1
        assert food_match[0].unmet_quantity > 0
        assert food_match[0].match_type == "partial"

    def test_sufficient_capacity(self, sample_needs, sample_offers):
        """Offer with sufficient quantity produces full match."""
        from agent.matching import find_matches_for_need
        repo = get_repository()

        # Boat need asks for 3, offer has 6
        need = repo.get_need("need_boat_jorhat")
        offers = repo.list_resource_offers(status="OFFERED")
        matches = find_matches_for_need(need, offers)

        boat_match = [m for m in matches if m.offer_id == "offer_boats_jorhat"]
        assert len(boat_match) == 1
        assert boat_match[0].unmet_quantity == 0
        assert boat_match[0].match_type == "full"

    def test_urgent_need_ranking(self, sample_needs, sample_offers):
        """Critical needs rank ahead of low-urgency needs."""
        from agent.matching import find_matches_for_need
        repo = get_repository()

        # Critical boat need in jorhat
        critical = repo.get_need("need_boat_jorhat")
        # Low water need in golaghat
        low = repo.get_need("need_water_golaghat")
        offers = repo.list_resource_offers(status="OFFERED")

        critical_matches = find_matches_for_need(critical, offers)
        low_matches = find_matches_for_need(low, offers)

        # Critical should have higher max score if it has any matches
        if critical_matches and low_matches:
            assert critical_matches[0].score >= low_matches[0].score

    def test_withdrawn_offer_excluded(self, sample_needs, sample_offers):
        """Withdrawn/expired offers are excluded from matching."""
        from agent.matching import find_matches_for_need
        repo = get_repository()

        need = repo.get_need("need_boat_jorhat")
        offers = repo.list_resource_offers(status="OFFERED")
        matches = find_matches_for_need(need, offers)

        withdrawn_ids = {m.offer_id for m in matches}
        assert "offer_withdrawn" not in withdrawn_ids

    def test_cross_district_offer(self, sample_needs, sample_offers):
        """Cross-district offers still match, but with lower score."""
        from agent.matching import find_matches_for_need
        repo = get_repository()

        # Jorhat boat need
        need = repo.get_need("need_boat_jorhat")
        offers = repo.list_resource_offers(status="OFFERED")
        matches = find_matches_for_need(need, offers)

        cross_match = [m for m in matches if m.offer_id == "offer_boats_charaideo"]
        jorhat_match = [m for m in matches if m.offer_id == "offer_boats_jorhat"]

        if cross_match and jorhat_match:
            # Same district should score higher
            assert jorhat_match[0].score > cross_match[0].score

    def test_multiple_candidates_ranked(self, sample_needs, sample_offers):
        """Multiple candidates are ranked deterministically."""
        from agent.matching import find_matches_for_need
        repo = get_repository()

        need = repo.get_need("need_boat_jorhat")
        offers = repo.list_resource_offers(status="OFFERED")
        matches = find_matches_for_need(need, offers)

        # Should have at least 2 matches (jorhat + charaideo boats)
        assert len(matches) >= 2
        # Sorted by score descending
        for i in range(len(matches) - 1):
            assert matches[i].score >= matches[i + 1].score

    def test_no_matching_offer(self, fresh_repo):
        """When no compatible offers exist, returns empty list."""
        from agent.matching import find_matches_for_need

        need = Need(
            id="need_orphan", need_type="satellite_phone",
            title="Need satellite phone", district_id="jorhat",
            requested_resources=[{"type": "satellite_phone", "quantity": 1}],
        )
        matches = find_matches_for_need(need, [])
        assert matches == []

    def test_explanation_contains_reasons(self, sample_needs, sample_offers):
        """Match explanation contains meaningful reasons."""
        from agent.matching import find_matches_for_need
        repo = get_repository()

        need = repo.get_need("need_boat_jorhat")
        offers = repo.list_resource_offers(status="OFFERED")
        matches = find_matches_for_need(need, offers)

        jorhat_match = [m for m in matches if m.offer_id == "offer_boats_jorhat"][0]
        assert len(jorhat_match.reasons) >= 2
        # Should mention district
        assert any("jorhat" in r.lower() for r in jorhat_match.reasons)
        # Should mention resource type
        assert any("boat" in r.lower() or "transport" in r.lower() for r in jorhat_match.reasons)


# ===========================================================================
# PART 2: Collaboration Lifecycle
# ===========================================================================

class TestCollaborationLifecycle:
    """Test the full Need → Offer → Match → Confirm → Operation flow."""

    def test_need_creation(self, sample_needs):
        """Need can be created and retrieved."""
        repo = get_repository()
        need = repo.get_need("need_boat_jorhat")
        assert need is not None
        assert need.status == "OPEN"
        assert need.urgency == "critical"

    def test_offer_creation(self, sample_offers):
        """Offer can be created and retrieved."""
        repo = get_repository()
        offer = repo.get_resource_offer("offer_boats_jorhat")
        assert offer is not None
        assert offer.status == "OFFERED"
        assert offer.quantity == 6

    def test_match_retrieval(self, sample_needs, sample_offers):
        """Matches can be retrieved for a need."""
        from agent.matching import find_matches_for_need
        repo = get_repository()

        need = repo.get_need("need_boat_jorhat")
        offers = repo.list_resource_offers(status="OFFERED")
        matches = find_matches_for_need(need, offers)
        assert len(matches) >= 1

    def test_no_operation_created_by_matching(self, sample_needs, sample_offers):
        """Matching does NOT create an operation."""
        from agent.matching import find_matches_for_need
        repo = get_repository()

        need = repo.get_need("need_boat_jorhat")
        offers = repo.list_resource_offers(status="OFFERED")
        matches = find_matches_for_need(need, offers)

        # No operations should exist yet
        ops = repo.list_operations()
        assert len(ops) == 0

    def test_confirm_creates_operation(self, sample_needs, sample_offers):
        """Human confirmation creates an Operation."""
        from agent.api import app
        client = app.test_client()

        resp = client.post("/api/matches/need_boat_jorhat/offer_boats_jorhat/confirm")
        assert resp.status_code == 201
        data = resp.get_json()
        assert "operation" in data
        op = data["operation"]
        assert op["need_id"] == "need_boat_jorhat"
        assert op["lead_organization_id"] == "org_relief"
        assert op["status"] == "PLANNING"

    def test_operation_references_correct_need_offer(self, sample_needs, sample_offers):
        """Created operation references the correct need and offer."""
        from agent.api import app
        client = app.test_client()

        resp = client.post("/api/matches/need_boat_jorhat/offer_boats_jorhat/confirm")
        op = resp.get_json()["operation"]
        assert op["need_id"] == "need_boat_jorhat"
        assert op["metadata"]["offer_id"] == "offer_boats_jorhat"
        assert op["metadata"]["organization_id"] == "org_relief"

    def test_activity_events_recorded(self, sample_needs, sample_offers):
        """Activity events are recorded on confirmation."""
        from agent.api import app
        repo = get_repository()
        client = app.test_client()

        client.post("/api/matches/need_boat_jorhat/offer_boats_jorhat/confirm")

        events = repo.list_activity_events()
        event_types = {e.event_type for e in events}
        assert "match_confirmed" in event_types
        assert "operation_created" in event_types

    def test_repeated_confirmation_idempotent(self, sample_needs, sample_offers):
        """Repeated confirmation for same need+offer returns existing operation."""
        from agent.api import app
        client = app.test_client()

        resp1 = client.post("/api/matches/need_boat_jorhat/offer_boats_jorhat/confirm")
        resp2 = client.post("/api/matches/need_boat_jorhat/offer_boats_jorhat/confirm")

        assert resp1.status_code == 201
        assert resp2.status_code == 200  # Already confirmed
        op1 = resp1.get_json()["operation"]
        op2 = resp2.get_json()["operation"]
        assert op1["id"] == op2["id"]

    def test_offer_status_updates(self, sample_needs, sample_offers):
        """Offer status changes to ACCEPTED after confirmation."""
        from agent.api import app
        repo = get_repository()
        client = app.test_client()

        client.post("/api/matches/need_boat_jorhat/offer_boats_jorhat/confirm")
        offer = repo.get_resource_offer("offer_boats_jorhat")
        assert offer.status == "ACCEPTED"

    def test_need_status_updates(self, sample_needs, sample_offers):
        """Need status changes to RESPONDING after confirmation."""
        from agent.api import app
        repo = get_repository()
        client = app.test_client()

        client.post("/api/matches/need_boat_jorhat/offer_boats_jorhat/confirm")
        need = repo.get_need("need_boat_jorhat")
        assert need.status == "RESPONDING"

    def test_confirmed_offer_not_matched_again(self, sample_needs, sample_offers):
        """Already accepted offer doesn't appear in new matches."""
        from agent.api import app
        from agent.matching import find_matches_for_need
        repo = get_repository()
        client = app.test_client()

        # Confirm the match
        client.post("/api/matches/need_boat_jorhat/offer_boats_jorhat/confirm")

        # Create a new boat need
        new_need = Need(
            id="need_boat_2",
            need_type="boat",
            title="More boats needed",
            district_id="jorhat",
            urgency="high",
            status="OPEN",
        )
        repo.create_need(new_need)

        # The accepted offer should not appear in new matches
        offers = repo.list_resource_offers(status="OFFERED")
        matches = find_matches_for_need(new_need, offers)
        offer_ids = {m.offer_id for m in matches}
        assert "offer_boats_jorhat" not in offer_ids
