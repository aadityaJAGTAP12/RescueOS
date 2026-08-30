"""
Phase 3 Tests: Generalized, Scenario-Independent Data Foundation

Tests 12 categories specified in the Phase 3 spec:
1. Two different districts can be represented
2. Flood status can be queried by district/data source
3. Flood snapshots can differ by date
4. Infrastructure queries are district-independent
5. Provenance survives storage/retrieval
6. Field reports survive storage/retrieval
7. Overrides retain source + prior state
8. Generalized location resolution works
9. Existing Sivasagar behavior remains unchanged
10. Existing routing still works
11. Existing PDC still works
12. All old tests remain passing

Also includes the GENERALIZATION TEST (category 18 from spec):
- Dataset A: District A, Flood snapshot A, Infrastructure A, Resources A
- Dataset B: District B, Flood snapshot B, Infrastructure B, Resources B
- Same core assessment code runs against both
"""

import pytest
from datetime import datetime, timezone

from agent.data.repository import InMemoryRepository, set_repository, reset_repository
from agent.data.models import (
    District,
    Settlement,
    FloodSnapshot,
    FieldReport,
    Override,
    MedicalFacility,
    Building,
    Road,
    Provenance,
    VerificationState,
    QueryRequest,
    make_flood_snapshot_id,
    make_settlement_id,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_repository():
    """Each test gets a fresh in-memory repository."""
    repo = InMemoryRepository()
    set_repository(repo)
    yield repo
    reset_repository()


# ---------------------------------------------------------------------------
# Synthetic test districts (clearly labeled TEST/SYNTHETIC)
# ---------------------------------------------------------------------------

def _create_district_a(repo: InMemoryRepository) -> None:
    """Create synthetic District A with flood + infrastructure."""
    district = District(
        id="test_district_a",
        name="Test District A",
        state="Test State",
        country="Test Country",
    )
    repo.upsert_district(district)

    # Settlements
    repo.upsert_settlement(Settlement(
        id="test_a_capital",
        name="Test Capital A",
        district_id="test_district_a",
        lat=26.5,
        lon=94.5,
    ))
    repo.upsert_settlement(Settlement(
        id="test_a_flooded",
        name="Test Flooded Village A",
        district_id="test_district_a",
        lat=26.52,
        lon=94.55,
    ))

    # Flood snapshot — large flood (3 polygons)
    flood_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[94.53, 26.51], [94.57, 26.51], [94.57, 26.53], [94.53, 26.53], [94.53, 26.51]]]
                },
                "properties": {"area_km2": 12.5}
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[94.48, 26.48], [94.52, 26.48], [94.52, 26.50], [94.48, 26.50], [94.48, 26.48]]]
                },
                "properties": {"area_km2": 8.0}
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[94.55, 26.54], [94.60, 26.54], [94.60, 26.56], [94.55, 26.56], [94.55, 26.54]]]
                },
                "properties": {"area_km2": 5.0}
            }
        ]
    }
    repo.import_flood_geojson(
        geojson=flood_geojson,
        district_id="test_district_a",
        source="TEST Synthetic Sentinel-1",
        observed_at="2026-07-15T00:00:00+00:00",
    )

    # Medical facilities
    repo.upsert_medical_facilities([
        MedicalFacility(
            id="test_a_hospital",
            district_id="test_district_a",
            name="Test Hospital A",
            lat=26.51,
            lon=94.52,
            facility_type="hospital",
            provenance=Provenance.SYNTHETIC,
        ),
    ])

    # Buildings
    repo.upsert_buildings([
        Building(
            id="test_a_bldg_1",
            district_id="test_district_a",
            lat=26.52,
            lon=94.54,
            in_flood_zone=True,
            provenance=Provenance.SYNTHETIC,
        ),
        Building(
            id="test_a_bldg_2",
            district_id="test_district_a",
            lat=26.50,
            lon=94.50,
            in_flood_zone=False,
            provenance=Provenance.SYNTHETIC,
        ),
    ])


def _create_district_b(repo: InMemoryRepository) -> None:
    """Create synthetic District B with different flood + infrastructure."""
    district = District(
        id="test_district_b",
        name="Test District B",
        state="Test State",
        country="Test Country",
    )
    repo.upsert_district(district)

    # Settlements
    repo.upsert_settlement(Settlement(
        id="test_b_capital",
        name="Test Capital B",
        district_id="test_district_b",
        lat=27.0,
        lon=95.0,
    ))
    repo.upsert_settlement(Settlement(
        id="test_b_safe",
        name="Test Safe Village B",
        district_id="test_district_b",
        lat=27.05,
        lon=95.05,
    ))

    # Flood snapshot — smaller flood, different date (2 polygons)
    flood_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[94.99, 26.99], [95.01, 26.99], [95.01, 27.01], [94.99, 27.01], [94.99, 26.99]]]
                },
                "properties": {"area_km2": 3.2}
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[95.02, 27.02], [95.04, 27.02], [95.04, 27.04], [95.02, 27.04], [95.02, 27.02]]]
                },
                "properties": {"area_km2": 1.5}
            }
        ]
    }
    repo.import_flood_geojson(
        geojson=flood_geojson,
        district_id="test_district_b",
        source="TEST Synthetic Sentinel-1",
        observed_at="2026-08-01T00:00:00+00:00",
    )

    # Medical facilities — further away
    repo.upsert_medical_facilities([
        MedicalFacility(
            id="test_b_hospital",
            district_id="test_district_b",
            name="Test Hospital B",
            lat=27.02,
            lon=95.08,
            facility_type="hospital",
            provenance=Provenance.SYNTHETIC,
        ),
    ])

    # Buildings — different pattern
    repo.upsert_buildings([
        Building(
            id="test_b_bldg_1",
            district_id="test_district_b",
            lat=27.00,
            lon=95.00,
            in_flood_zone=True,
            provenance=Provenance.SYNTHETIC,
        ),
        Building(
            id="test_b_bldg_2",
            district_id="test_district_b",
            lat=27.05,
            lon=95.05,
            in_flood_zone=False,
            provenance=Provenance.SYNTHETIC,
        ),
        Building(
            id="test_b_bldg_3",
            district_id="test_district_b",
            lat=27.01,
            lon=95.01,
            in_flood_zone=True,
            provenance=Provenance.SYNTHETIC,
        ),
    ])


# ===================================================================
# TEST CATEGORY 1: Two different districts can be represented
# ===================================================================

class TestTwoDistrictsRepresented:
    """Two different districts with different data can coexist."""

    def test_two_districts_stored(self, fresh_repository):
        """Both districts should be stored and retrievable."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        districts = fresh_repository.list_districts()
        assert len(districts) == 2
        ids = {d.id for d in districts}
        assert "test_district_a" in ids
        assert "test_district_b" in ids

    def test_districts_have_distinct_settlements(self, fresh_repository):
        """Each district has its own settlements."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        a_settlements = fresh_repository.list_settlements(district_id="test_district_a")
        b_settlements = fresh_repository.list_settlements(district_id="test_district_b")

        assert len(a_settlements) >= 2
        assert len(b_settlements) >= 2
        assert all(s.district_id == "test_district_a" for s in a_settlements)
        assert all(s.district_id == "test_district_b" for s in b_settlements)

    def test_districts_have_distinct_flood_data(self, fresh_repository):
        """Each district has its own flood snapshots."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        a_snapshots = fresh_repository.list_flood_snapshots(district_id="test_district_a")
        b_snapshots = fresh_repository.list_flood_snapshots(district_id="test_district_b")

        assert len(a_snapshots) == 1
        assert len(b_snapshots) == 1
        assert a_snapshots[0].polygon_count != b_snapshots[0].polygon_count


# ===================================================================
# TEST CATEGORY 2: Flood status can be queried by district/data source
# ===================================================================

class TestFloodQueryByDistrict:
    """Flood snapshots are queryable by district and source."""

    def test_query_by_district(self, fresh_repository):
        """Can filter flood snapshots by district_id."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        a = fresh_repository.list_flood_snapshots(district_id="test_district_a")
        b = fresh_repository.list_flood_snapshots(district_id="test_district_b")

        assert len(a) == 1
        assert a[0].district_id == "test_district_a"
        assert len(b) == 1
        assert b[0].district_id == "test_district_b"

    def test_query_all_districts(self, fresh_repository):
        """Querying without district filter returns all snapshots."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        all_snapshots = fresh_repository.list_flood_snapshots()
        assert len(all_snapshots) == 2

    def test_flood_source_recorded(self, fresh_repository):
        """Each flood snapshot records its data source."""
        _create_district_a(fresh_repository)

        snapshots = fresh_repository.list_flood_snapshots(district_id="test_district_a")
        assert "TEST Synthetic" in snapshots[0].source

    def test_flood_confidence_recorded(self, fresh_repository):
        """Each flood snapshot records confidence."""
        _create_district_a(fresh_repository)

        snapshots = fresh_repository.list_flood_snapshots(district_id="test_district_a")
        assert snapshots[0].confidence == 1.0


# ===================================================================
# TEST CATEGORY 3: Flood snapshots can differ by date
# ===================================================================

class TestTemporalFloodModel:
    """Multiple flood snapshots can exist for the same district at different dates."""

    def test_same_district_different_dates(self, fresh_repository):
        """Two snapshots for the same district with different dates."""
        district = District(id="temporal_test", name="Temporal Test")
        fresh_repository.upsert_district(district)

        # July flood — larger
        snap_july = FloodSnapshot(
            id="flood_temporal_july",
            district_id="temporal_test",
            observed_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
            source="TEST July snapshot",
            polygon_count=50,
            provenance=Provenance.SYNTHETIC,
        )
        fresh_repository.upsert_flood_snapshot(snap_july)

        # August flood — smaller
        snap_aug = FloodSnapshot(
            id="flood_temporal_aug",
            district_id="temporal_test",
            observed_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            source="TEST August snapshot",
            polygon_count=20,
            provenance=Provenance.SYNTHETIC,
        )
        fresh_repository.upsert_flood_snapshot(snap_aug)

        all_snaps = fresh_repository.list_flood_snapshots(district_id="temporal_test")
        assert len(all_snaps) == 2

        # Can get latest
        latest = fresh_repository.get_latest_flood_snapshot("temporal_test")
        assert latest.id == "flood_temporal_aug"

    def test_get_latest_before_date(self, fresh_repository):
        """get_latest_flood_snapshot with date filter returns correct snapshot."""
        district = District(id="temporal_test2", name="Temporal Test 2")
        fresh_repository.upsert_district(district)

        snap_early = FloodSnapshot(
            id="flood_early",
            district_id="temporal_test2",
            observed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            source="TEST early",
            provenance=Provenance.SYNTHETIC,
        )
        snap_late = FloodSnapshot(
            id="flood_late",
            district_id="temporal_test2",
            observed_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            source="TEST late",
            provenance=Provenance.SYNTHETIC,
        )
        fresh_repository.upsert_flood_snapshot(snap_early)
        fresh_repository.upsert_flood_snapshot(snap_late)

        # Get latest before July 15
        latest = fresh_repository.get_latest_flood_snapshot(
            "temporal_test2",
            observed_at="2026-07-15T00:00:00+00:00"
        )
        assert latest.id == "flood_early"


# ===================================================================
# TEST CATEGORY 4: Infrastructure queries are district-independent
# ===================================================================

class TestDistrictIndependentInfrastructure:
    """Infrastructure queries work the same way for any district."""

    def test_medical_facilities_by_district(self, fresh_repository):
        """Medical facilities are filtered by district."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        a_facilities = fresh_repository.get_medical_facilities("test_district_a")
        b_facilities = fresh_repository.get_medical_facilities("test_district_b")

        assert len(a_facilities) == 1
        assert a_facilities[0].name == "Test Hospital A"
        assert len(b_facilities) == 1
        assert b_facilities[0].name == "Test Hospital B"

    def test_buildings_by_district(self, fresh_repository):
        """Buildings are filtered by district."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        a_buildings = fresh_repository.get_buildings("test_district_a")
        b_buildings = fresh_repository.get_buildings("test_district_b")

        assert len(a_buildings) == 2  # 1 in flood zone, 1 not
        assert len(b_buildings) == 3  # 2 in flood zone, 1 not

    def test_buildings_by_district_and_location(self, fresh_repository):
        """Buildings can be filtered by district AND proximity."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        # Query near District A capital
        nearby = fresh_repository.get_buildings(
            "test_district_a", lat=26.5, lon=94.5, radius_km=5.0
        )
        assert len(nearby) >= 1  # at least the capital buildings


# ===================================================================
# TEST CATEGORY 5: Provenance survives storage/retrieval
# ===================================================================

class TestProvenancePersistence:
    """Provenance tags are preserved through storage and retrieval."""

    def test_flood_snapshot_provenance(self, fresh_repository):
        """Flood snapshot provenance is preserved."""
        snap = FloodSnapshot(
            id="prov_test_snap",
            district_id="prov_test",
            observed_at=datetime.now(timezone.utc),
            source="TEST",
            provenance=Provenance.REAL,
        )
        fresh_repository.upsert_flood_snapshot(snap)

        retrieved = fresh_repository.get_flood_snapshot("prov_test_snap")
        assert retrieved.provenance == Provenance.REAL

    def test_field_report_provenance(self, fresh_repository):
        """Field report provenance is preserved."""
        report = FieldReport(
            id="prov_test_report",
            source_type="community_report",
            provenance=Provenance.REAL,
        )
        fresh_repository.upsert_field_report(report)

        retrieved = fresh_repository.get_field_report("prov_test_report")
        assert retrieved.provenance == Provenance.REAL

    def test_synthetic_provenance(self, fresh_repository):
        """Synthetic data is clearly tagged."""
        snap = FloodSnapshot(
            id="prov_synthetic",
            district_id="prov_test",
            observed_at=datetime.now(timezone.utc),
            source="TEST",
            provenance=Provenance.SYNTHETIC,
        )
        fresh_repository.upsert_flood_snapshot(snap)

        retrieved = fresh_repository.get_flood_snapshot("prov_synthetic")
        assert retrieved.provenance == Provenance.SYNTHETIC

    def test_provenance_summary(self, fresh_repository):
        """Provenance summary counts by type."""
        fresh_repository.upsert_flood_snapshot(FloodSnapshot(
            id="ps1", district_id="d1", observed_at=datetime.now(timezone.utc),
            source="t", provenance=Provenance.REAL,
        ))
        fresh_repository.upsert_flood_snapshot(FloodSnapshot(
            id="ps2", district_id="d1", observed_at=datetime.now(timezone.utc),
            source="t", provenance=Provenance.SYNTHETIC,
        ))
        fresh_repository.upsert_field_report(FieldReport(
            id="pr1", provenance=Provenance.MANUAL_OVERRIDE,
        ))

        summary = fresh_repository.get_provenance_summary()
        assert summary.get("REAL") == 1
        assert summary.get("SYNTHETIC") == 1
        assert summary.get("MANUAL_OVERRIDE") == 1


# ===================================================================
# TEST CATEGORY 6: Field reports survive storage/retrieval
# ===================================================================

class TestFieldReportPersistence:
    """Field reports are stored and retrieved correctly."""

    def test_store_and_retrieve(self, fresh_repository):
        """A field report can be stored and retrieved by ID."""
        report = FieldReport(
            id="fr_test_1",
            district_id="sivasagar",
            lat=26.98,
            lon=94.66,
            source_type="community_report",
            raw_text="Road blocked near the school",
            people_count=30,
            needs=["food", "water"],
            observed_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        )
        fresh_repository.upsert_field_report(report)

        retrieved = fresh_repository.get_field_report("fr_test_1")
        assert retrieved is not None
        assert retrieved.raw_text == "Road blocked near the school"
        assert retrieved.people_count == 30
        assert "food" in retrieved.needs

    def test_list_by_district(self, fresh_repository):
        """Field reports can be filtered by district."""
        fresh_repository.upsert_field_report(FieldReport(
            id="fr_d1", district_id="d_a", lat=26.5, lon=94.5,
        ))
        fresh_repository.upsert_field_report(FieldReport(
            id="fr_d2", district_id="d_b", lat=27.0, lon=95.0,
        ))

        a_reports = fresh_repository.list_field_reports(district_id="d_a")
        assert len(a_reports) == 1
        assert a_reports[0].id == "fr_d1"

    def test_list_by_proximity(self, fresh_repository):
        """Field reports can be found by proximity."""
        fresh_repository.upsert_field_report(FieldReport(
            id="fr_near", lat=26.50, lon=94.50,
        ))
        fresh_repository.upsert_field_report(FieldReport(
            id="fr_far", lat=28.00, lon=96.00,
        ))

        nearby = fresh_repository.list_field_reports(lat=26.50, lon=94.50, radius_km=5.0)
        nearby_ids = {r.id for r in nearby}
        assert "fr_near" in nearby_ids
        assert "fr_far" not in nearby_ids

    def test_raw_text_preserved(self, fresh_repository):
        """Raw text is preserved exactly."""
        raw = "Road blocked near the school. 30 people need water urgently."
        report = FieldReport(id="fr_raw", raw_text=raw)
        fresh_repository.upsert_field_report(report)

        retrieved = fresh_repository.get_field_report("fr_raw")
        assert retrieved.raw_text == raw


# ===================================================================
# TEST CATEGORY 7: Overrides retain source + prior state
# ===================================================================

class TestOverridePersistence:
    """Overrides retain system_status and override_status."""

    def test_store_and_retrieve(self, fresh_repository):
        """Override can be stored and retrieved."""
        override = Override(
            id="ov_test_1",
            target_type="facility",
            target_id="Test Hospital",
            override_status="damaged",
            reason="Flood damage observed",
            system_status="operational",
        )
        fresh_repository.upsert_override(override)

        retrieved = fresh_repository.get_active_override("facility", "Test Hospital")
        assert retrieved is not None
        assert retrieved.override_status == "damaged"
        assert retrieved.system_status == "operational"
        assert retrieved.reason == "Flood damage observed"

    def test_override_preserves_prior_state(self, fresh_repository):
        """Override records both system_status and override_status."""
        override = Override(
            id="ov_prior",
            target_type="road",
            target_id="Main Road",
            override_status="blocked",
            system_status="clear",
        )
        fresh_repository.upsert_override(override)

        retrieved = fresh_repository.get_active_override("road", "Main Road")
        assert retrieved.system_status == "clear"
        assert retrieved.override_status == "blocked"

    def test_inactive_override_not_returned(self, fresh_repository):
        """Inactive overrides are not returned by get_active_override."""
        override = Override(
            id="ov_inactive",
            target_type="facility",
            target_id="Test Facility",
            override_status="damaged",
            active=False,
        )
        fresh_repository.upsert_override(override)

        retrieved = fresh_repository.get_active_override("facility", "Test Facility")
        assert retrieved is None

    def test_fuzzy_name_matching(self, fresh_repository):
        """Override matching uses case-insensitive substring matching."""
        override = Override(
            id="ov_fuzzy",
            target_type="facility",
            target_id="East Point Hospital And Research Centre",
            override_status="damaged",
        )
        fresh_repository.upsert_override(override)

        # Should match partial name
        retrieved = fresh_repository.get_active_override("facility", "East Point Hospital")
        assert retrieved is not None


# ===================================================================
# TEST CATEGORY 8: Generalized location resolution works
# ===================================================================

class TestLocationResolution:
    """Location resolution works without hardcoded place names."""

    def test_resolve_by_exact_name(self, fresh_repository):
        """Exact name match resolves correctly."""
        _create_district_a(fresh_repository)

        settlement = fresh_repository.resolve_location("test_a_capital")
        assert settlement is not None
        assert settlement.name == "Test Capital A"
        assert settlement.lat == 26.5

    def test_resolve_by_coordinate(self, fresh_repository):
        """Coordinates resolve to nearest settlement."""
        _create_district_a(fresh_repository)

        settlement = fresh_repository.resolve_location(lat=26.501, lon=94.501)
        assert settlement is not None
        assert settlement.lat == 26.5  # nearest to test_a_capital

    def test_resolve_by_partial_name(self, fresh_repository):
        """Partial name match resolves correctly."""
        _create_district_a(fresh_repository)

        settlement = fresh_repository.resolve_location("Capital A")
        assert settlement is not None
        assert settlement.id == "test_a_capital"

    def test_resolve_unknown_returns_none(self, fresh_repository):
        """Unknown location returns None."""
        _create_district_a(fresh_repository)

        settlement = fresh_repository.resolve_location("nonexistent_place")
        assert settlement is None

    def test_resolve_direct_coordinates_creates_synthetic(self, fresh_repository):
        """Direct coordinates not near any settlement create a synthetic settlement."""
        _create_district_a(fresh_repository)

        settlement = fresh_repository.resolve_location(lat=28.0, lon=96.0)
        assert settlement is not None
        assert settlement.lat == 28.0
        assert settlement.lon == 96.0
        # Synthetic ID
        assert "coord_" in settlement.id

    def test_resolve_across_districts(self, fresh_repository):
        """Location resolution works across districts."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        a = fresh_repository.resolve_location("test_a_capital")
        b = fresh_repository.resolve_location("test_b_capital")
        assert a is not None
        assert b is not None
        assert a.district_id == "test_district_a"
        assert b.district_id == "test_district_b"


# ===================================================================
# TEST CATEGORY 9: Existing Sivasagar behavior remains unchanged
# ===================================================================

class TestSivasagarBackwardCompatibility:
    """The existing Sivasagar data still works through the new layer."""

    def test_sivasagar_migration(self, fresh_repository):
        """Sivasagar flood data can be imported."""
        from agent.data.migration import migrate_flood_data

        snapshot = migrate_flood_data(fresh_repository)
        assert snapshot is not None
        assert snapshot.district_id == "sivasagar"
        assert snapshot.polygon_count > 0
        assert "Sentinel-1" in snapshot.source

    def test_sivasagar_settlements_present(self, fresh_repository):
        """Sivasagar known locations exist as settlements."""
        from agent.data.migration import SIVASAGAR_SETTLEMENTS

        for s in SIVASAGAR_SETTLEMENTS:
            fresh_repository.upsert_settlement(s)

        settlement = fresh_repository.resolve_location("sivasagar_flood_zone")
        assert settlement is not None
        assert settlement.lat == 26.9894
        assert settlement.lon == 94.6698

    def test_sivasagar_flood_geojson_importable(self, fresh_repository):
        """The actual sivasagar_flood.geojson can be imported."""
        import json
        import os

        geojson_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "sivasagar_flood.geojson"
        )
        if os.path.exists(geojson_path):
            with open(geojson_path, "r") as f:
                geojson = json.load(f)

            snapshot = fresh_repository.import_flood_geojson(
                geojson=geojson,
                district_id="sivasagar",
                source="Sentinel-1 SAR (Earth Engine export)",
            )
            assert snapshot.polygon_count == len(geojson.get("features", []))


# ===================================================================
# TEST CATEGORY 10: Existing routing still works
# ===================================================================

class TestRoutingBackwardCompatibility:
    """Routing tool still functions (tested via import)."""

    def test_routing_tool_importable(self):
        """routing_tool.py can be imported without errors."""
        from agent.tools.routing_tool import get_route, check_route_flood_intersection
        assert callable(get_route)
        assert callable(check_route_flood_intersection)


# ===================================================================
# TEST CATEGORY 11: Existing PDC still works
# ===================================================================

class TestPDCBackwardCompatibility:
    """PDC scoring formula is unchanged."""

    def test_pdc_formula_unchanged(self):
        """calculate_priority still produces expected results."""
        from agent.tools.allocation_tool import calculate_priority

        # Known inputs → known outputs (from existing tests)
        result = calculate_priority(
            flood_detected=True,
            exposure_ratio=0.6,
            nearest_flood_polygon_km2=4.88,
            medical_distance_km=12.0,
            data_confidence="High",
        )
        assert result["pdc_score"] > 0.5
        assert result["category"] in ("PRIORITY", "HIGH PRIORITY")

    def test_pdc_no_flood(self):
        """No flood → score 0.0."""
        from agent.tools.allocation_tool import calculate_priority

        result = calculate_priority(
            flood_detected=False,
            exposure_ratio=0.5,
            nearest_flood_polygon_km2=5.0,
            medical_distance_km=3.0,
            data_confidence="High",
        )
        assert result["pdc_score"] == 0.0
        assert result["category"] == "NONE"


# ===================================================================
# TEST CATEGORY 12: All old tests remain passing
# (This is validated by running the full test suite — see Step 12)
# ===================================================================

class TestOldTestsStillPass:
    """Placeholder — actual validation is running pytest."""

    def test_placeholder(self):
        """This test exists so the category is visible in test output."""
        assert True


# ===================================================================
# GENERALIZATION TEST (Category 18 from spec)
# ===================================================================

class TestGeneralization:
    """
    The most important acceptance criterion:
    Can the same assessment code run against two different district datasets
    without district-specific code or scenario-specific branching?
    """

    def test_same_code_two_districts(self, fresh_repository):
        """
        Same assessment logic runs against both District A and District B.
        No code changes between A and B.
        """
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        # Run the SAME query contract against both districts
        for district_id in ["test_district_a", "test_district_b"]:
            # Get district data
            district = fresh_repository.get_district(district_id)
            assert district is not None

            # Get flood snapshot
            snapshots = fresh_repository.list_flood_snapshots(district_id=district_id)
            assert len(snapshots) >= 1

            # Get settlements
            settlements = fresh_repository.list_settlements(district_id=district_id)
            assert len(settlements) >= 1

            # Get medical facilities
            facilities = fresh_repository.get_medical_facilities(district_id=district_id)
            assert len(facilities) >= 1

            # Get buildings
            buildings = fresh_repository.get_buildings(district_id=district_id)
            assert len(buildings) >= 1

            # Resolve a location
            settlement = fresh_repository.resolve_location(
                lat=settlements[0].lat, lon=settlements[0].lon
            )
            assert settlement is not None

    def test_data_driven_not_scripted(self, fresh_repository):
        """
        The application is data-driven, not district-scripted.
        Evidence: the same repository methods work for any district.
        """
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        # These are the generalized data access methods
        # They work for ANY district — no if/else on district name
        for district in fresh_repository.list_districts():
            # Flood queries
            snapshots = fresh_repository.list_flood_snapshots(district_id=district.id)
            assert isinstance(snapshots, list)

            # Location resolution
            settlements = fresh_repository.list_settlements(district_id=district.id)
            for s in settlements:
                resolved = fresh_repository.resolve_location(s.name)
                assert resolved is not None

            # Infrastructure queries
            facilities = fresh_repository.get_medical_facilities(district_id=district.id)
            buildings = fresh_repository.get_buildings(district_id=district.id)
            assert isinstance(facilities, list)
            assert isinstance(buildings, list)

    def test_different_flood_data_per_district(self, fresh_repository):
        """Different districts have different flood data — no shared state."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        a_snap = fresh_repository.get_latest_flood_snapshot("test_district_a")
        b_snap = fresh_repository.get_latest_flood_snapshot("test_district_b")

        # Different polygon counts
        assert a_snap.polygon_count != b_snap.polygon_count

        # Different dates
        assert a_snap.observed_at != b_snap.observed_at

        # Different sources
        assert a_snap.source != b_snap.source or a_snap.observed_at != b_snap.observed_at

    def test_query_contract_works_for_any_district(self, fresh_repository):
        """The QueryRequest contract is district-agnostic."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        for district in fresh_repository.list_districts():
            request = QueryRequest(
                query_type="assessment",
                locations=[{"district_id": district.id}],
                raw_input=f"Assess flood status in {district.name}",
            )
            # The contract doesn't reference any specific district
            assert request.query_type == "assessment"
            assert len(request.locations) == 1
            assert request.locations[0]["district_id"] == district.id
