"""Shared deterministic facts for Need-to-resource comparisons."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


RESOURCE_CATEGORIES = {
    "boat": "transport",
    "boats": "transport",
    "vehicle": "transport",
    "vehicles": "transport",
    "transport": "transport",
    "medical_team": "medical",
    "medical": "medical",
    "doctor": "medical",
    "doctors": "medical",
    "nurse": "medical",
    "medicine": "medical",
    "food": "food",
    "rice": "food",
    "ration": "food",
    "rations": "food",
    "water": "water",
    "drinking_water": "water",
    "shelter": "shelter",
    "tent": "shelter",
    "tents": "shelter",
    "personnel": "personnel",
    "volunteer": "personnel",
    "volunteers": "personnel",
    "rescue": "rescue",
    "rescue_team": "rescue",
}


@dataclass(frozen=True)
class MatchFacts:
    """Facts only; this type contains no recommendation or interpretation."""

    available_quantity: int | float
    requested_quantity: Optional[int | float]
    requested_quantity_specified: bool
    available_unit: Optional[str]
    requested_unit: Optional[str]
    unit_match: bool
    unit_mismatch: bool
    type_match: bool
    sufficiency: str  # sufficient, insufficient, or unknown

    def to_dict(self) -> dict:
        return asdict(self)


def canonical_category(resource_type: str) -> str:
    value = (resource_type or "").strip().lower()
    return RESOURCE_CATEGORIES.get(value, value)


def types_match(need_type: str, resource_type: str) -> bool:
    need = (need_type or "").strip().lower()
    resource = (resource_type or "").strip().lower()
    if not need or not resource:
        return False
    return (
        need == resource
        or need in resource
        or resource in need
        or canonical_category(need) == canonical_category(resource)
    )


def _numeric_quantity(value) -> int | float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _requested_for_type(
    requested_resources: list[dict] | None,
    need_type: str,
    resource_type: str,
) -> tuple[Optional[int | float], Optional[str], bool]:
    """Return requested quantity/unit for entries compatible with this resource."""
    entries = requested_resources or []
    matching = []
    for entry in entries:
        entry_type = entry.get("type", entry.get("resource_type", ""))
        if types_match(need_type or resource_type, entry_type) or types_match(resource_type, entry_type):
            matching.append(entry)

    if not matching:
        return None, None, False

    quantities = [
        entry.get("quantity")
        for entry in matching
        if isinstance(entry.get("quantity"), (int, float)) and not isinstance(entry.get("quantity"), bool)
    ]
    requested = sum(quantities) if quantities else None
    units = {entry.get("unit") for entry in matching if entry.get("unit")}
    requested_unit = next(iter(units)) if len(units) == 1 else None
    return requested, requested_unit, requested is not None


def compare_need_resource(
    requested_resources: list[dict] | None,
    resource_type: str,
    quantity,
    unit: str | None,
    need_type: str = "",
) -> MatchFacts:
    """Compare one resource/offer to a Need using only structured facts."""
    available = _numeric_quantity(quantity)
    type_match = types_match(need_type or resource_type, resource_type)
    requested, requested_unit, specified = _requested_for_type(
        requested_resources, need_type, resource_type
    )

    unit_match = not requested_unit or not unit or requested_unit.lower() == unit.lower()
    unit_mismatch = specified and not unit_match

    if not type_match or unit_mismatch:
        sufficiency = "insufficient" if type_match and unit_mismatch else "unknown"
    elif requested is None:
        sufficiency = "unknown"
    elif available >= requested:
        sufficiency = "sufficient"
    else:
        sufficiency = "insufficient"

    return MatchFacts(
        available_quantity=available,
        requested_quantity=requested,
        requested_quantity_specified=specified,
        available_unit=unit,
        requested_unit=requested_unit,
        unit_match=unit_match,
        unit_mismatch=unit_mismatch,
        type_match=type_match,
        sufficiency=sufficiency,
    )
