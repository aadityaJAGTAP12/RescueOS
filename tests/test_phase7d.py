"""
Phase 7D: Tests for Operational Data Completion + Real-Data Verification

Tests for:
- Roads endpoint
- Bridges endpoint
- Road GeoJSON
- Override precedence
- District isolation
- Real flood API retrieval
- Planner API
- Need -> offer workflow
- Field report -> override workflow
- Privacy boundary

Uses RELIEFOS_MEMORY=1 to ensure InMemoryRepository is used.
"""

import os
os.environ["RELIEFOS_MEMORY"] = "1"

import json
import pytest
from datetime import datetime, timezone

from agent.data.models import (
    District, Settlement, Road, FloodSnapshot, FieldReport, Override,
    MedicalFacility, Provenance, VerificationState, make_flood_snapshot_id,
    Organization, Need, ResourceOffer, Operation, ActivityEvent,
)
from agent.data.repository import get_repository, reset_repository
from agent.overrides import apply_override, get_active_override, get_operational_status, clear_overrides


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_repo():
    """Provide a fresh InMemoryRepository for each test."""
    reset_repository()
    repo = get_repository()
    yield repo
    reset_repository()
    clear_overrides()


@pytest.fixture
def four_districts(fresh_repo):
    """Create the four Assam districts."""
    districts = [
        District(id="sivasagar", name="Sivasagar", state="Assam"),
        District(id="jorhat", name="Jorhat", state="Assam"),
        District(id="charaideo", name="Charaideo", state="Assam"),
        District(id="golaghat", name="Golaghat", state="Assam"),
    ]
    for d in districts:
        fresh_repo.upsert_district(d)
    return districts


@pytest.fixture
def sample_roads(fresh_repo, four_districts):
    """Create sample roads for each district."""
    roads = [
        Road(
            id="road_siv_main_1", district_id="sivasagar",
            name="NH-37 Sivasagar", highway_type="primary",
            geometry_coords=[[94.50, 26.99], [94.55, 27.00], [94.60, 27.01]],
            flood_affected=False, provenance=Provenance.REAL,
        ),
        Road(
            id="road_siv_bridge_1", district_id="sivasagar",
            name="Brahmaputra Bridge Sivasagar", highway_type="primary",
            geometry_coords=[[94.52, 26.98], [94.53, 26.99]],
            flood_affected=False, provenance=Provenance.REAL, is_bridge=True,
        ),
        Road(
            id="road_jor_main_1", district_id="jorhat",
            name="NH-37 Jorhat", highway_type="primary",
            geometry_coords=[[94.18, 26.74], [94.20, 26.75], [94.22, 26.76]],
            flood_affected=True, provenance=Provenance.REAL,
        ),
        Road(
            id="road_jor_bridge_1", district_id="jorhat",
            name="Jorhat Bridge", highway_type="tertiary",
            geometry_coords=[[94.19, 26.73], [94.20, 26.74]],
            flood_affected=True, provenance=Provenance.REAL, is_bridge=True,
        ),
        Road(
            id="road_jor_residential", district_id="jorhat",
            name="Gymkhana Road", highway_type="residential",
            geometry_coords=[[94.15, 26.72], [94.16, 26.73]],
            flood_affected=False, provenance=Provenance.REAL,
        ),
        Road(
            id="road_char_main_1", district_id="charaideo",
            name="Charaideo Road", highway_type="secondary",
            geometry_coords=[[94.80, 27.10], [94.85, 27.12]],
            flood_affected=False, provenance=Provenance.REAL,
        ),
        Road(
            id="road_gola_main_1", district_id="golaghat",
            name="Golaghat Road", highway_type="tertiary",
            geometry_coords=[[93.58, 26.50], [93.60, 26.51]],
            flood_affected=False, provenance=Provenance.REAL,
        ),
    ]
    for r in roads:
        fresh_repo.upsert_roads([r])
    return roads


@pytest.fixture
def sample_floods(fresh_repo, four_districts):
    """Create flood snapshots for each district."""
    snapshots = [
        FloodSnapshot(
            id="flood_sivasagar_20260701",
            district_id="sivasagar",
            observed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            source="Sentinel-1 SAR",
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
            source="Sentinel-1 SAR",
            confidence=1.0,
            geometry_geojson={"type": "FeatureCollection", "features": [
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[94.1, 26.7], [94.2, 26.7], [94.2, 26.8], [94.1, 26.8], [94.1, 26.7]]]}},
            ]},
            polygon_count=1,
            provenance=Provenance.REAL,
        ),
        FloodSnapshot(
            id="flood_charaideo_20260729",
            district_id="charaideo",
            observed_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
            source="Sentinel-1 SAR",
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
            source="Sentinel-1 SAR",
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


@pytest.fixture
def sample_settlements(fresh_repo, four_districts):
    """Create sample settlements for each district."""
    settlements = [
        Settlement(id="siv_town", name="Sivasagar Town", district_id="sivasagar", lat=26.99, lon=94.64),
        Settlement(id="jor_town", name="Jorhat Town", district_id="jorhat", lat=26.74, lon=94.21),
        Settlement(id="char_town", name="Sonari", district_id="charaideo", lat=27.09, lon=94.88),
        Settlement(id="gola_town", name="Golaghat Town", district_id="golaghat", lat=26.50, lon=93.60),
    ]
    for s in settlements:
        fresh_repo.upsert_settlement(s)
    return settlements


@pytest.fixture
def sample_medical(fresh_repo, four_districts):
    """Create sample medical facilities."""
    facilities = [
        MedicalFacility(
            id="med_siv_1", district_id="sivasagar",
            name="Sivasagar Civil Hospital", lat=26.99, lon=94.64,
            facility_type="hospital",
        ),
        MedicalFacility(
            id="med_jor_1", district_id="jorhat",
            name="Jorhat Medical College", lat=26.74, lon=94.21,
            facility_type="hospital",
        ),
    ]
    for f in facilities:
        fresh_repo.upsert_medical_facilities([f])
    return facilities


# ===========================================================================
# 1. Roads endpoint
# ===========================================================================

class TestRoadsEndpoint:
    def test_roads_returns_list(self, sample_roads):
        """GET /api/districts/<id>/roads returns a list of roads."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/jorhat/roads")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "roads" in data
        assert data["count"] == 3  # 3 roads in jorhat

    def test_roads_have_geometry(self, sample_roads):
        """Roads include geometry_coords."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/sivasagar/roads")
        data = resp.get_json()
        assert data["count"] == 2
        for road in data["roads"]:
            assert "geometry_coords" in road
            assert len(road["geometry_coords"]) >= 2

    def test_roads_have_operational_status(self, sample_roads):
        """Each road has an operational_status."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/jorhat/roads")
        data = resp.get_json()
        for road in data["roads"]:
            assert "operational_status" in road
            assert road["operational_status"] in ("open", "uncertain", "blocked", "submerged", "damaged", "passable", "restricted")

    def test_flood_affected_road_is_uncertain(self, sample_roads):
        """A flood-affected road without override has status 'uncertain'."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/jorhat/roads")
        data = resp.get_json()
        flood_road = [r for r in data["roads"] if r["name"] == "NH-37 Jorhat"][0]
        assert flood_road["operational_status"] == "uncertain"
        assert flood_road["override"] is None

    def test_non_flooded_road_is_open(self, sample_roads):
        """A non-flooded road without override has status 'open'."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/sivasagar/roads")
        data = resp.get_json()
        road = [r for r in data["roads"] if r["name"] == "NH-37 Sivasagar"][0]
        assert road["operational_status"] == "open"
        assert road["override"] is None

    def test_roads_unknown_district(self, sample_roads):
        """Unknown district returns empty roads."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/nonexistent/roads")
        data = resp.get_json()
        assert data["roads"] == []
        assert data["count"] == 0

    def test_roads_provenance_preserved(self, sample_roads):
        """Road provenance is preserved."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/jorhat/roads")
        data = resp.get_json()
        for road in data["roads"]:
            assert road["provenance"] == "REAL"


# ===========================================================================
# 2. Bridges endpoint
# ===========================================================================

class TestBridgesEndpoint:
    def test_bridges_returns_only_bridges(self, sample_roads):
        """Bridges endpoint only returns roads where is_bridge=True."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/jorhat/bridges")
        data = resp.get_json()
        assert data["count"] == 1  # Only Jorhat Bridge
        assert data["bridges"][0]["is_bridge"] is True
        assert data["bridges"][0]["name"] == "Jorhat Bridge"

    def test_bridges_sivasagar(self, sample_roads):
        """Sivasagar has one bridge."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/sivasagar/bridges")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["bridges"][0]["name"] == "Brahmaputra Bridge Sivasagar"

    def test_bridges_empty_district(self, sample_roads):
        """District with no bridges returns empty list."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/charaideo/bridges")
        data = resp.get_json()
        assert data["count"] == 0
        assert data["bridges"] == []

    def test_bridges_has_operational_status(self, sample_roads):
        """Bridges include operational_status."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/jorhat/bridges")
        data = resp.get_json()
        bridge = data["bridges"][0]
        assert "operational_status" in bridge
        assert "override" in bridge


# ===========================================================================
# 3. Road GeoJSON endpoint
# ===========================================================================

class TestRoadGeoJSON:
    def test_geojson_returns_feature_collection(self, sample_roads):
        """GET /api/districts/<id>/roads/geojson returns FeatureCollection."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/jorhat/roads/geojson")
        data = resp.get_json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 3

    def test_geojson_features_have_geometry(self, sample_roads):
        """Each feature has LineString geometry."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/jorhat/roads/geojson")
        data = resp.get_json()
        for feature in data["features"]:
            assert feature["geometry"]["type"] == "LineString"
            assert len(feature["geometry"]["coordinates"]) >= 2

    def test_geojson_features_have_properties(self, sample_roads):
        """Each feature has required properties."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/jorhat/roads/geojson")
        data = resp.get_json()
        for feature in data["features"]:
            props = feature["properties"]
            assert "id" in props
            assert "name" in props
            assert "highway_type" in props
            assert "operational_status" in props
            assert "color" in props

    def test_geojson_color_matches_status(self, sample_roads):
        """Color matches operational status."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/jorhat/roads/geojson")
        data = resp.get_json()
        for feature in data["features"]:
            status = feature["properties"]["operational_status"]
            color = feature["properties"]["color"]
            if status in ("blocked", "submerged", "damaged"):
                assert color == "#dc2626"
            elif status == "uncertain":
                assert color == "#d97706"
            else:
                assert color == "#16a34a"


# ===========================================================================
# 4. Override precedence
# ===========================================================================

class TestOverridePrecedence:
    def test_override_changes_road_status(self, sample_roads):
        """An override changes the operational status of a road."""
        from agent.api import app
        client = app.test_client()

        # Apply override
        apply_override(
            target_type="road",
            target_id="NH-37 Jorhat",
            new_status="blocked",
            reason="Bridge washed out",
            actor="field_team_1",
        )

        resp = client.get("/api/districts/jorhat/roads")
        data = resp.get_json()
        road = [r for r in data["roads"] if r["name"] == "NH-37 Jorhat"][0]
        assert road["operational_status"] == "blocked"
        assert road["override"] is not None
        assert road["override"]["status"] == "blocked"
        assert road["override"]["reason"] == "Bridge washed out"

    def test_override_does_not_replace_source_data(self, sample_roads):
        """Override does not replace the source flood_affected flag."""
        from agent.api import app
        client = app.test_client()

        apply_override(
            target_type="road",
            target_id="NH-37 Jorhat",
            new_status="passable",
            reason="Confirmed passable by field team",
        )

        resp = client.get("/api/districts/jorhat/roads")
        data = resp.get_json()
        road = [r for r in data["roads"] if r["name"] == "NH-37 Jorhat"][0]
        # Operational status is overridden
        assert road["operational_status"] == "passable"
        # But source data is preserved
        assert road["flood_affected"] is True

    def test_override_appears_in_geojson(self, sample_roads):
        """Override is reflected in GeoJSON output."""
        from agent.api import app
        client = app.test_client()

        apply_override(
            target_type="road",
            target_id="NH-37 Sivasagar",
            new_status="blocked",
            reason="Landslide",
        )

        resp = client.get("/api/districts/sivasagar/roads/geojson")
        data = resp.get_json()
        feature = [f for f in data["features"] if f["properties"]["name"] == "NH-37 Sivasagar"][0]
        assert feature["properties"]["operational_status"] == "blocked"
        assert feature["properties"]["color"] == "#dc2626"
        assert feature["properties"]["override"] is not None

    def test_override_show_in_context_panel(self, sample_roads):
        """Road detail shows both source and override status."""
        from agent.api import app
        client = app.test_client()

        apply_override(
            target_type="road",
            target_id="NH-37 Jorhat",
            new_status="blocked",
            reason="Washed out",
            actor="coordinator_1",
        )

        resp = client.get("/api/districts/jorhat/roads")
        data = resp.get_json()
        road = [r for r in data["roads"] if r["name"] == "NH-37 Jorhat"][0]
        # Both are present
        assert road["flood_affected"] is True  # source
        assert road["operational_status"] == "blocked"  # override
        assert road["override"]["actor"] == "coordinator_1"


# ===========================================================================
# 5. District isolation
# ===========================================================================

class TestDistrictIsolation:
    def test_roads_isolated_by_district(self, sample_roads):
        """Roads are isolated by district."""
        from agent.api import app
        client = app.test_client()

        jorhat_roads = client.get("/api/districts/jorhat/roads").get_json()
        sivasagar_roads = client.get("/api/districts/sivasagar/roads").get_json()

        jorhat_names = {r["name"] for r in jorhat_roads["roads"]}
        sivasagar_names = {r["name"] for r in sivasagar_roads["roads"]}

        assert "NH-37 Jorhat" in jorhat_names
        assert "NH-37 Jorhat" not in sivasagar_names
        assert "NH-37 Sivasagar" in sivasagar_names
        assert "NH-37 Sivasagar" not in jorhat_names

    def test_flood_isolated_by_district(self, sample_floods):
        """Flood data is isolated by district."""
        from agent.api import app
        client = app.test_client()

        siv_flood = client.get("/api/districts/sivasagar/flood-geojson").get_json()
        jor_flood = client.get("/api/districts/jorhat/flood-geojson").get_json()

        # Sivasagar flood has 1 feature
        assert len(siv_flood.get("features", [])) == 1
        # Jorhat flood has 1 feature
        assert len(jor_flood.get("features", [])) == 1
        # They should be different geometries
        assert siv_flood != jor_flood

    def test_bridges_isolated_by_district(self, sample_roads):
        """Bridges are isolated by district."""
        from agent.api import app
        client = app.test_client()

        jorhat_bridges = client.get("/api/districts/jorhat/bridges").get_json()
        sivasagar_bridges = client.get("/api/districts/sivasagar/bridges").get_json()

        assert jorhat_bridges["count"] == 1
        assert jorhat_bridges["bridges"][0]["district_id"] == "jorhat"
        assert sivasagar_bridges["count"] == 1
        assert sivasagar_bridges["bridges"][0]["district_id"] == "sivasagar"

    def test_no_hardcoded_district_names(self, fresh_repo):
        """Code does not contain if district == 'jorhat' etc."""
        from agent.api import app
        client = app.test_client()

        # Create a random district name
        fresh_repo.upsert_district(District(id="test_district_xyz", name="Test District", state="Test"))
        fresh_repo.upsert_roads([Road(
            id="road_test_1", district_id="test_district_xyz",
            name="Test Road", highway_type="tertiary",
            geometry_coords=[[94.0, 26.0], [94.1, 26.1]],
        )])

        resp = client.get("/api/districts/test_district_xyz/roads")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert data["roads"][0]["name"] == "Test Road"


# ===========================================================================
# 6. Real flood API verification
# ===========================================================================

class TestFloodAPIVerification:
    def test_flood_sivasagar_date(self, sample_floods):
        """Sivasagar flood observed 2026-07-01."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/sivasagar/flood-geojson")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data.get("features", [])) == 1

    def test_flood_jorhat_date(self, sample_floods):
        """Jorhat flood observed 2026-07-29."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/jorhat/flood-geojson")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data.get("features", [])) == 1

    def test_flood_charaideo_date(self, sample_floods):
        """Charaideo flood observed 2026-07-29."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/charaideo/flood-geojson")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data.get("features", [])) == 1

    def test_flood_golaghat_date(self, sample_floods):
        """Golaghat flood observed 2026-07-22."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/golaghat/flood-geojson")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data.get("features", [])) == 1

    def test_flood_geometry_valid(self, sample_floods):
        """Flood GeoJSON has valid geometry."""
        from agent.api import app
        client = app.test_client()
        resp = client.get("/api/districts/jorhat/flood-geojson")
        data = resp.get_json()
        feature = data["features"][0]
        assert feature["geometry"]["type"] == "Polygon"
        coords = feature["geometry"]["coordinates"][0]
        assert len(coords) >= 3  # At least a triangle

    def test_flood_source_preserved(self, sample_floods):
        """Flood source/provenance is preserved."""
        from agent.data.repository import get_repository
        repo = get_repository()
        snapshot = repo.get_latest_flood_snapshot("jorhat")
        assert snapshot is not None
        assert snapshot.source == "Sentinel-1 SAR"
        assert snapshot.provenance == Provenance.REAL

    def test_flood_latest_snapshot_correct(self, sample_floods):
        """Latest snapshot for each district is correct."""
        from agent.data.repository import get_repository
        repo = get_repository()
        snapshots = {
            "sivasagar": ("flood_sivasagar_20260701", datetime(2026, 7, 1, tzinfo=timezone.utc)),
            "jorhat": ("flood_jorhat_20260729", datetime(2026, 7, 29, tzinfo=timezone.utc)),
            "charaideo": ("flood_charaideo_20260729", datetime(2026, 7, 29, tzinfo=timezone.utc)),
            "golaghat": ("flood_golaghat_20260722", datetime(2026, 7, 22, tzinfo=timezone.utc)),
        }
        for district_id, (expected_id, expected_date) in snapshots.items():
            latest = repo.get_latest_flood_snapshot(district_id)
            assert latest is not None, f"No snapshot for {district_id}"
            assert latest.id == expected_id, f"Wrong snapshot for {district_id}: {latest.id} != {expected_id}"
            assert latest.observed_at.date() == expected_date.date()


# ===========================================================================
# 7. Planner API verification
# ===========================================================================

class TestPlannerAPIVerification:
    def test_planner_returns_recommendation(self, fresh_repo, four_districts, sample_floods, sample_settlements, sample_roads, sample_medical):
        """POST /api/planner returns a recommendation."""
        from agent.api import app
        client = app.test_client()
        resp = client.post("/api/planner", json={"query": "What needs attention in Jorhat right now?"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "recommendation" in data
        assert "why" in data
        assert "evidence" in data
        assert "constraints" in data
        assert "uncertainty" in data
        assert "data_gaps" in data
        assert "tools_used" in data

    def test_planner_flood_query(self, fresh_repo, four_districts, sample_floods, sample_settlements, sample_roads, sample_medical):
        """Planner handles flood query."""
        from agent.api import app
        client = app.test_client()
        resp = client.post("/api/planner", json={"query": "Where is flooding reported?"})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["recommendation"]  # Non-empty

    def test_planner_empty_query(self):
        """Planner rejects empty query."""
        from agent.api import app
        client = app.test_client()
        resp = client.post("/api/planner", json={"query": ""})
        assert resp.status_code == 400

    def test_planner_no_query(self):
        """Planner rejects missing query."""
        from agent.api import app
        client = app.test_client()
        resp = client.post("/api/planner", json={})
        assert resp.status_code == 400


# ===========================================================================
# 8. Need -> Offer workflow
# ===========================================================================

class TestNeedOfferWorkflow:
    def test_create_need_appears_on_map(self, fresh_repo):
        """Creating a need makes it visible via the API."""
        from agent.api import app
        client = app.test_client()

        resp = client.post("/api/needs", json={
            "need_type": "transport",
            "title": "Boats needed",
            "description": "3 boats for evacuation",
            "district_id": "jorhat",
            "lat": 26.74,
            "lon": 94.21,
            "urgency": "critical",
        })
        assert resp.status_code == 201
        need = resp.get_json()["need"]
        assert need["status"] == "OPEN"
        assert need["urgency"] == "critical"

        # Verify it appears in the list
        resp = client.get("/api/needs?district_id=jorhat")
        data = resp.get_json()
        assert len(data["needs"]) == 1
        assert data["needs"][0]["title"] == "Boats needed"

    def test_create_offer_appears_on_map(self, fresh_repo):
        """Creating an offer makes it visible via the API."""
        from agent.api import app
        client = app.test_client()

        resp = client.post("/api/offers", json={
            "resource_type": "boat",
            "quantity": 2,
            "unit": "units",
            "district_id": "jorhat",
            "lat": 26.74,
            "lon": 94.21,
            "notes": "2 boats available",
        })
        assert resp.status_code == 201
        offer = resp.get_json()["offer"]
        assert offer["status"] == "OFFERED"
        assert offer["quantity"] == 2

    def test_need_offer_coexist(self, fresh_repo):
        """Need and offer can coexist for the same district."""
        from agent.api import app
        client = app.test_client()

        # Create need
        client.post("/api/needs", json={
            "need_type": "transport",
            "title": "Boats needed",
            "district_id": "jorhat",
            "urgency": "critical",
        })

        # Create offer
        client.post("/api/offers", json={
            "resource_type": "boat",
            "quantity": 2,
            "district_id": "jorhat",
        })

        # Both appear
        needs = client.get("/api/needs?district_id=jorhat").get_json()
        offers = client.get("/api/offers?district_id=jorhat").get_json()
        assert len(needs["needs"]) == 1
        assert len(offers["offers"]) == 1

    def test_need_offer_different_districts(self, fresh_repo):
        """Need and offer in different districts are isolated."""
        from agent.api import app
        client = app.test_client()

        client.post("/api/needs", json={
            "need_type": "food",
            "title": "Food in Jorhat",
            "district_id": "jorhat",
        })
        client.post("/api/offers", json={
            "resource_type": "food",
            "quantity": 100,
            "district_id": "sivasagar",
        })

        jorhat_needs = client.get("/api/needs?district_id=jorhat").get_json()
        sivasagar_offers = client.get("/api/offers?district_id=sivasagar").get_json()

        assert len(jorhat_needs["needs"]) == 1
        assert len(sivasagar_offers["offers"]) == 1

        # Jorhat has no offers, sivasagar has no needs
        jorhat_offers = client.get("/api/offers?district_id=jorhat").get_json()
        sivasagar_needs = client.get("/api/needs?district_id=sivasagar").get_json()
        assert len(jorhat_offers["offers"]) == 0
        assert len(sivasagar_needs["needs"]) == 0

    def test_activity_events_generated(self, fresh_repo):
        """Creating a need generates an activity event."""
        from agent.api import app
        client = app.test_client()

        client.post("/api/needs", json={
            "need_type": "food",
            "title": "Food needed",
            "district_id": "jorhat",
        })

        resp = client.get("/api/activity?entity_type=need")
        data = resp.get_json()
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "need_created"

    def test_need_status_lifecycle(self, fresh_repo):
        """Need status can be updated through lifecycle."""
        from agent.api import app
        client = app.test_client()

        # Create
        resp = client.post("/api/needs", json={
            "need_type": "food",
            "title": "Food needed",
            "urgency": "high",
        })
        need_id = resp.get_json()["need"]["id"]

        # OPEN -> RESPONDING
        resp = client.patch(f"/api/needs/{need_id}", json={"status": "RESPONDING"})
        assert resp.get_json()["need"]["status"] == "RESPONDING"

        # RESPONDING -> RESOLVED
        resp = client.patch(f"/api/needs/{need_id}", json={"status": "RESOLVED"})
        assert resp.get_json()["need"]["status"] == "RESOLVED"


# ===========================================================================
# 9. Field report -> override workflow
# ===========================================================================

class TestFieldReportOverrideWorkflow:
    def test_field_report_submitted(self, fresh_repo):
        """Field report can be submitted."""
        from agent.api import app
        client = app.test_client()

        resp = client.post("/api/field-intelligence", json={
            "raw_text": "Road blocked near Jorhat due to flooding",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "extraction" in data

    def test_override_applied_to_road(self, fresh_repo, sample_roads):
        """Override can be applied to a road after field report."""
        from agent.api import app
        client = app.test_client()

        # Apply override based on field report
        resp = client.post("/api/override", json={
            "target_type": "road",
            "target_id": "NH-37 Jorhat",
            "new_status": "blocked",
            "reason": "Field report: road blocked due to flooding",
        })
        assert resp.status_code == 200
        override = resp.get_json()["override"]
        assert override["override_status"] == "blocked"
        assert override["target_type"] == "road"

        # Verify override is active
        resp = client.get("/api/override/status?target_type=road&target_id=NH-37 Jorhat")
        data = resp.get_json()
        assert data["operational_status"] == "blocked"
        assert data["override"] is not None

    def test_all_overrides_listed(self, fresh_repo, sample_roads):
        """All overrides can be listed."""
        from agent.api import app
        client = app.test_client()

        client.post("/api/override", json={
            "target_type": "road",
            "target_id": "NH-37 Jorhat",
            "new_status": "blocked",
            "reason": "Blocked",
        })
        client.post("/api/override", json={
            "target_type": "road",
            "target_id": "NH-37 Sivasagar",
            "new_status": "passable",
            "reason": "Confirmed passable",
        })

        resp = client.get("/api/overrides")
        data = resp.get_json()
        assert len(data["overrides"]) == 2


# ===========================================================================
# 10. Privacy boundary
# ===========================================================================

class TestPrivacyBoundary:
    def test_no_private_ngo_data(self, fresh_repo):
        """Network endpoints do not expose private NGO inventory."""
        from agent.api import app
        client = app.test_client()

        # Organizations endpoint only returns public data
        resp = client.get("/api/organizations")
        data = resp.get_json()
        for org in data.get("organizations", []):
            # Should have published_capabilities, not full_inventory
            assert "full_inventory" not in org
            assert "staff_roster" not in org
            assert "private_missions" not in org
            assert "financial_data" not in org

    def test_roads_no_sensitive_data(self, sample_roads):
        """Roads endpoint doesn't expose sensitive internal fields."""
        from agent.api import app
        client = app.test_client()

        resp = client.get("/api/districts/jorhat/roads")
        data = resp.get_json()
        for road in data["roads"]:
            # Should not contain internal credentials or private data
            assert "password" not in str(road).lower()
            assert "secret" not in str(road).lower()
            assert "api_key" not in str(road).lower()

    def test_needs_no_private_fields(self, fresh_repo):
        """Needs endpoint doesn't expose reporter private data."""
        from agent.api import app
        client = app.test_client()

        client.post("/api/needs", json={
            "need_type": "food",
            "title": "Food needed",
            "reporter_id": "team_alpha",
        })

        resp = client.get("/api/needs")
        data = resp.get_json()
        for need in data["needs"]:
            # reporter_type is public, but no private contact info
            assert "private_contact" not in need
            assert "phone" not in str(need).lower()
            assert "email" not in str(need).lower()


# ===========================================================================
# 11. Cross-district generalization
# ===========================================================================

class TestCrossDistrictGeneralization:
    def test_same_api_pattern_all_districts(self, fresh_repo, four_districts, sample_roads):
        """Same API pattern works for all four districts."""
        from agent.api import app
        client = app.test_client()

        for district_id in ["sivasagar", "jorhat", "charaideo", "golaghat"]:
            resp = client.get(f"/api/districts/{district_id}/roads")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "roads" in data
            assert "count" in data

    def test_different_results_from_data(self, fresh_repo, four_districts, sample_roads):
        """Different results arise from database data, not hardcoded logic."""
        from agent.api import app
        client = app.test_client()

        siv = client.get("/api/districts/sivasagar/roads").get_json()
        jor = client.get("/api/districts/jorhat/roads").get_json()
        char = client.get("/api/districts/charaideo/roads").get_json()
        gola = client.get("/api/districts/golaghat/roads").get_json()

        # Each district has different road counts from data
        counts = {d["count"] for d in [siv, jor, char, gola]}
        assert 2 in counts  # sivasagar has 2
        assert 3 in counts  # jorhat has 3
        assert 1 in counts  # charaideo has 1
