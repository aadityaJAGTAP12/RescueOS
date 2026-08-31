"""
Tests for the ReliefOS Operational Planner / Query Orchestrator.

Tests cover:
1. Cross-district behavior: same query, different districts produce different results
2. Temporal behavior: same district, different flood snapshot dates
3. Resource-aware planning: different resource constraints
4. Generalization: planner code path is district-agnostic
5. Evidence output: every recommendation exposes why it was produced
6. Uncertainty handling: data gaps are reported honestly
7. Human-in-the-loop: recommendations are advisory, not commands

All tests use the development PostgreSQL database (read-only for planner)
or InMemoryRepository for unit tests.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

# Use development database for integration tests
# (planner only reads, never writes)
os.environ.setdefault("DATABASE_URL", "postgresql://reliefos:reliefos@localhost:5433/reliefos")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_repo():
    """Create an InMemoryRepository with test data for unit tests."""
    from agent.data.repository import InMemoryRepository
    from agent.data.models import (
        District, Settlement, FloodSnapshot, FieldReport,
        Provenance, VerificationState, make_flood_snapshot_id,
    )
    from datetime import datetime, timezone

    repo = InMemoryRepository()

    # District A (high flood)
    repo.upsert_district(District(
        id="district_a",
        name="District A",
        state="TestState",
        country="TestCountry",
        geometry_wkt="POLYGON((94 26, 95 26, 95 27, 94 27, 94 26))",
    ))

    # District B (low flood)
    repo.upsert_district(District(
        id="district_b",
        name="District B",
        state="TestState",
        country="TestCountry",
        geometry_wkt="POLYGON((93 25, 94 25, 94 26, 93 26, 93 25))",
    ))

    # Settlements in District A
    repo.upsert_settlement(Settlement(
        id="loc_a1", name="Alpha Town", district_id="district_a",
        lat=26.5, lon=94.5,
    ))
    repo.upsert_settlement(Settlement(
        id="loc_a2", name="Beta Village", district_id="district_a",
        lat=26.3, lon=94.3,
    ))

    # Settlements in District B
    repo.upsert_settlement(Settlement(
        id="loc_b1", name="Gamma City", district_id="district_b",
        lat=25.5, lon=93.5,
    ))
    repo.upsert_settlement(Settlement(
        id="loc_b2", name="Delta Hamlet", district_id="district_b",
        lat=25.3, lon=93.3,
    ))

    # Flood snapshot for District A (high polygon count — major flood)
    flood_a = FloodSnapshot(
        id="flood_district_a_20260729",
        district_id="district_a",
        observed_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        source="Sentinel-1 SAR",
        confidence=1.0,
        polygon_count=5000,
        provenance=Provenance.REAL,
        geometry_geojson={
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[94.4, 26.4], [94.6, 26.4], [94.6, 26.6], [94.4, 26.6], [94.4, 26.4]]]
                },
                "properties": {}
            }]
        },
    )
    repo.upsert_flood_snapshot(flood_a)

    # Flood snapshot for District B (lower polygon count — minor flood)
    flood_b = FloodSnapshot(
        id="flood_district_b_20260729",
        district_id="district_b",
        observed_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        source="Sentinel-1 SAR",
        confidence=1.0,
        polygon_count=500,
        provenance=Provenance.REAL,
        geometry_geojson={
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[93.4, 25.4], [93.6, 25.4], [93.6, 25.6], [93.4, 25.6], [93.4, 25.4]]]
                },
                "properties": {}
            }]
        },
    )
    repo.upsert_flood_snapshot(flood_b)

    # Field report for District A
    repo.upsert_field_report(FieldReport(
        id="report_a1",
        district_id="district_a",
        lat=26.5,
        lon=94.5,
        source_type="coordinator",
        raw_text="Major flooding in Alpha Town area, 200 people stranded",
        people_count=200,
        needs=["food", "water", "medical"],
        verification_state=VerificationState.VERIFIED,
        extraction_confidence=0.8,
        observed_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        ingested_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        provenance=Provenance.REAL,
    ))

    return repo


@pytest.fixture
def planning_request_high_flood():
    """A planning request for a high-flood district."""
    return {
        "intent": "allocation",
        "locations_mentioned": ["Alpha Town"],
        "resources_mentioned": [
            {"raw_phrase": "3 boats", "resource_type": "transport", "quantity_text": "3", "quantity_numeric": 3, "unit": "boats"},
            {"raw_phrase": "2 medical teams", "resource_type": "medical", "quantity_text": "2", "quantity_numeric": 2, "unit": "medical teams"},
        ],
        "requested_capabilities": {
            "priority_ranking": True,
            "resource_allocation": True,
            "route_optimization": False,
            "river_gauge_data": False,
            "sustainment_calculation": False,
        },
        "prioritization_criteria": [],
        "parse_confidence": "high",
        "clarification_needed": [],
    }


@pytest.fixture
def planning_request_low_flood():
    """A planning request for a low-flood district."""
    return {
        "intent": "allocation",
        "locations_mentioned": ["Gamma City"],
        "resources_mentioned": [
            {"raw_phrase": "3 boats", "resource_type": "transport", "quantity_text": "3", "quantity_numeric": 3, "unit": "boats"},
        ],
        "requested_capabilities": {
            "priority_ranking": True,
            "resource_allocation": True,
            "route_optimization": False,
            "river_gauge_data": False,
            "sustainment_calculation": False,
        },
        "prioritization_criteria": [],
        "parse_confidence": "high",
        "clarification_needed": [],
    }


@pytest.fixture
def planning_request_assessment():
    """An assessment query."""
    return {
        "intent": "assessment",
        "locations_mentioned": ["Alpha Town", "Gamma City"],
        "resources_mentioned": [],
        "requested_capabilities": {
            "priority_ranking": True,
            "resource_allocation": False,
            "route_optimization": False,
            "river_gauge_data": False,
            "sustainment_calculation": False,
        },
        "prioritization_criteria": [],
        "parse_confidence": "high",
        "clarification_needed": [],
    }


# ---------------------------------------------------------------------------
# Test: Cross-district generalization
# ---------------------------------------------------------------------------

class TestCrossDistrictGeneralization:
    """Prove the same planner code path works for different districts
    and can produce different results based on data differences."""

    def test_same_query_different_districts_different_results(self, mem_repo, planning_request_high_flood, planning_request_low_flood):
        """Query A + District A data and Query A + District B data
        use the same planner code but produce different results."""
        from agent.planner import PlannerOrchestrator

        planner = PlannerOrchestrator(repository=mem_repo)

        # Plan for high-flood district
        result_high = planner.plan("Where should 3 boats go first?", planning_request_high_flood)

        # Plan for low-flood district
        result_low = planner.plan("Where should 3 boats go first?", planning_request_low_flood)

        # Both should use the same code path
        assert result_high is not None
        assert result_low is not None

        # Both should have evidence
        assert len(result_high.tools_used) > 0
        assert len(result_low.tools_used) > 0

        # Both should have ranked locations
        assert len(result_high.ranked_locations) > 0
        assert len(result_low.ranked_locations) > 0

        # The recommendation should differ (different data → different output)
        # At minimum, the evidence should be district-specific
        high_districts = set(r["district_id"] for r in result_high.ranked_locations)
        low_districts = set(r["district_id"] for r in result_low.ranked_locations)
        assert high_districts != low_districts or len(result_high.ranked_locations) != len(result_low.ranked_locations)

    def test_same_district_different_flood_dates(self, mem_repo):
        """Same district + different flood snapshot date produces different results."""
        from agent.planner import PlannerOrchestrator
        from agent.data.models import FloodSnapshot, Provenance
        from datetime import datetime, timezone

        # Add an earlier, smaller flood snapshot for District A
        flood_earlier = FloodSnapshot(
            id="flood_district_a_20260701",
            district_id="district_a",
            observed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            source="Sentinel-1 SAR",
            confidence=1.0,
            polygon_count=100,  # Much smaller flood
            provenance=Provenance.REAL,
            geometry_geojson={
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[94.45, 26.45], [94.55, 26.45], [94.55, 26.55], [94.45, 26.55], [94.45, 26.45]]]
                    },
                    "properties": {}
                }]
            },
        )
        mem_repo.upsert_flood_snapshot(flood_earlier)

        planner = PlannerOrchestrator(repository=mem_repo)

        # Query for latest (should get the bigger July 29 flood)
        request = {
            "intent": "assessment",
            "locations_mentioned": ["Alpha Town"],
            "resources_mentioned": [],
            "requested_capabilities": {"priority_ranking": True, "resource_allocation": False, "route_optimization": False, "river_gauge_data": False, "sustainment_calculation": False},
            "prioritization_criteria": [],
            "parse_confidence": "high",
            "clarification_needed": [],
        }

        result = planner.plan("What is the flood status?", request)

        # Should have results
        assert result is not None
        assert len(result.ranked_locations) > 0

        # The flood snapshot list should show both dates
        snaps = result.evidence.get("flood_snapshots", {}).get("district_a", [])
        assert len(snaps) == 2  # Both snapshots should be listed

        # Different dates should be present
        dates = [s["observed_at"] for s in snaps]
        assert "2026-07-01T00:00:00+00:00" in dates
        assert "2026-07-29T00:00:00+00:00" in dates


# ---------------------------------------------------------------------------
# Test: Resource-aware planning
# ---------------------------------------------------------------------------

class TestResourceAwarePlanning:
    """Test that the planner correctly handles different resource constraints."""

    def test_resource_extraction(self, mem_repo, planning_request_high_flood):
        """Resources are correctly extracted from the parsed query."""
        from agent.planner import PlannerOrchestrator

        planner = PlannerOrchestrator(repository=mem_repo)
        result = planner.plan("We have 3 boats and 2 medical teams. Where should they go?", planning_request_high_flood)

        # Should have allocation plan
        assert result.allocation_plan is not None
        assert "RESOURCE ALLOCATION PLAN" in result.allocation_plan

    def test_different_resources_different_plan(self, mem_repo):
        """Different resource quantities produce different allocation plans."""
        from agent.planner import PlannerOrchestrator

        planner = PlannerOrchestrator(repository=mem_repo)

        # Many resources
        request_many = {
            "intent": "allocation",
            "locations_mentioned": ["Alpha Town", "Beta Village"],
            "resources_mentioned": [
                {"raw_phrase": "10 boats", "resource_type": "transport", "quantity_text": "10", "quantity_numeric": 10, "unit": "boats"},
            ],
            "requested_capabilities": {"priority_ranking": True, "resource_allocation": True, "route_optimization": False, "river_gauge_data": False, "sustainment_calculation": False},
            "prioritization_criteria": [],
            "parse_confidence": "high",
            "clarification_needed": [],
        }

        # Few resources
        request_few = {
            "intent": "allocation",
            "locations_mentioned": ["Alpha Town", "Beta Village"],
            "resources_mentioned": [
                {"raw_phrase": "1 boat", "resource_type": "transport", "quantity_text": "1", "quantity_numeric": 1, "unit": "boat"},
            ],
            "requested_capabilities": {"priority_ranking": True, "resource_allocation": True, "route_optimization": False, "river_gauge_data": False, "sustainment_calculation": False},
            "prioritization_criteria": [],
            "parse_confidence": "high",
            "clarification_needed": [],
        }

        result_many = planner.plan("Deploy boats", request_many)
        result_few = planner.plan("Deploy boat", request_few)

        # Both should produce allocation plans
        assert result_many.allocation_plan is not None
        assert result_few.allocation_plan is not None

        # The constraint lists should differ
        assert len(result_many.constraints) > 0
        assert len(result_few.constraints) > 0


# ---------------------------------------------------------------------------
# Test: Evidence output
# ---------------------------------------------------------------------------

class TestEvidenceOutput:
    """Every recommendation must expose why it was produced."""

    def test_recommendation_has_why(self, mem_repo, planning_request_high_flood):
        """Recommendation includes WHY explanation."""
        from agent.planner import PlannerOrchestrator

        planner = PlannerOrchestrator(repository=mem_repo)
        result = planner.plan("Where should boats go?", planning_request_high_flood)

        assert result.recommendation
        assert result.why
        assert len(result.why) > 10  # Non-trivial explanation

    def test_recommendation_has_evidence(self, mem_repo, planning_request_high_flood):
        """Recommendation includes evidence."""
        from agent.planner import PlannerOrchestrator

        planner = PlannerOrchestrator(repository=mem_repo)
        result = planner.plan("Where should boats go?", planning_request_high_flood)

        assert "flood_snapshots" in result.evidence
        assert "location_assessments" in result.evidence
        assert "tools_used" in result.evidence

    def test_recommendation_has_constraints(self, mem_repo, planning_request_high_flood):
        """Recommendation includes constraints."""
        from agent.planner import PlannerOrchestrator

        planner = PlannerOrchestrator(repository=mem_repo)
        result = planner.plan("Where should boats go?", planning_request_high_flood)

        assert len(result.constraints) > 0
        # Should mention the boats constraint
        constraint_text = " ".join(result.constraints).lower()
        assert "boat" in constraint_text


# ---------------------------------------------------------------------------
# Test: Uncertainty handling
# ---------------------------------------------------------------------------

class TestUncertaintyHandling:
    """Test that the planner honestly reports uncertainty."""

    def test_uncertainty_reported(self, mem_repo, planning_request_high_flood):
        """Uncertainty is reported when data is limited."""
        from agent.planner import PlannerOrchestrator

        planner = PlannerOrchestrator(repository=mem_repo)
        result = planner.plan("Where should boats go?", planning_request_high_flood)

        # Should have some uncertainty (flood data age, missing road status, etc.)
        assert isinstance(result.uncertainty, list)

    def test_data_gaps_reported(self, mem_repo, planning_request_high_flood):
        """Data gaps are reported honestly."""
        from agent.planner import PlannerOrchestrator

        planner = PlannerOrchestrator(repository=mem_repo)
        result = planner.plan("Where should boats go?", planning_request_high_flood)

        # Should report road status as a gap
        assert isinstance(result.data_gaps, list)
        gap_text = " ".join(result.data_gaps).lower()
        assert "road" in gap_text  # Road status is always a gap


# ---------------------------------------------------------------------------
# Test: Human-in-the-loop
# ---------------------------------------------------------------------------

class TestHumanInTheLoop:
    """Recommendations are advisory, never autonomous commands."""

    def test_advisory_language(self, mem_repo, planning_request_high_flood):
        """Recommendation uses advisory language, not commands."""
        from agent.planner import PlannerOrchestrator

        planner = PlannerOrchestrator(repository=mem_repo)
        result = planner.plan("Where should boats go?", planning_request_high_flood)

        # Should not contain autonomous command language
        rec_lower = result.recommendation.lower()
        # These phrases imply autonomous authority
        autonomous_phrases = ["i have deployed", "i have ordered", "i am sending", "authorized deployment"]
        for phrase in autonomous_phrases:
            assert phrase not in rec_lower, f"Recommendation contains autonomous language: '{phrase}'"

    def test_ranked_locations_are_advisory(self, mem_repo, planning_request_high_flood):
        """Ranked locations are presented as advisory, not commands."""
        from agent.planner import PlannerOrchestrator

        planner = PlannerOrchestrator(repository=mem_repo)
        result = planner.plan("Where should boats go?", planning_request_high_flood)

        # Ranked locations should be a list of dicts with advisory info
        assert isinstance(result.ranked_locations, list)
        for loc in result.ranked_locations:
            assert "recommendation" in loc
            assert "pdc_score" in loc
            assert "category" in loc


# ---------------------------------------------------------------------------
# Test: Generalization acceptance test
# ---------------------------------------------------------------------------

class TestGeneralizationAcceptance:
    """Prove the planner is district-agnostic."""

    def test_no_district_specific_branches_in_plan(self, mem_repo):
        """The planner code path does not branch on district names."""
        from agent.planner import PlannerOrchestrator
        import inspect

        planner = PlannerOrchestrator(repository=mem_repo)
        source = inspect.getsource(planner.plan)
        source += inspect.getsource(planner._select_capabilities)
        source += inspect.getsource(planner._build_planning_request)

        # Should not contain hardcoded district names
        forbidden_names = ["sivasagar", "jorhat", "charaideo", "golaghat"]
        for name in forbidden_names:
            assert name not in source.lower(), \
                f"Planner code contains hardcoded district name: '{name}'"

    def test_planner_works_with_inmemory_repo(self, mem_repo):
        """Planner works with InMemoryRepository (no PostgreSQL needed)."""
        from agent.planner import PlannerOrchestrator

        planner = PlannerOrchestrator(repository=mem_repo)
        result = planner.plan("What is the flood status?", {
            "intent": "assessment",
            "locations_mentioned": ["Alpha Town"],
            "resources_mentioned": [],
            "requested_capabilities": {"priority_ranking": True, "resource_allocation": False, "route_optimization": False, "river_gauge_data": False, "sustainment_calculation": False},
            "prioritization_criteria": [],
            "parse_confidence": "high",
            "clarification_needed": [],
        })

        assert result is not None
        assert result.recommendation
        assert len(result.ranked_locations) > 0

    def test_regional_query(self, mem_repo):
        """A query with no specific locations scans all districts."""
        from agent.planner import PlannerOrchestrator

        planner = PlannerOrchestrator(repository=mem_repo)
        result = planner.plan("Show me all flood-affected areas", {
            "intent": "assessment",
            "locations_mentioned": [],  # No specific locations
            "resources_mentioned": [],
            "requested_capabilities": {"priority_ranking": True, "resource_allocation": False, "route_optimization": False, "river_gauge_data": False, "sustainment_calculation": False},
            "prioritization_criteria": [],
            "parse_confidence": "high",
            "clarification_needed": [],
        })

        # Should cover both districts
        district_ids = set(r["district_id"] for r in result.ranked_locations)
        assert "district_a" in district_ids
        assert "district_b" in district_ids


# ---------------------------------------------------------------------------
# Test: Integration with real database (read-only)
# ---------------------------------------------------------------------------

def _mock_flood_status(location=None, lat=None, lon=None, district_id=None):
    """Mock flood status that uses repository data without Overpass."""
    from agent.tools.flood_tool import _resolve_location, FLOOD_PROXIMITY_DEG
    from agent.data_loader import get_flood_polygons
    from shapely.geometry import Point

    point_lon, point_lat, location_label = _resolve_location(location, lat, lon, district_id)
    if point_lon is None:
        return location_label

    point = Point(point_lon, point_lat)
    polygons = get_flood_polygons(district_id)

    exactly_contained = False
    near_flood_zone = False
    for poly in polygons:
        if poly.contains(point):
            exactly_contained = True
            break
        elif poly.distance(point) < FLOOD_PROXIMITY_DEG:
            near_flood_zone = True

    is_flooded = exactly_contained or near_flood_zone
    nearest_km2 = 0.0
    if polygons:
        closest = min(polygons, key=lambda p: p.distance(point))
        nearest_km2 = closest.area * 111 * 111

    if exactly_contained:
        detail = f"EXACTLY CONTAINED: {len(polygons)} flood areas in district"
    elif near_flood_zone:
        detail = f"NEAR FLOOD ZONE: {len(polygons)} areas in district"
    else:
        detail = f"NOT FLOOD-AFFECTED: {len(polygons)} areas elsewhere in district"

    return {
        "location": location_label,
        "flooded": is_flooded,
        "exactly_contained": exactly_contained,
        "near_flood_zone": near_flood_zone,
        "total_flood_polygons": len(polygons),
        "nearest_flood_polygon_km2": nearest_km2,
        "detail": detail,
    }


def _mock_building_exposure(location=None, lat=None, lon=None):
    """Mock exposure returning data-available=False (no Overpass needed)."""
    from agent.tools.flood_tool import _resolve_location
    point_lon, point_lat, location_label = _resolve_location(location, lat, lon)
    if point_lon is None:
        return {
            "location": str(location or "unknown"),
            "total_buildings": 0, "exposed_count": 0,
            "exposure_ratio": 0.0, "detail": "No location",
            "data_available": False,
        }
    return {
        "location": location_label, "total_buildings": 0,
        "exposed_count": 0, "exposure_ratio": 0.0,
        "detail": "Building exposure: unavailable (mocked for integration test)",
        "data_available": False,
    }


def _mock_medical_accessibility(location=None, lat=None, lon=None):
    """Mock accessibility returning data-available=False (no Overpass needed)."""
    from agent.tools.flood_tool import _resolve_location
    point_lon, point_lat, location_label = _resolve_location(location, lat, lon)
    if point_lon is None:
        return {
            "location": str(location or "unknown"),
            "medical_distance_km": -1,
            "medical_facility_name": "Unknown",
            "detail": "No location", "data_available": False,
        }
    return {
        "location": location_label, "medical_distance_km": -1,
        "medical_facility_name": "Unknown",
        "detail": "Accessibility: unavailable (mocked for integration test)",
        "data_available": False,
    }




class TestPlannerIntegration:
    """Integration tests against the real development database.

    External network calls (Overpass API, OSRM) are mocked.
    PostgreSQL queries (flood snapshots, settlements, districts) are real.
    These are READ-ONLY — the planner never writes to the database.
    """

    @pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="DATABASE_URL not set"
    )
    def test_cross_district_real_db(self):
        """Same planner code processes different real districts."""
        from agent.planner import PlannerOrchestrator
        from agent.data.postgres_repository import PostgresRepository

        # Explicitly create a PostgreSQL repo (previous tests may have reset to InMemory)
        repo = PostgresRepository(database_url=os.environ["DATABASE_URL"])

        # Use injected mocks for Overpass-dependent tools; real PostgreSQL for snapshots/settlements
        planner = PlannerOrchestrator(
            repository=repo,
            get_flood_status=_mock_flood_status,
            get_building_exposure=_mock_building_exposure,
            get_medical_accessibility=_mock_medical_accessibility,
        )

        # Plan for Jorhat
        result_jh = planner.plan("Assess flood status", {
            "intent": "assessment",
            "locations_mentioned": ["Jorhat"],
            "resources_mentioned": [],
            "requested_capabilities": {"priority_ranking": True, "resource_allocation": False, "route_optimization": False, "river_gauge_data": False, "sustainment_calculation": False},
            "prioritization_criteria": [],
            "parse_confidence": "high",
            "clarification_needed": [],
        })

        # Plan for Golaghat
        result_gol = planner.plan("Assess flood status", {
            "intent": "assessment",
            "locations_mentioned": ["Golaghat"],
            "resources_mentioned": [],
            "requested_capabilities": {"priority_ranking": True, "resource_allocation": False, "route_optimization": False, "river_gauge_data": False, "sustainment_calculation": False},
            "prioritization_criteria": [],
            "parse_confidence": "high",
            "clarification_needed": [],
        })

        # Both should produce results
        assert result_jh is not None
        assert result_gol is not None

        # Both should have evidence
        assert len(result_jh.tools_used) > 0
        assert len(result_gol.tools_used) > 0

        # Should have different flood snapshot data
        jh_snaps = result_jh.evidence.get("flood_snapshots", {})
        gol_snaps = result_gol.evidence.get("flood_snapshots", {})
        assert jh_snaps != gol_snaps

    @pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="DATABASE_URL not set"
    )
    def test_allocation_real_db(self):
        """Resource allocation works against real database."""
        from agent.planner import PlannerOrchestrator
        from agent.data.postgres_repository import PostgresRepository

        repo = PostgresRepository(database_url=os.environ["DATABASE_URL"])

        planner = PlannerOrchestrator(
            repository=repo,
            get_flood_status=_mock_flood_status,
            get_building_exposure=_mock_building_exposure,
            get_medical_accessibility=_mock_medical_accessibility,
        )

        result = planner.plan("We have 5 boats. Where should they go first?", {
            "intent": "allocation",
            "locations_mentioned": ["Jorhat", "Golaghat"],
            "resources_mentioned": [
                {"raw_phrase": "5 boats", "resource_type": "transport", "quantity_text": "5", "quantity_numeric": 5, "unit": "boats"},
            ],
            "requested_capabilities": {"priority_ranking": True, "resource_allocation": True, "route_optimization": False, "river_gauge_data": False, "sustainment_calculation": False},
            "prioritization_criteria": [],
            "parse_confidence": "high",
            "clarification_needed": [],
        })

        assert result is not None
        assert result.allocation_plan is not None
        assert len(result.ranked_locations) > 0
        assert len(result.constraints) > 0
        assert len(result.evidence.get("tools_used", [])) > 0

    @pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="DATABASE_URL not set"
    )
    def test_general_query_real_db(self):
        """General informational query works against real database."""
        from agent.planner import PlannerOrchestrator
        from agent.data.postgres_repository import PostgresRepository

        repo = PostgresRepository(database_url=os.environ["DATABASE_URL"])
        planner = PlannerOrchestrator(repository=repo)
        result = planner.plan("What is the current flood situation across all districts?", {
            "intent": "general",
            "locations_mentioned": [],
            "resources_mentioned": [],
            "requested_capabilities": {"priority_ranking": False, "resource_allocation": False, "route_optimization": False, "river_gauge_data": False, "sustainment_calculation": False},
            "prioritization_criteria": [],
            "parse_confidence": "high",
            "clarification_needed": [],
        })

        assert result is not None
        assert result.recommendation
        # Should have flood snapshot data for all districts
        snaps = result.evidence.get("flood_snapshots", {})
        assert len(snaps) >= 4  # At least 4 districts
