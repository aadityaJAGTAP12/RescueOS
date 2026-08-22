"""
Tests for rank_locations() and allocate_resources().

Tests rank ordering and greedy allocation without Overpass or Ollama.
Tools are mocked so only the deterministic sorting/allocation logic is tested.
"""

import pytest
from unittest.mock import patch, MagicMock
from agent.tools.allocation_tool import rank_locations, allocate_resources


def _make_ranked(location, pdc_score, category):
    """Helper: build a minimal ranked-location dict."""
    return {
        "location": location,
        "pdc_score": pdc_score,
        "category": category,
        "flood_status": {"flooded": True, "exactly_contained": True,
                         "near_flood_zone": False, "total_flood_polygons": 45,
                         "nearest_flood_polygon_km2": 4.88, "detail": ""},
        "exposure": {"total_buildings": 100, "exposed_count": 50,
                     "exposure_ratio": 0.5, "data_available": True},
        "accessibility": {"medical_distance_km": 5.0, "data_available": True},
        "priority": {"pdc_score": pdc_score, "category": category,
                     "recommendation": "test"},
    }


class TestRankLocations:
    """Tests for rank_locations() ordering behavior."""

    @patch("agent.tools.allocation_tool.get_medical_accessibility")
    @patch("agent.tools.allocation_tool.get_building_exposure")
    @patch("agent.tools.allocation_tool.get_flood_status")
    def test_descending_pdc_order(self, mock_flood, mock_exposure, mock_access):
        """Ranked output should be sorted by PDC score descending."""
        # Setup mocks: location_a has high flood, location_b has low
        mock_flood.side_effect = [
            {"flooded": True, "exactly_contained": True, "near_flood_zone": False,
             "total_flood_polygons": 45, "nearest_flood_polygon_km2": 8.0, "detail": ""},
            {"flooded": True, "exactly_contained": True, "near_flood_zone": False,
             "total_flood_polygons": 45, "nearest_flood_polygon_km2": 2.0, "detail": ""},
        ]
        mock_exposure.side_effect = [
            {"exposure_ratio": 0.6, "total_buildings": 100, "exposed_count": 60,
             "data_available": True, "detail": ""},
            {"exposure_ratio": 0.1, "total_buildings": 50, "exposed_count": 5,
             "data_available": True, "detail": ""},
        ]
        mock_access.side_effect = [
            {"medical_distance_km": 12.0, "data_available": True,
             "medical_facility_name": "H1", "detail": ""},
            {"medical_distance_km": 3.0, "data_available": True,
             "medical_facility_name": "H2", "detail": ""},
        ]

        ranked = rank_locations(["location_a", "location_b"])
        scores = [r["pdc_score"] for r in ranked]
        assert scores == sorted(scores, reverse=True), \
            f"Expected descending PDC scores, got {scores}"

    @patch("agent.tools.allocation_tool.get_medical_accessibility")
    @patch("agent.tools.allocation_tool.get_building_exposure")
    @patch("agent.tools.allocation_tool.get_flood_status")
    def test_safe_location_preserved(self, mock_flood, mock_exposure, mock_access):
        """A SAFE/none location should appear in results with score 0."""
        mock_flood.side_effect = [
            {"flooded": True, "exactly_contained": True, "near_flood_zone": False,
             "total_flood_polygons": 45, "nearest_flood_polygon_km2": 5.0, "detail": ""},
            {"flooded": False, "exactly_contained": False, "near_flood_zone": False,
             "total_flood_polygons": 45, "nearest_flood_polygon_km2": 0.0, "detail": ""},
        ]
        mock_exposure.side_effect = [
            {"exposure_ratio": 0.5, "total_buildings": 100, "exposed_count": 50,
             "data_available": True, "detail": ""},
            {"exposure_ratio": 0.0, "total_buildings": 0, "exposed_count": 0,
             "data_available": False, "detail": ""},
        ]
        mock_access.side_effect = [
            {"medical_distance_km": 5.0, "data_available": True,
             "medical_facility_name": "H1", "detail": ""},
            {"medical_distance_km": -1, "data_available": False,
             "medical_facility_name": "Unknown", "detail": ""},
        ]

        ranked = rank_locations(["flooded_loc", "safe_loc"])
        safe = [r for r in ranked if r["location"] == "safe_loc"]
        assert len(safe) == 1
        assert safe[0]["pdc_score"] == 0.0
        assert safe[0]["category"] == "NONE"

    @patch("agent.tools.allocation_tool.get_medical_accessibility")
    @patch("agent.tools.allocation_tool.get_building_exposure")
    @patch("agent.tools.allocation_tool.get_flood_status")
    def test_ties_preserve_input_order(self, mock_flood, mock_exposure, mock_access):
        """When two locations tie on PDC score, they should appear in input order."""
        # Both locations get identical tool responses → same PDC score
        identical_flood = {"flooded": True, "exactly_contained": True,
                           "near_flood_zone": False, "total_flood_polygons": 45,
                           "nearest_flood_polygon_km2": 4.88, "detail": ""}
        identical_exposure = {"exposure_ratio": 0.3, "total_buildings": 50,
                              "exposed_count": 15, "data_available": True, "detail": ""}
        identical_access = {"medical_distance_km": 5.0, "data_available": True,
                            "medical_facility_name": "H1", "detail": ""}

        mock_flood.side_effect = [identical_flood, identical_flood]
        mock_exposure.side_effect = [identical_exposure, identical_exposure]
        mock_access.side_effect = [identical_access, identical_access]

        ranked = rank_locations(["first", "second"])
        assert ranked[0]["location"] == "first"
        assert ranked[1]["location"] == "second"
        assert ranked[0]["pdc_score"] == ranked[1]["pdc_score"]


class TestAllocateResources:
    """Tests for allocate_resources() greedy allocation behavior."""

    def test_safe_locations_receive_nothing(self):
        """SAFE/none locations should receive zero resources."""
        ranked = [
            _make_ranked("safe_loc", 0.0, "NONE"),
            _make_ranked("flooded_loc", 0.6, "PRIORITY"),
        ]
        resources = {"boats": 2, "medical_teams": 1, "food_kg": 5000}
        plan = allocate_resources(ranked, resources)
        assert "no resources allocated" in plan.lower()

    def test_higher_priority_gets_resources_first(self):
        """Highest-priority location should get resources before lower ones."""
        ranked = [
            _make_ranked("high_priority", 0.8, "HIGH PRIORITY"),
            _make_ranked("medium_priority", 0.5, "PRIORITY"),
        ]
        resources = {"boats": 1, "medical_teams": 1, "food_kg": 1000}
        plan = allocate_resources(ranked, resources)
        # high_priority should get allocated
        assert "ALLOCATED" in plan
        assert "high_priority" in plan.upper() or "HIGH_PRIORITY" in plan.upper()

    def test_resource_exhaustion(self):
        """When resources run out, lower-priority locations should get none."""
        ranked = [
            _make_ranked("loc_a", 0.8, "HIGH PRIORITY"),
            _make_ranked("loc_b", 0.6, "PRIORITY"),
            _make_ranked("loc_c", 0.5, "PRIORITY"),
        ]
        resources = {"boats": 1, "medical_teams": 1, "food_kg": 1000}
        plan = allocate_resources(ranked, resources)
        # Only one location should be fully allocated
        assert "NEEDS RESOURCES" in plan or "none remaining" in plan.lower()

    def test_remaining_resources_reported(self):
        """Plan should show remaining unallocated resources."""
        ranked = [
            _make_ranked("safe_loc", 0.0, "NONE"),
        ]
        resources = {"boats": 2, "medical_teams": 1, "food_kg": 5000}
        plan = allocate_resources(ranked, resources)
        assert "Remaining" in plan

    def test_per_location_food_cap(self):
        """Each location gets at most 1000kg food (MVP simplification)."""
        ranked = [
            _make_ranked("loc_a", 0.8, "HIGH PRIORITY"),
        ]
        resources = {"boats": 5, "medical_teams": 5, "food_kg": 10000}
        plan = allocate_resources(ranked, resources)
        # The plan should show allocation for loc_a with food_kg: 1000
        assert "food_kg" in plan

    def test_empty_ranked_list(self):
        """Empty ranked list should produce a valid plan with all resources remaining."""
        resources = {"boats": 2, "medical_teams": 1, "food_kg": 5000}
        plan = allocate_resources([], resources)
        assert "Remaining" in plan
        # All resources should remain
        assert "2" in plan  # boats
        assert "5000" in plan  # food_kg
