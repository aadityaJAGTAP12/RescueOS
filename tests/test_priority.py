"""
Tests for calculate_priority() — the v2 recalibrated PDC scoring formula.

These tests verify the deterministic scoring logic without any network calls.
"""

import pytest
from unittest.mock import patch
from agent.tools.allocation_tool import calculate_priority


class TestCalculatePrioritySafe:
    """Tests for non-flooded (SAFE) locations."""

    def test_no_flood_returns_zero(self):
        """SAFE location: flood_detected=False should always return 0.0."""
        result = calculate_priority(
            flood_detected=False,
            exposure_ratio=0.5,
            nearest_flood_polygon_km2=5.0,
            medical_distance_km=3.0,
            data_confidence="High",
        )
        assert result["pdc_score"] == 0.0
        assert result["category"] == "NONE"

    def test_no_flood_ignores_exposure(self):
        """SAFE location: high exposure is irrelevant when not flooded."""
        result = calculate_priority(
            flood_detected=False,
            exposure_ratio=1.0,
            nearest_flood_polygon_km2=10.0,
            medical_distance_km=20.0,
            data_confidence="High",
        )
        assert result["pdc_score"] == 0.0
        assert result["category"] == "NONE"


class TestCalculatePriorityFlooded:
    """Tests for flooded locations with varying parameters."""

    def test_flooded_low_exposure_near_medical(self):
        """Flooded, low exposure, nearby medical = lower score."""
        result = calculate_priority(
            flood_detected=True,
            exposure_ratio=0.06,
            nearest_flood_polygon_km2=4.88,
            medical_distance_km=2.5,
            data_confidence="High",
        )
        assert 0.0 <= result["pdc_score"] <= 1.0
        assert result["category"] in ("NONE", "SAFE", "EXPOSED", "PRIORITY", "HIGH PRIORITY")

    def test_flooded_high_exposure_far_medical(self):
        """Flooded, high exposure, far medical = higher score."""
        result_low = calculate_priority(
            flood_detected=True,
            exposure_ratio=0.06,
            nearest_flood_polygon_km2=4.88,
            medical_distance_km=2.5,
            data_confidence="High",
        )
        result_high = calculate_priority(
            flood_detected=True,
            exposure_ratio=0.6,
            nearest_flood_polygon_km2=4.88,
            medical_distance_km=12.0,
            data_confidence="High",
        )
        assert result_high["pdc_score"] > result_low["pdc_score"]

    def test_larger_flood_polygon_increases_score(self):
        """Larger flood polygon should increase score (35% weight)."""
        result_small = calculate_priority(
            flood_detected=True,
            exposure_ratio=0.3,
            nearest_flood_polygon_km2=1.0,
            medical_distance_km=8.0,
            data_confidence="High",
        )
        result_large = calculate_priority(
            flood_detected=True,
            exposure_ratio=0.3,
            nearest_flood_polygon_km2=8.0,
            medical_distance_km=8.0,
            data_confidence="High",
        )
        assert result_large["pdc_score"] >= result_small["pdc_score"]

    def test_unknown_medical_uses_default(self):
        """Unknown medical distance (medical_distance_km < 0) uses 0.5 accessibility score."""
        result = calculate_priority(
            flood_detected=True,
            exposure_ratio=0.3,
            nearest_flood_polygon_km2=3.0,
            medical_distance_km=-1,
            data_confidence="Medium",
        )
        assert result["pdc_score"] > 0.0
        assert result["category"] != "NONE"


class TestCalculatePriorityBoundaries:
    """Tests for category boundaries."""

    def test_high_priority_threshold(self):
        """Score >= 0.75 should be HIGH PRIORITY."""
        result = calculate_priority(
            flood_detected=True,
            exposure_ratio=1.0,
            nearest_flood_polygon_km2=10.0,
            medical_distance_km=20.0,
            data_confidence="High",
        )
        # With max inputs this should score very high
        assert result["pdc_score"] >= 0.75
        assert result["category"] == "HIGH PRIORITY"

    def test_exposed_threshold(self):
        """Score >= 0.25 should be at least EXPOSED."""
        result = calculate_priority(
            flood_detected=True,
            exposure_ratio=0.1,
            nearest_flood_polygon_km2=2.0,
            medical_distance_km=8.0,
            data_confidence="Medium",
        )
        assert result["pdc_score"] >= 0.25
        assert result["category"] in ("EXPOSED", "PRIORITY", "HIGH PRIORITY")

    def test_score_is_rounded_to_two_decimals(self):
        """PDC score should be rounded to 2 decimal places."""
        result = calculate_priority(
            flood_detected=True,
            exposure_ratio=0.3333,
            nearest_flood_polygon_km2=3.3333,
            medical_distance_km=7.7777,
            data_confidence="High",
        )
        # Verify rounding
        assert result["pdc_score"] == round(result["pdc_score"], 2)

    def test_score_range_bounded(self):
        """PDC score must always be between 0.0 and 1.0."""
        # Test with extreme values
        extremes = [
            (True, 0.0, 0.0, -1, "High"),
            (True, 1.0, 20.0, 30.0, "High"),
            (True, 0.5, 5.0, 10.0, "Medium"),
        ]
        for flood, exp, poly, med, conf in extremes:
            result = calculate_priority(
                flood_detected=flood,
                exposure_ratio=exp,
                nearest_flood_polygon_km2=poly,
                medical_distance_km=med,
                data_confidence=conf,
            )
            assert 0.0 <= result["pdc_score"] <= 1.0, (
                f"Score {result['pdc_score']} out of range for inputs: "
                f"exp={exp}, poly={poly}, med={med}"
            )

    def test_recommendation_present(self):
        """Every result should include a recommendation string."""
        result = calculate_priority(
            flood_detected=True,
            exposure_ratio=0.4,
            nearest_flood_polygon_km2=3.0,
            medical_distance_km=5.0,
            data_confidence="High",
        )
        assert "recommendation" in result
        assert isinstance(result["recommendation"], str)
        assert len(result["recommendation"]) > 0
