"""Tests for shared deterministic Need/resource facts."""

from agent.matching_core import compare_need_resource


def test_specified_quantity_is_sufficient():
    facts = compare_need_resource(
        [{"type": "food", "quantity": 2000, "unit": "kg"}],
        "food",
        5000,
        "kg",
        "food",
    )
    assert facts.requested_quantity == 2000
    assert facts.requested_quantity_specified is True
    assert facts.unit_match is True
    assert facts.sufficiency == "sufficient"


def test_specified_quantity_is_insufficient():
    facts = compare_need_resource(
        [{"type": "food", "quantity": 5000, "unit": "kg"}],
        "food",
        2000,
        "kg",
        "food",
    )
    assert facts.sufficiency == "insufficient"


def test_unspecified_quantity_reports_real_available_amount():
    facts = compare_need_resource([], "food", 5000, "kg", "food")
    assert facts.available_quantity == 5000
    assert facts.requested_quantity is None
    assert facts.requested_quantity_specified is False
    assert facts.sufficiency == "unknown"


def test_unit_mismatch_is_flagged_without_conversion():
    facts = compare_need_resource(
        [{"type": "food", "quantity": 2000, "unit": "kg"}],
        "food",
        5000,
        "liters",
        "food",
    )
    assert facts.unit_match is False
    assert facts.unit_mismatch is True
    assert facts.sufficiency == "insufficient"
