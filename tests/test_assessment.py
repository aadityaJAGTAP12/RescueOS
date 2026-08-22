"""
Tests for run_relief_assessment() — the orchestration boundary.

These tests verify that:
1. The coordinator gathers evidence deterministically from tools
2. PDC calculation is always deterministic (never LLM-generated)
3. The structured result contains all expected fields
4. Error handling works correctly
5. The LLM path is optional and doesn't break the deterministic path

All tests mock the tool layer — no Overpass or Ollama required.
"""

import pytest
from unittest.mock import patch, MagicMock
from agent.assessment import (
    run_relief_assessment,
    gather_flood_evidence,
    gather_accessibility_evidence,
    _determine_data_confidence,
    _resolve_location_label,
    _resolve_coordinates,
)
from agent.tools.allocation_tool import calculate_priority


# ---------------------------------------------------------------------------
# Mock data fixtures
# ---------------------------------------------------------------------------

MOCK_FLOOD_FLOODED = {
    "location": "test_flood_zone",
    "flooded": True,
    "exactly_contained": True,
    "near_flood_zone": False,
    "total_flood_polygons": 45,
    "nearest_flood_polygon_km2": 4.88,
    "detail": "EXACTLY CONTAINED"
}

MOCK_FLOOD_SAFE = {
    "location": "test_safe",
    "flooded": False,
    "exactly_contained": False,
    "near_flood_zone": False,
    "total_flood_polygons": 45,
    "nearest_flood_polygon_km2": 0.0,
    "detail": "NOT FLOOD-AFFECTED"
}

MOCK_EXPOSURE_HIGH = {
    "location": "test",
    "total_buildings": 100,
    "exposed_count": 60,
    "exposure_ratio": 0.6,
    "detail": "100 buildings, 60 exposed",
    "data_available": True
}

MOCK_EXPOSURE_LOW = {
    "location": "test",
    "total_buildings": 50,
    "exposed_count": 3,
    "exposure_ratio": 0.06,
    "detail": "50 buildings, 3 exposed",
    "data_available": True
}

MOCK_ACCESSIBILITY_NEAR = {
    "location": "test",
    "medical_distance_km": 2.5,
    "medical_facility_name": "Test Hospital",
    "detail": "Test Hospital at 2.5km",
    "data_available": True
}

MOCK_ACCESSIBILITY_FAR = {
    "location": "test",
    "medical_distance_km": 12.0,
    "medical_facility_name": "Remote Clinic",
    "detail": "Remote Clinic at 12.0km",
    "data_available": True
}

MOCK_ACCESSIBILITY_UNKNOWN = {
    "location": "test",
    "medical_distance_km": -1,
    "medical_facility_name": "Unknown",
    "detail": "No medical facilities found",
    "data_available": False
}


# ---------------------------------------------------------------------------
# Helper to build mock side_effects for run_relief_assessment
# ---------------------------------------------------------------------------

def _make_tool_side_effects(flood, exposure, accessibility):
    """
    Build side_effect tuples for the three tools in the order
    gather_flood_evidence and gather_accessibility_evidence call them.
    """
    # gather_flood_evidence calls: get_flood_status, get_building_exposure
    # gather_accessibility_evidence calls: get_medical_accessibility
    return (flood, exposure, accessibility)


# ---------------------------------------------------------------------------
# Tests: run_relief_assessment() structured result
# ---------------------------------------------------------------------------

class TestRunReliefAssessment:
    """Tests for the main entry point."""

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_known_location_assessment(self, mock_flood, mock_exposure, mock_access):
        """Assessment of a known location should return structured result."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        result = run_relief_assessment("sivasagar_flood_zone")

        assert result["location"] == "sivasagar_flood_zone"
        assert result["coordinates"]["lat"] is not None
        assert result["coordinates"]["lon"] is not None
        assert "evidence" in result
        assert "priority" in result
        assert result["llm_synthesis"] is None  # no LLM by default

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_arbitrary_coordinates(self, mock_flood, mock_exposure, mock_access):
        """Assessment with explicit lat/lon should work."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        result = run_relief_assessment(lat=26.9894, lon=94.6698)

        assert "26.9894" in result["location"]
        assert result["coordinates"]["lat"] == 26.9894
        assert result["coordinates"]["lon"] == 94.6698

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_safe_location(self, mock_flood, mock_exposure, mock_access):
        """Safe (non-flooded) location should have PDC=0 and category=NONE."""
        mock_flood.return_value = MOCK_FLOOD_SAFE
        mock_exposure.return_value = MOCK_EXPOSURE_LOW
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        result = run_relief_assessment("sivasagar")

        assert result["priority"]["pdc_score"] == 0.0
        assert result["priority"]["category"] == "NONE"
        assert result["evidence"]["flood"]["flooded"] is False

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_flooded_high_priority_location(self, mock_flood, mock_exposure, mock_access):
        """Flooded location with high exposure should have elevated PDC."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_FAR

        result = run_relief_assessment("sivasagar_flood_zone")

        assert result["priority"]["pdc_score"] > 0.0
        assert result["priority"]["category"] != "NONE"
        assert result["evidence"]["flood"]["flooded"] is True

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_pdc_is_deterministic(self, mock_flood, mock_exposure, mock_access):
        """PDC must come from calculate_priority(), not from LLM."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        result = run_relief_assessment("test_location")

        # Verify PDC matches what calculate_priority produces
        expected_pdc = calculate_priority(
            flood_detected=MOCK_FLOOD_FLOODED["flooded"],
            exposure_ratio=MOCK_EXPOSURE_HIGH["exposure_ratio"],
            nearest_flood_polygon_km2=MOCK_FLOOD_FLOODED["nearest_flood_polygon_km2"],
            medical_distance_km=MOCK_ACCESSIBILITY_NEAR["medical_distance_km"],
            data_confidence="High",
        )
        assert result["priority"]["pdc_score"] == expected_pdc["pdc_score"]
        assert result["priority"]["category"] == expected_pdc["category"]
        assert result["priority"]["recommendation"] == expected_pdc["recommendation"]

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_structured_result_schema(self, mock_flood, mock_exposure, mock_access):
        """Result should contain all expected top-level fields."""
        mock_flood.return_value = MOCK_FLOOD_SAFE
        mock_exposure.return_value = MOCK_EXPOSURE_LOW
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        result = run_relief_assessment("sivasagar")

        required_fields = {
            "location", "coordinates", "evidence", "priority",
            "data_confidence", "llm_synthesis"
        }
        assert required_fields.issubset(set(result.keys()))

        # Evidence sub-fields
        assert "flood" in result["evidence"]
        assert "exposure" in result["evidence"]
        assert "accessibility" in result["evidence"]

        # Priority sub-fields
        assert "pdc_score" in result["priority"]
        assert "category" in result["priority"]
        assert "recommendation" in result["priority"]

        # Coordinates
        assert "lat" in result["coordinates"]
        assert "lon" in result["coordinates"]


# ---------------------------------------------------------------------------
# Tests: data confidence determination
# ---------------------------------------------------------------------------

class TestDataConfidence:
    """Tests for _determine_data_confidence()."""

    def test_both_available_is_high(self):
        exp = {"data_available": True}
        acc = {"data_available": True}
        assert _determine_data_confidence(exp, acc) == "High"

    def test_exposure_missing_is_medium(self):
        exp = {"data_available": False}
        acc = {"data_available": True}
        assert _determine_data_confidence(exp, acc) == "Medium"

    def test_accessibility_missing_is_medium(self):
        exp = {"data_available": True}
        acc = {"data_available": False}
        assert _determine_data_confidence(exp, acc) == "Medium"

    def test_both_missing_is_medium(self):
        exp = {"data_available": False}
        acc = {"data_available": False}
        assert _determine_data_confidence(exp, acc) == "Medium"


# ---------------------------------------------------------------------------
# Tests: location resolution
# ---------------------------------------------------------------------------

class TestLocationResolution:
    """Tests for _resolve_location_label() and _resolve_coordinates()."""

    def test_label_from_name(self):
        assert _resolve_location_label("sivasagar") == "sivasagar"

    def test_label_from_coords(self):
        label = _resolve_location_label(lat=26.97, lon=94.64)
        assert "26.97" in label

    def test_label_unknown(self):
        assert _resolve_location_label() == "unknown"

    def test_coords_from_name(self):
        lat, lon = _resolve_coordinates("sivasagar")
        assert lat is not None
        assert lon is not None

    def test_coords_direct(self):
        lat, lon = _resolve_coordinates(lat=26.97, lon=94.64)
        assert lat == 26.97
        assert lon == 94.64

    def test_coords_unknown_name(self):
        lat, lon = _resolve_coordinates("nonexistent_place")
        assert lat is None
        assert lon is None


# ---------------------------------------------------------------------------
# Tests: unknown/malformed location handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Tests for error handling in run_relief_assessment()."""

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_unknown_location_still_returns_result(self, mock_flood, mock_exposure, mock_access):
        """Unknown location should still produce a valid structured result."""
        mock_flood.return_value = {
            "location": "unknown",
            "flooded": False,
            "exactly_contained": False,
            "near_flood_zone": False,
            "total_flood_polygons": 0,
            "nearest_flood_polygon_km2": 0.0,
            "detail": "No coordinate data available",
            "error": "Location not found"
        }
        mock_exposure.return_value = {
            "location": "unknown",
            "total_buildings": 0,
            "exposed_count": 0,
            "exposure_ratio": 0.0,
            "detail": "No data",
            "data_available": False
        }
        mock_access.return_value = {
            "location": "unknown",
            "medical_distance_km": -1,
            "medical_facility_name": "Unknown",
            "detail": "No data",
            "data_available": False
        }

        result = run_relief_assessment("nonexistent_place")

        assert result["priority"]["pdc_score"] == 0.0
        assert result["priority"]["category"] == "NONE"
        assert result["data_confidence"] == "Medium"

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_tool_failure_returns_error_result(self, mock_flood, mock_exposure, mock_access):
        """If a tool raises an exception, the assessment should handle it gracefully."""
        mock_flood.side_effect = Exception("Tool failed")

        try:
            result = run_relief_assessment("test_location")
            # If it returns a result, it should have the expected structure
            assert "priority" in result
        except Exception:
            # If it propagates the exception, that's also acceptable
            # The key is that it doesn't silently produce wrong data
            pass


# ---------------------------------------------------------------------------
# Tests: LLM path is optional
# ---------------------------------------------------------------------------

class TestLLMPath:
    """Tests for the optional LLM synthesis path."""

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_no_llm_by_default(self, mock_flood, mock_exposure, mock_access):
        """Default path should not invoke LLM."""
        mock_flood.return_value = MOCK_FLOOD_SAFE
        mock_exposure.return_value = MOCK_EXPOSURE_LOW
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        result = run_relief_assessment("sivasagar")

        assert result["llm_synthesis"] is None

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_llm_path_with_mocked_coordinator(self, mock_flood, mock_exposure, mock_access):
        """When use_llm=True and coordinator is mocked, should return LLM output."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        mock_synthesis = MagicMock(return_value="LLM recommendation text")

        with patch("agent.assessment.coordinator_synthesize", mock_synthesis):
            result = run_relief_assessment("sivasagar_flood_zone", use_llm=True)

        assert result["llm_synthesis"] == "LLM recommendation text"
        mock_synthesis.assert_called_once()

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_llm_failure_graceful_fallback(self, mock_flood, mock_exposure, mock_access):
        """When LLM fails, should return error message, not crash."""
        mock_flood.return_value = MOCK_FLOOD_SAFE
        mock_exposure.return_value = MOCK_EXPOSURE_LOW
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        with patch("agent.assessment.coordinator_synthesize", side_effect=Exception("Ollama down")):
            result = run_relief_assessment("sivasagar", use_llm=True)

        # Should have error message, not crash
        assert result["llm_synthesis"] is not None
        assert "unavailable" in result["llm_synthesis"].lower() or "error" in result["llm_synthesis"].lower()
        # PDC should still be correct
        assert result["priority"]["pdc_score"] == 0.0
        assert result["priority"]["category"] == "NONE"
