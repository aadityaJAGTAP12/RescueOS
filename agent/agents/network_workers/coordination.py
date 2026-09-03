"""
Coordination Worker — Network-level coordination analysis.

Identifies uncovered needs, available offers, possible pairings,
duplicate responses, and coordination opportunities.
"""

from __future__ import annotations


def analyze_coordination(repo) -> dict:
    """
    Analyze coordination state: needs vs offers, response gaps,
    duplicate coverage.
    """
    findings = []
    evidence = []
    uncertainty = []
    data_gaps = []
    recommendations = []

    needs = repo.list_needs(status="OPEN") if hasattr(repo, 'list_needs') else []
    offers = repo.list_resource_offers(status="OFFERED") if hasattr(repo, 'list_resource_offers') else []
    operations = repo.list_operations() if hasattr(repo, 'list_operations') else []

    evidence.append({
        "type": "coordination_summary",
        "detail": f"{len(needs)} open needs, {len(offers)} published offers, {len(operations)} total operations",
    })

    # Uncovered needs
    for need in needs:
        need_id = need.id if hasattr(need, 'id') else need.get('id', '')
        need_type = need.need_type if hasattr(need, 'need_type') else need.get('need_type', '')
        urgency = need.urgency if hasattr(need, 'urgency') else need.get('urgency', 'medium')

        # Check for linked operations
        linked_ops = [o for o in operations if (o.need_id if hasattr(o, 'need_id') else o.get('need_id')) == need_id]
        # Check for matching offers
        matching_offers = [o for o in offers if _types_match(
            need_type, o.resource_type if hasattr(o, 'resource_type') else o.get('resource_type', '')
        )]

        if not linked_ops and not matching_offers:
            findings.append({
                "type": "uncovered_need",
                "severity": "critical" if urgency == "critical" else "urgent" if urgency == "high" else "information",
                "title": f"Uncovered {need_type} need",
                "summary": f"Need '{need.title if hasattr(need, 'title') else need.get('title', '')}' has no responders",
                "location": need.location_name if hasattr(need, 'location_name') else need.get('location_name', ''),
                "entity_type": "need",
                "entity_id": need_id,
            })

    # Coordination opportunities (offers with no needs)
    for offer in offers:
        otype = offer.resource_type if hasattr(offer, 'resource_type') else offer.get('resource_type', '')
        matching_needs = [n for n in needs if _types_match(
            n.need_type if hasattr(n, 'need_type') else n.get('need_type', ''), otype
        )]
        if not matching_needs:
            org_id = offer.organization_id if hasattr(offer, 'organization_id') else offer.get('organization_id', '')
            findings.append({
                "type": "surplus_offer",
                "severity": "information",
                "title": f"Published {otype} offer with no matching need",
                "summary": f"{org_id} has published {otype} but no open need matches",
            })

    return _build_result(findings, evidence, uncertainty, data_gaps, recommendations)


def _types_match(need_type: str, offer_type: str) -> bool:
    if not need_type or not offer_type:
        return False
    n, o = need_type.lower(), offer_type.lower()
    if n == o or n in o or o in n:
        return True
    categories = {"boat": "transport", "vehicle": "transport", "medical_team": "medical", "food": "supplies", "water": "supplies"}
    return categories.get(n) == categories.get(o) and categories.get(n) is not None


def _build_result(findings, evidence, uncertainty, data_gaps, recommendations):
    return {
        "worker": "coordination",
        "findings": findings,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "recommendations": recommendations,
    }
