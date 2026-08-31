"""
RescueOS Matching Service — Deterministic Need ↔ Offer matching.

This module provides a deterministic, explainable, testable matching service
that pairs needs with compatible resource offers. It does NOT create operations
automatically — it produces PROPOSED MATCHES that require human confirmation.

The matching service is designed to be:
- Deterministic: same inputs → same outputs
- Explainable: every match includes why it was proposed
- Testable: no external dependencies (LLM, APIs)
- Reusable: the future AI Coordinator can call this service

Architecture:
    Need → Matching Service → Candidate Offers → Human Confirmation → Operation

The matching service considers:
- Geographic compatibility (same district preferred)
- Resource type compatibility (structured, not just string equality)
- Quantity/capacity (partial vs complete fulfillment)
- Availability/status (exclude withdrawn/expired)
- Urgency ranking
- Operational relevance
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from agent.data.models import (
    Need,
    ResourceOffer,
    Provenance,
)


# -----------------------------------------------------------------------
# Resource type compatibility mapping
# -----------------------------------------------------------------------

# Maps resource types to canonical categories for matching.
# Uses the strongest structured representation available from the schema.
RESOURCE_CATEGORIES = {
    # Transport
    "boat": "transport",
    "boats": "transport",
    "vehicle": "transport",
    "vehicles": "transport",
    "transport": "transport",

    # Medical
    "medical_team": "medical",
    "medical": "medical",
    "doctor": "medical",
    "doctors": "medical",
    "nurse": "medical",
    "medicine": "medical",

    # Food
    "food": "food",
    "rice": "food",
    "ration": "food",
    "rations": "food",

    # Water
    "water": "water",
    "drinking_water": "water",

    # Shelter
    "shelter": "shelter",
    "tent": "shelter",
    "tents": "shelter",

    # Personnel
    "personnel": "personnel",
    "volunteer": "personnel",
    "volunteers": "personnel",

    # Rescue
    "rescue": "rescue",
    "rescue_team": "rescue",
}


def _canonical_category(resource_type: str) -> str:
    """Map a resource type string to a canonical category.

    Falls back to the lowercased input if not in the known mapping.
    """
    return RESOURCE_CATEGORIES.get(resource_type.lower(), resource_type.lower())


def _resources_compatible(need_type: str, offer_type: str) -> bool:
    """Check if a need's resource type is compatible with an offer's resource type.

    Uses canonical categories for comparison, falling back to substring matching
    for partial compatibility.
    """
    need_cat = _canonical_category(need_type)
    offer_cat = _canonical_category(offer_type)

    # Exact category match
    if need_cat == offer_cat:
        return True

    # Substring containment (e.g., "drinking_water" contains "water")
    if need_cat in offer_cat or offer_cat in need_cat:
        return True

    return False


# -----------------------------------------------------------------------
# Match result types
# -----------------------------------------------------------------------

@dataclass
class MatchCandidate:
    """A proposed match between a need and an offer."""
    need_id: str
    offer_id: str
    compatibility: str  # "HIGH", "MEDIUM", "LOW", "PARTIAL"
    score: float  # 0.0 to 1.0, higher = better match
    match_type: str  # "full", "partial", "cross_district"
    reasons: list[str]
    unmet_quantity: int  # 0 = fully satisfied, >0 = partially satisfied
    requested_quantity: int
    available_quantity: int
    allocatable_quantity: int  # min(requested, available)


# -----------------------------------------------------------------------
# Scoring helpers
# -----------------------------------------------------------------------

def _haversine_km(lon1: float, lat1: float, lon2: float, lon3: float = None, lat3: float = None) -> float:
    """Straight-line distance in km between two lon/lat points."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat3 or lat1)
    dphi = math.radians((lat3 or lat1) - lat1)
    dlambda = math.radians((lon3 or lon1) - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _urgency_weight(urgency: str) -> float:
    """Convert urgency string to numeric weight for ranking."""
    weights = {
        "critical": 1.0,
        "high": 0.75,
        "medium": 0.5,
        "low": 0.25,
    }
    return weights.get(urgency.lower(), 0.5)


# -----------------------------------------------------------------------
# Matching engine
# -----------------------------------------------------------------------

def find_matches_for_need(
    need: Need,
    offers: list[ResourceOffer],
    max_results: int = 10,
) -> list[MatchCandidate]:
    """
    Find compatible resource offers for a given need.

    This is the core deterministic matching algorithm. It considers:
    1. Resource type compatibility
    2. Geographic compatibility (same district preferred)
    3. Quantity/capacity
    4. Availability/status
    5. Urgency ranking

    Args:
        need: The need to find matches for
        offers: All available resource offers
        max_results: Maximum number of matches to return

    Returns:
        List of MatchCandidate, sorted by score (highest first)
    """
    candidates = []

    for offer in offers:
        # 1. Filter: only OFFERED status
        if offer.status not in ("OFFERED",):
            continue

        # 2. Resource type compatibility
        if not _resources_compatible(need.need_type, offer.resource_type):
            continue

        # 3. Build match candidate
        reasons = []
        score = 0.0

        # Geographic compatibility (same district)
        same_district = (
            need.district_id
            and offer.district_id
            and need.district_id == offer.district_id
        )
        if same_district:
            reasons.append(f"Same district: {need.district_id}")
            score += 0.3
        elif need.district_id and offer.district_id:
            reasons.append(f"Cross-district: need in {need.district_id}, offer from {offer.district_id}")
            match_type = "cross_district"
        else:
            reasons.append("District information partially unavailable")

        # Resource type compatibility
        need_cat = _canonical_category(need.need_type)
        offer_cat = _canonical_category(offer.resource_type)
        if need_cat == offer_cat:
            reasons.append(f"Resource type matches: {need.need_type} = {offer.resource_type}")
            score += 0.3
        else:
            reasons.append(f"Resource type compatible: {need.need_type} ~ {offer.resource_type}")
            score += 0.15

        # Quantity/capacity
        requested = _extract_quantity(need.requested_resources, need.need_type)
        available = offer.quantity or 0

        if requested > 0 and available > 0:
            if available >= requested:
                reasons.append(f"Sufficient capacity: {available} available >= {requested} requested")
                allocatable = requested
                score += 0.2
            else:
                reasons.append(f"Partial capacity: {available} available < {requested} requested")
                allocatable = available
                score += 0.1
            unmet = max(0, requested - available)
        elif available > 0:
            reasons.append(f"Offer available: {available} {offer.unit}")
            allocatable = available
            unmet = 0
            score += 0.15
        else:
            reasons.append("No quantity specified")
            allocatable = 0
            unmet = 0

        # Availability/status
        reasons.append(f"Offer is currently available (status: {offer.status})")
        score += 0.1

        # Urgency bonus
        urgency_w = _urgency_weight(need.urgency)
        score += urgency_w * 0.1
        if urgency_w >= 0.75:
            reasons.append(f"High urgency need: {need.urgency}")

        # Determine match type
        if same_district:
            if available >= (requested or 0) and requested > 0:
                match_type = "full"
            elif available > 0:
                match_type = "partial"
            else:
                match_type = "full"
        else:
            match_type = "cross_district"

        # Determine compatibility level
        if score >= 0.7:
            compatibility = "HIGH"
        elif score >= 0.4:
            compatibility = "MEDIUM"
        else:
            compatibility = "LOW"

        # Clamp score to 0-1
        score = min(1.0, max(0.0, score))

        candidates.append(MatchCandidate(
            need_id=need.id,
            offer_id=offer.id,
            compatibility=compatibility,
            score=score,
            match_type=match_type,
            reasons=reasons,
            unmet_quantity=unmet,
            requested_quantity=requested or 0,
            available_quantity=available,
            allocatable_quantity=allocatable,
        ))

    # Sort by score descending, then by offer quantity descending (prefer larger offers)
    candidates.sort(key=lambda c: (-c.score, -c.available_quantity))

    return candidates[:max_results]


def find_matches_for_need_id(
    need_id: str,
    offers: list[ResourceOffer],
    get_need_fn=None,
    max_results: int = 10,
) -> list[MatchCandidate]:
    """
    Find matches for a need by ID. Convenience wrapper.

    Args:
        need_id: The need ID to find matches for
        offers: All available resource offers
        get_need_fn: Function to retrieve a Need by ID (uses repo default if None)
        max_results: Maximum results

    Returns:
        List of MatchCandidate
    """
    if get_need_fn is None:
        from agent.data.repository import get_repository
        repo = get_repository()
        need = repo.get_need(need_id)
    else:
        need = get_need_fn(need_id)

    if need is None:
        return []

    return find_matches_for_need(need, offers, max_results=max_results)


# -----------------------------------------------------------------------
# Quantity extraction
# -----------------------------------------------------------------------

def _extract_quantity(requested_resources: list[dict], need_type: str) -> int:
    """Extract the total requested quantity from a need's requested_resources list.

    Tries to match the resource type to the need type, and sums quantities.
    Returns 0 if no structured quantity is available.
    """
    if not requested_resources:
        return 0

    total = 0
    for r in requested_resources:
        rtype = r.get("type", r.get("resource_type", "")).lower()
        # Match if the resource type contains the need type or vice versa
        if (need_type.lower() in rtype or rtype in need_type.lower()
                or _canonical_category(need_type) == _canonical_category(rtype)):
            qty = r.get("quantity", 0)
            if isinstance(qty, (int, float)):
                total += int(qty)

    return total


# -----------------------------------------------------------------------
# Format match for display
# -----------------------------------------------------------------------

def format_match_proposal(candidate: MatchCandidate, need: Need, offer: ResourceOffer) -> str:
    """Format a match candidate into a human-readable proposal.

    This is the text shown to the human coordinator before confirmation.
    """
    lines = []
    lines.append("MATCH PROPOSED")
    lines.append("")
    lines.append("Need:")
    lines.append(f"  {need.title or need.need_type}")
    lines.append(f"  Location: {need.location_name or need.district_id or 'unspecified'}")
    lines.append(f"  Urgency: {need.urgency}")
    lines.append("")
    lines.append("Offer:")
    lines.append(f"  {offer.quantity} {offer.resource_type}")
    lines.append(f"  Organization: {offer.organization_id}")
    lines.append(f"  Location: {offer.location_name or offer.district_id or 'unspecified'}")
    lines.append("")
    lines.append(f"Compatibility: {candidate.compatibility}")
    lines.append("")
    lines.append("Why:")
    for reason in candidate.reasons:
        lines.append(f"  • {reason}")
    lines.append("")
    lines.append("Capacity:")
    lines.append(f"  Requested: {candidate.requested_quantity}")
    lines.append(f"  Available: {candidate.available_quantity}")
    lines.append(f"  Potentially allocatable: {candidate.allocatable_quantity}")
    if candidate.unmet_quantity > 0:
        lines.append(f"  Unmet: {candidate.unmet_quantity}")

    return "\n".join(lines)
