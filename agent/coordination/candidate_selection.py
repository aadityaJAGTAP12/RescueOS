"""
Candidate Selection — Identify candidate organizations using ONLY public information.

Phase 7H: The Network identifies possible organizations for a Need
based on published offers, public organization info, and geographic relevance.
"""

from __future__ import annotations


def select_candidates(
    need: dict,
    repo=None,
) -> list[dict]:
    """
    Select candidate organizations for a Need using only public information.

    Returns ranked list of candidates with evidence.
    """
    if repo is None:
        from agent.data.repository import get_repository
        repo = get_repository()

    need_type = need.get("need_type", "")
    need_lat = need.get("lat")
    need_lon = need.get("lon")
    need_district = need.get("district_id", "")

    candidates = []

    # Get all organizations
    orgs = repo.list_organizations() if hasattr(repo, 'list_organizations') else []
    org_map = {o.id: o for o in orgs if hasattr(o, 'id')} if orgs else {}

    # Get all published offers
    offers = repo.list_resource_offers(status="OFFERED") if hasattr(repo, 'list_resource_offers') else []

    # Get all operations for org history
    operations = repo.list_operations() if hasattr(repo, 'list_operations') else []

    # Group offers by organization
    offers_by_org = {}
    for offer in offers:
        org_id = offer.organization_id if hasattr(offer, 'organization_id') else offer.get('organization_id', '')
        offers_by_org.setdefault(org_id, []).append(offer)

    # Group operations by organization
    ops_by_org = {}
    for op in operations:
        org_id = op.lead_organization_id if hasattr(op, 'lead_organization_id') else op.get('lead_organization_id', '')
        if org_id:
            ops_by_org.setdefault(org_id, []).append(op)

    # Evaluate each organization
    for org_id, org_offers in offers_by_org.items():
        # Check if any offer matches the need type
        matching_offers = [
            o for o in org_offers
            if _types_match(need_type, o.resource_type if hasattr(o, 'resource_type') else o.get('resource_type', ''))
        ]

        if not matching_offers:
            continue

        # Score the candidate
        score = 0.0
        evidence = []
        constraints = []
        uncertainty = []

        # Geographic relevance
        for offer in matching_offers:
            o_lat = offer.lat if hasattr(offer, 'lat') else offer.get('lat')
            o_lon = offer.lon if hasattr(offer, 'lon') else offer.get('lon')
            o_district = offer.district_id if hasattr(offer, 'district_id') else offer.get('district_id', '')

            if o_district and need_district and o_district == need_district:
                score += 0.4
                evidence.append(f"Same district: {o_district}")
            elif o_lat and o_lon and need_lat and need_lon:
                from agent.data_loader import haversine_km
                dist = haversine_km(o_lon, o_lat, need_lon, need_lat)
                if dist < 50:
                    score += 0.3
                    evidence.append(f"Nearby: {dist:.0f}km")
                elif dist < 100:
                    score += 0.2
                    evidence.append(f"Regional: {dist:.0f}km")
                else:
                    uncertainty.append(f"Distant: {dist:.0f}km")

        # Resource quantity
        total_quantity = sum(
            o.quantity if hasattr(o, 'quantity') else o.get('quantity', 0)
            for o in matching_offers
        )
        if total_quantity > 0:
            score += 0.2
            evidence.append(f"{total_quantity} units available (public)")

        # Previous operations
        org_ops = ops_by_org.get(org_id, [])
        if org_ops:
            score += 0.1
            evidence.append(f"{len(org_ops)} previous public operations")

        # Organization info
        org = org_map.get(org_id)
        org_name = org.name if hasattr(org, 'name') else org_id if org else org_id
        org_type = org.organization_type if hasattr(org, 'organization_type') else "unknown" if org else "unknown"

        # Build candidate
        candidate = {
            "organization_id": org_id,
            "organization_name": org_name,
            "organization_type": org_type,
            "score": min(1.0, score),
            "evidence": evidence,
            "constraints": constraints,
            "uncertainty": uncertainty,
            "matching_offers": len(matching_offers),
            "total_public_quantity": total_quantity,
            "previous_operations": len(org_ops),
        }

        # Add offer details
        if matching_offers:
            best_offer = matching_offers[0]
            candidate["offer_type"] = best_offer.resource_type if hasattr(best_offer, 'resource_type') else best_offer.get('resource_type', '')
            candidate["offer_quantity"] = best_offer.quantity if hasattr(best_offer, 'quantity') else best_offer.get('quantity', 0)

        candidates.append(candidate)

    # Sort by score descending
    candidates.sort(key=lambda c: c["score"], reverse=True)

    return candidates


def _types_match(need_type: str, offer_type: str) -> bool:
    if not need_type or not offer_type:
        return False
    n, o = need_type.lower(), offer_type.lower()
    if n == o or n in o or o in n:
        return True
    categories = {"boat": "transport", "vehicle": "transport", "medical_team": "medical", "food": "supplies", "water": "supplies"}
    return categories.get(n) == categories.get(o) and categories.get(n) is not None
