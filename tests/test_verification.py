"""
Tests for agent/verification.py — shared deterministic verification
utilities for LLM extraction guardrails.

Tests verify both fabrication detection (catching invented values) and
flexibility (allowing legitimately extracted values with unusual phrasing).
"""

import pytest
from agent.verification import (
    verify_numbers_against_source,
    verify_entity_mentioned,
    verify_all_numbers,
    verify_all_entities,
)


# ================================================================
# verify_numbers_against_source
# ================================================================

class TestVerifyNumbersAgainstSource:
    """Tests for the numeric fabrication detection guardrail."""

    def test_literal_number_passes(self):
        """Number that literally appears in source text is verified."""
        result = verify_numbers_against_source(400, "We have food for 400 families")
        assert result["verified"] is True
        assert result["note"] is None

    def test_fabricated_number_flagged(self):
        """Number NOT in source text is flagged as possible fabrication."""
        result = verify_numbers_against_source(35000, "Food for 5000 people for 7 days")
        assert result["verified"] is False
        assert "35000" in result["note"]
        assert "computed" in result["note"].lower() or "inferred" in result["note"].lower()

    def test_none_value_always_verified(self):
        """None (no number extracted) is always fine."""
        result = verify_numbers_against_source(None, "some food")
        assert result["verified"] is True

    def test_zero_in_source(self):
        """Zero appears in source text."""
        result = verify_numbers_against_source(0, "0 people reported")
        assert result["verified"] is True

    def test_large_number_in_source(self):
        """Large number that literally appears."""
        result = verify_numbers_against_source(5000, "We have 5000 kg of rice")
        assert result["verified"] is True

    def test_number_substring_false_positive(self):
        """Number '5' shouldn't match '50' — must be exact digit match."""
        result = verify_numbers_against_source(5, "50 families need food")
        assert result["verified"] is False

    def test_float_vs_int(self):
        """Float 35000.0 should match string '35000' in source."""
        result = verify_numbers_against_source(35000.0, "We need 35000 units")
        assert result["verified"] is True


# ================================================================
# verify_entity_mentioned
# ================================================================

class TestVerifyEntityMentioned:
    """Tests for the entity fabrication detection guardrail."""

    def test_exact_match_passes(self):
        """Entity that literally appears is verified."""
        result = verify_entity_mentioned(
            "Red Cross shelter",
            "People gathered at the Red Cross shelter near the school"
        )
        assert result["verified"] is True
        assert result["match_type"] == "exact"

    def test_fabricated_entity_flagged(self):
        """Entity NOT in source text is flagged."""
        result = verify_entity_mentioned(
            "Green Crescent Hospital",
            "People gathered at the Red Cross shelter"
        )
        assert result["verified"] is False
        assert result["match_type"] == "none"

    def test_case_insensitive_match(self):
        """Case differences don't prevent matching."""
        result = verify_entity_mentioned(
            "RED CROSS SHELTER",
            "People at the red cross shelter"
        )
        assert result["verified"] is True

    def test_punctuation_tolerant(self):
        """Minor punctuation differences don't prevent matching."""
        result = verify_entity_mentioned(
            "NH-702C",
            "The road NH702C is blocked"
        )
        assert result["verified"] is True

    def test_empty_entity_always_passes(self):
        """Empty entity string is always fine."""
        result = verify_entity_mentioned("", "some text")
        assert result["verified"] is True

    def test_fuzzy_match_nearby_road(self):
        """Close but not exact match should pass fuzzy threshold."""
        result = verify_entity_mentioned(
            "Bihubar Road near Santak High School",
            "Bihubar Road, Near Santak Hight School, Santak",
            threshold=0.6,
        )
        # Should match via fuzzy due to "Hight" vs "High" typo
        assert result["verified"] is True

    def test_fuzzy_match_fails_for_completely_different(self):
        """Completely different entity should fail fuzzy."""
        result = verify_entity_mentioned(
            "Main Street Hospital",
            "Bihubar Road near the school",
            threshold=0.6,
        )
        assert result["verified"] is False


# ================================================================
# verify_all_numbers (list wrapper)
# ================================================================

class TestVerifyAllNumbers:
    """Tests for the list-level number verification wrapper."""

    def test_marks_verified_items(self):
        """Items with numbers in source text are marked verified."""
        items = [
            {"quantity_numeric": 400},
            {"quantity_numeric": 200},
        ]
        result = verify_all_numbers(items, "We have 400 families and 200 bottles")
        assert result[0]["flagged_as_possible_fabrication"] is False
        assert result[1]["flagged_as_possible_fabrication"] is False

    def test_marks_fabricated_items(self):
        """Items with numbers NOT in source text are flagged."""
        items = [
            {"quantity_numeric": 35000},
        ]
        result = verify_all_numbers(items, "Food for 5000 people for 7 days")
        assert result[0]["flagged_as_possible_fabrication"] is True
        assert result[0]["verification_note"] is not None

    def test_null_quantity_passes(self):
        """Items with null quantity are not flagged."""
        items = [
            {"quantity_numeric": None},
        ]
        result = verify_all_numbers(items, "some food")
        assert result[0]["flagged_as_possible_fabrication"] is False

    def test_mixed_verified_and_fabricated(self):
        """Mix of legitimate and fabricated numbers."""
        items = [
            {"quantity_numeric": 400},
            {"quantity_numeric": 35000},
            {"quantity_numeric": None},
        ]
        result = verify_all_numbers(items, "400 families, food for 5000 people for 7 days")
        assert result[0]["flagged_as_possible_fabrication"] is False  # 400 in source
        assert result[1]["flagged_as_possible_fabrication"] is True   # 35000 not in source
        assert result[2]["flagged_as_possible_fabrication"] is False  # None is fine


# ================================================================
# verify_all_entities (list wrapper)
# ================================================================

class TestVerifyAllEntities:
    """Tests for the list-level entity verification wrapper."""

    def test_marks_verified_entities(self):
        """Entities found in source text are verified."""
        items = [
            {"road_description": "NH702C"},
        ]
        result = verify_all_entities(items, "The road NH702C is blocked", "road_description")
        assert result[0]["entity_verified"] is True

    def test_marks_fabricated_entities(self):
        """Entities NOT in source text are flagged."""
        items = [
            {"road_description": "Main Street Highway"},
        ]
        result = verify_all_entities(items, "The road NH702C is blocked", "road_description")
        assert result[0]["entity_verified"] is False
        assert result[0]["entity_verification_note"] is not None

    def test_empty_entity_passes(self):
        """Empty entity is always fine."""
        items = [
            {"facility_description": ""},
        ]
        result = verify_all_entities(items, "some text", "facility_description")
        assert result[0]["entity_verified"] is True
