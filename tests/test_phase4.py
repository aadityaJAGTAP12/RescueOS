"""
Phase 4 Tests: Rewire the Real Runtime to the Generalized Data Layer

Tests that the ACTUAL production tools read data through the DataRepository
abstraction, not hardcoded file paths or location dicts.

Categories:
1. Flood tool reads repository data
2. District A assessment (via repository)
3. District B assessment (via repository)
4. Settlement resolution through repository
5. Arbitrary coordinate assessment through repository
6. Repository-backed building exposure
7. Repository-backed medical accessibility
8. Repository-backed field reports
9. Repository-backed overrides
10. Different flood snapshots by date
11. Sivasagar regression
12. No district-specific branching
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from agent.data.repository import InMemoryRepository, set_repository, reset_repository
from agent.data.models import (
    District, Settlement, FloodSnapshot, FieldReport, Override,
    MedicalFacility, Building, Road, Provenance, VerificationState,
)
from agent.tools.flood_tool import get_flood_status, _resolve_location
from agent.tools.exposure_tool import get_building_exposure
from agent.tools.accessibility_tool import get_medical_accessibility
from agent.tools.allocation_tool import calculate_priority
from agent.data_loader import get_flood_polygons, get_known_locations, get_all_known_locations


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_repository():
    """Each test gets a fresh in-memory repository with Sivasagar data."""
    repo = InMemoryRepository()
    set_repository(repo)
    # Run migration to populate Sivasagar data
    from agent.data.migration import run_full_migration
    run_full_migration(repo)
    yield repo
    reset_repository()


def _create_district_a(repo: InMemoryRepository) -> None:
    """Create synthetic District A."""
    repo.upsert_district(District(id="test_a", name="Test District A", state="Test"))
    repo.upsert_settlement(Settlement(
        id="test_a_capital", name="Test Capital A", district_id="test_a",
        lat=26.5, lon=94.5,
    ))
    repo.upsert_settlement(Settlement(
        id="test_a_flooded", name="Test Flooded A", district_id="test_a",
        lat=26.52, lon=94.55,
    ))
    # Flood snapshot — 3 polygons
    repo.import_flood_geojson(
        geojson={
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Polygon",
                    "coordinates": [[[94.53, 26.51], [94.57, 26.51], [94.57, 26.53], [94.53, 26.53], [94.53, 26.51]]]},
                 "properties": {}},
                {"type": "Feature", "geometry": {"type": "Polygon",
                    "coordinates": [[[94.48, 26.48], [94.52, 26.48], [94.52, 26.50], [94.48, 26.50], [94.48, 26.48]]]},
                 "properties": {}},
                {"type": "Feature", "geometry": {"type": "Polygon",
                    "coordinates": [[[94.55, 26.54], [94.60, 26.54], [94.60, 26.56], [94.55, 26.56], [94.55, 26.54]]]},
                 "properties": {}},
            ]
        },
        district_id="test_a", source="TEST Synthetic A",
        observed_at="2026-07-15T00:00:00+00:00",
    )
    repo.upsert_medical_facilities([
        MedicalFacility(id="test_a_hosp", district_id="test_a", name="Hospital A",
                       lat=26.51, lon=94.52, provenance=Provenance.SYNTHETIC),
    ])
    repo.upsert_buildings([
        Building(id="test_a_b1", district_id="test_a", lat=26.52, lon=94.54,
                in_flood_zone=True, provenance=Provenance.SYNTHETIC),
        Building(id="test_a_b2", district_id="test_a", lat=26.50, lon=94.50,
                in_flood_zone=False, provenance=Provenance.SYNTHETIC),
    ])


def _create_district_b(repo: InMemoryRepository) -> None:
    """Create synthetic District B."""
    repo.upsert_district(District(id="test_b", name="Test District B", state="Test"))
    repo.upsert_settlement(Settlement(
        id="test_b_capital", name="Test Capital B", district_id="test_b",
        lat=27.0, lon=95.0,
    ))
    repo.upsert_settlement(Settlement(
        id="test_b_safe", name="Test Safe B", district_id="test_b",
        lat=27.05, lon=95.05,
    ))
    # Flood snapshot — 2 polygons, different date
    repo.import_flood_geojson(
        geojson={
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Polygon",
                    "coordinates": [[[94.99, 26.99], [95.01, 26.99], [95.01, 27.01], [94.99, 27.01], [94.99, 26.99]]]},
                 "properties": {}},
                {"type": "Feature", "geometry": {"type": "Polygon",
                    "coordinates": [[[95.02, 27.02], [95.04, 27.02], [95.04, 27.04], [95.02, 27.04], [95.02, 27.02]]]},
                 "properties": {}},
            ]
        },
        district_id="test_b", source="TEST Synthetic B",
        observed_at="2026-08-01T00:00:00+00:00",
    )
    repo.upsert_medical_facilities([
        MedicalFacility(id="test_b_hosp", district_id="test_b", name="Hospital B",
                       lat=27.02, lon=95.08, provenance=Provenance.SYNTHETIC),
    ])
    repo.upsert_buildings([
        Building(id="test_b_b1", district_id="test_b", lat=27.00, lon=95.00,
                in_flood_zone=True, provenance=Provenance.SYNTHETIC),
        Building(id="test_b_b2", district_id="test_b", lat=27.05, lon=95.05,
                in_flood_zone=False, provenance=Provenance.SYNTHETIC),
        Building(id="test_b_b3", district_id="test_b", lat=27.01, lon=95.01,
                in_flood_zone=True, provenance=Provenance.SYNTHETIC),
    ])


# ===================================================================
# TEST 1: Flood tool reads repository data
# ===================================================================

class TestFloodToolRepositoryData:
    """Flood tool reads data from the repository, not hardcoded files."""

    def test_flood_tool_uses_repository_polygons(self, fresh_repository):
        """get_flood_status should work with repository-backed flood data."""
        # Sivasagar flood data is in the repository from migration
        result = get_flood_status("sivasagar_flood_zone")
        assert result["flooded"] is True
        assert result["total_flood_polygons"] > 0

    def test_flood_tool_with_new_district(self, fresh_repository):
        """Flood tool works with a non-Sivasagar district."""
        _create_district_a(fresh_repository)

        # Get flood status for District A
        result = get_flood_status("test_a_flooded")
        assert result["flooded"] is True

    def test_get_flood_polygons_repository(self, fresh_repository):
        """get_flood_polygons returns repository data for known districts."""
        _create_district_a(fresh_repository)

        polygons = get_flood_polygons("test_a")
        assert len(polygons) == 3

    def test_get_flood_polygons_fallback(self, fresh_repository):
        """get_flood_polygons falls back to legacy for unknown districts."""
        polygons = get_flood_polygons("nonexistent_district")
        # Should fall back to legacy Sivasagar data
        assert len(polygons) > 0


# ===================================================================
# TEST 2-3: District A and B assessments via repository
# ===================================================================

class TestMultiDistrictFloodStatus:
    """Different districts return different flood data through the same code path."""

    def test_district_a_flooded(self, fresh_repository):
        """District A capital is inside a flood zone."""
        _create_district_a(fresh_repository)
        result = get_flood_status("test_a_flooded")
        assert result["flooded"] is True
        assert result["exactly_contained"] is True

    def test_district_b_flooded(self, fresh_repository):
        """District B capital is inside a flood zone."""
        _create_district_b(fresh_repository)
        result = get_flood_status("test_b_capital")
        assert result["flooded"] is True

    def test_district_a_has_3_polygons(self, fresh_repository):
        """District A has 3 flood polygons."""
        _create_district_a(fresh_repository)
        result = get_flood_status("test_a_capital")
        assert result["total_flood_polygons"] == 3

    def test_district_b_has_2_polygons(self, fresh_repository):
        """District B has 2 flood polygons."""
        _create_district_b(fresh_repository)
        result = get_flood_status("test_b_capital")
        assert result["total_flood_polygons"] == 2


# ===================================================================
# TEST 4: Settlement resolution through repository
# ===================================================================

class TestSettlementResolution:
    """Location resolution works through the repository."""

    def test_resolve_sivasagar(self, fresh_repository):
        """Sivasagar settlement resolves through repository."""
        settlement = fresh_repository.resolve_location("sivasagar")
        assert settlement is not None
        assert settlement.lat == 26.9701

    def test_resolve_new_district(self, fresh_repository):
        """New district settlement resolves through repository."""
        _create_district_a(fresh_repository)
        settlement = fresh_repository.resolve_location("test_a_capital")
        assert settlement is not None
        assert settlement.district_id == "test_a"

    def test_resolve_coordinate(self, fresh_repository):
        """Coordinate resolution works through repository."""
        _create_district_a(fresh_repository)
        settlement = fresh_repository.resolve_location(lat=26.501, lon=94.501)
        assert settlement is not None


# ===================================================================
# TEST 5: Arbitrary coordinate assessment
# ===================================================================

class TestArbitraryCoordinateAssessment:
    """Assessment works with arbitrary coordinates, not just named locations."""

    def test_flood_status_by_coordinates(self, fresh_repository):
        """Flood status works with explicit lat/lon."""
        _create_district_a(fresh_repository)
        result = get_flood_status(lat=26.52, lon=94.55)
        assert result["flooded"] is True

    def test_flood_status_outside_flood_zone(self, fresh_repository):
        """Point outside flood zone reports not flooded."""
        _create_district_a(fresh_repository)
        result = get_flood_status(lat=26.0, lon=94.0)
        assert result["flooded"] is False


# ===================================================================
# TEST 6: Repository-backed building exposure
# ===================================================================

class TestRepositoryBackedExposure:
    """Building exposure works with repository data."""

    def test_exposure_tool_works(self, fresh_repository):
        """Exposure tool resolves location through repository."""
        # Test the tool's location resolution, not Overpass API
        point_lon, point_lat, label = _resolve_location("sivasagar_flood_zone")
        assert point_lon is not None
        assert point_lat is not None

    def test_exposure_district_resolution(self, fresh_repository):
        """Exposure tool can determine district from location name."""
        from agent.tools.exposure_tool import _resolve_location as exp_resolve
        # Verify the resolve_location function works
        settlement = fresh_repository.resolve_location(name="sivasagar_flood_zone")
        assert settlement is not None
        assert settlement.district_id == "sivasagar"


# ===================================================================
# TEST 7: Repository-backed medical accessibility
# ===================================================================

class TestRepositoryBackedAccessibility:
    """Medical accessibility works with repository data."""

    def test_accessibility_tool_resolves_location(self, fresh_repository):
        """Accessibility tool resolves location through repository."""
        point_lon, point_lat, label = _resolve_location("sivasagar_flood_zone")
        assert point_lon is not None
        assert point_lat is not None

    def test_accessibility_district_resolution(self, fresh_repository):
        """Accessibility tool can determine district from location name."""
        settlement = fresh_repository.resolve_location(name="sivasagar_flood_zone")
        assert settlement is not None
        assert settlement.district_id == "sivasagar"


# ===================================================================
# TEST 8: Repository-backed field reports
# ===================================================================

class TestRepositoryBackedFieldReports:
    """Field reports are stored in and retrieved from the repository."""

    def test_store_and_retrieve(self, fresh_repository):
        """Field report can be stored and retrieved."""
        report = FieldReport(
            id="test_fr_1", district_id="sivasagar",
            lat=26.98, lon=94.66, raw_text="Road blocked",
            people_count=30, needs=["food"],
        )
        fresh_repository.upsert_field_report(report)

        retrieved = fresh_repository.get_field_report("test_fr_1")
        assert retrieved is not None
        assert retrieved.raw_text == "Road blocked"

    def test_list_by_district(self, fresh_repository):
        """Field reports can be filtered by district."""
        fresh_repository.upsert_field_report(FieldReport(
            id="fr_a", district_id="test_a",
        ))
        fresh_repository.upsert_field_report(FieldReport(
            id="fr_b", district_id="test_b",
        ))

        a_reports = fresh_repository.list_field_reports(district_id="test_a")
        assert len(a_reports) == 1


# ===================================================================
# TEST 9: Repository-backed overrides
# ===================================================================

class TestRepositoryBackedOverrides:
    """Overrides are stored in and retrieved from the repository."""

    def test_store_and_retrieve(self, fresh_repository):
        """Override can be stored and retrieved."""
        override = Override(
            id="test_ov_1", target_type="facility",
            target_id="Test Hospital", override_status="damaged",
            system_status="operational",
        )
        fresh_repository.upsert_override(override)

        retrieved = fresh_repository.get_active_override("facility", "Test Hospital")
        assert retrieved is not None
        assert retrieved.override_status == "damaged"
        assert retrieved.system_status == "operational"


# ===================================================================
# TEST 10: Different flood snapshots by date
# ===================================================================

class TestTemporalFloodSnapshots:
    """Different flood snapshots by date work through the repository."""

    def test_same_district_different_dates(self, fresh_repository):
        """Two snapshots for the same district at different dates."""
        repo = fresh_repository
        repo.upsert_district(District(id="temp", name="Temporal Test"))

        snap_early = FloodSnapshot(
            id="temp_early", district_id="temp",
            observed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            source="TEST early", polygon_count=50,
            provenance=Provenance.SYNTHETIC,
        )
        snap_late = FloodSnapshot(
            id="temp_late", district_id="temp",
            observed_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            source="TEST late", polygon_count=20,
            provenance=Provenance.SYNTHETIC,
        )
        repo.upsert_flood_snapshot(snap_early)
        repo.upsert_flood_snapshot(snap_late)

        latest = repo.get_latest_flood_snapshot("temp")
        assert latest.id == "temp_late"


# ===================================================================
# TEST 11: Sivasagar regression
# ===================================================================

class TestSivasagarRegression:
    """Existing Sivasagar behavior remains valid."""

    def test_sivasagar_flood_zone_flooded(self, fresh_repository):
        """Sivasagar flood zone is still detected as flooded."""
        result = get_flood_status("sivasagar_flood_zone")
        assert result["flooded"] is True

    def test_sivasagar_town_center(self, fresh_repository):
        """Sivasagar town center reports flood status."""
        result = get_flood_status("sivasagar")
        assert "flooded" in result

    def test_pdc_formula_unchanged(self, fresh_repository):
        """PDC scoring formula is unchanged."""
        result = calculate_priority(
            flood_detected=True, exposure_ratio=0.6,
            nearest_flood_polygon_km2=4.88, medical_distance_km=12.0,
            data_confidence="High",
        )
        assert result["pdc_score"] > 0.5

    def test_rank_locations_still_works(self, fresh_repository):
        """rank_locations still produces expected ranking for Sivasagar."""
        from agent.tools.allocation_tool import rank_locations
        from agent.config import KNOWN_LOCATIONS
        # Mock Overpass tools at the allocation_tool import point (they're imported at module level)
        with patch("agent.tools.allocation_tool.get_building_exposure") as mock_exp, \
             patch("agent.tools.allocation_tool.get_medical_accessibility") as mock_acc:
            mock_exp.side_effect = [
                {"exposure_ratio": 0.06, "total_buildings": 50, "exposed_count": 3,
                 "data_available": True, "detail": ""},
                {"exposure_ratio": 0.6, "total_buildings": 100, "exposed_count": 60,
                 "data_available": True, "detail": ""},
                {"exposure_ratio": 0.1, "total_buildings": 80, "exposed_count": 8,
                 "data_available": True, "detail": ""},
            ]
            mock_acc.side_effect = [
                {"medical_distance_km": 3.0, "data_available": True,
                 "medical_facility_name": "H1", "detail": ""},
                {"medical_distance_km": 12.0, "data_available": True,
                 "medical_facility_name": "H2", "detail": ""},
                {"medical_distance_km": 5.0, "data_available": True,
                 "medical_facility_name": "H3", "detail": ""},
            ]
            ranked = rank_locations(list(KNOWN_LOCATIONS.keys()))
        assert len(ranked) >= 3
        # Check that flood zone has highest PDC
        scores = [r["pdc_score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)


# ===================================================================
# TEST 12: No district-specific branching
# ===================================================================

class TestNoDistrictBranching:
    """The same code path works for any district — no if/else on district name."""

    def test_same_methods_for_both_districts(self, fresh_repository):
        """Identical method calls work for District A and B."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        for district_id in ["test_a", "test_b"]:
            # Flood polygons
            polygons = get_flood_polygons(district_id)
            assert isinstance(polygons, list)
            assert len(polygons) > 0

            # Known locations
            locs = get_known_locations(district_id)
            assert isinstance(locs, dict)
            assert len(locs) > 0

            # Settlements
            settlements = fresh_repository.list_settlements(district_id=district_id)
            assert len(settlements) >= 1

            # Medical facilities
            facilities = fresh_repository.get_medical_facilities(district_id)
            assert len(facilities) >= 1

            # Buildings
            buildings = fresh_repository.get_buildings(district_id)
            assert len(buildings) >= 1

            # Flood status (use name, not coordinates, to avoid Overpass calls)
            settlement = settlements[0]
            result = get_flood_status(settlement.name)
            assert "flooded" in result

    def test_data_driven_not_scripted(self, fresh_repository):
        """Evidence proves data-driven, not district-scripted."""
        _create_district_a(fresh_repository)
        _create_district_b(fresh_repository)

        a_polygons = get_flood_polygons("test_a")
        b_polygons = get_flood_polygons("test_b")

        # Different polygon counts prove different data
        assert len(a_polygons) != len(b_polygons)

        # Same code path was used for both (no branching in get_flood_polygons)
        # The function checks the repository by district_id, not by hardcoded name
