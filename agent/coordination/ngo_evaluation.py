"""
NGO Private Evaluation — Evaluate coordination proposals using private state.

Phase 7H: When the NGO Main Agent receives a coordination request,
it evaluates using private resources, teams, missions, and commitments.

PRIVATE factors never cross the boundary to the network.
"""

from __future__ import annotations

from agent.matching_core import compare_need_resource, types_match


def evaluate_coordination(
    proposal: dict,
    org_id: str,
) -> dict:
    """
    NGO Main Agent privately evaluates a coordination proposal.

    Returns:
        {
            "proposal_id": str,
            "org_id": str,
            "decision": "SUITABLE" | "POTENTIALLY_SUITABLE" | "UNAVAILABLE" | "CONFLICT" | "INSUFFICIENT_INFO",
            "public_summary": str,  # Safe for network
            "private_factors": list[str],  # NEVER exposed to network
            "constraints": list[str],
            "recommended_public_action": str,
            "resource_assessment": {...},
            "team_assessment": {...},
            "mission_assessment": {...},
        }
    """
    from agent.org_workspace import list_resources, list_teams, list_missions

    # Load private state
    resources = list_resources(org_id)
    teams = list_teams(org_id)
    missions = list_missions(org_id)

    need_type = proposal.get("proposal_type", "")
    need_id = proposal.get("need_id", "")
    requested_resources = proposal.get("requested_resources", [])

    # Resource assessment
    available_resources = [r for r in resources if r.get("status") == "available"]
    matching_resources = []
    resource_facts = []
    for resource in available_resources:
        facts = compare_need_resource(
            requested_resources,
            resource.get("type", resource.get("resource_type", "")),
            resource.get("quantity", 0),
            resource.get("unit"),
            need_type,
        )
        if facts.type_match:
            matching_resources.append(resource)
            resource_facts.append(facts)
    total_available = sum(r.get("quantity", 0) for r in matching_resources)
    requested_quantity = next(
        (facts.requested_quantity for facts in resource_facts if facts.requested_quantity is not None),
        None,
    )
    unit_match = all(facts.unit_match for facts in resource_facts)
    matching_facts = {
        "available_quantity": total_available,
        "requested_quantity": requested_quantity,
        "requested_quantity_specified": requested_quantity is not None,
        "unit_match": unit_match,
        "unit_mismatch": not unit_match,
        "type_match": bool(resource_facts),
        "sufficiency": (
            "unknown" if requested_quantity is None or not unit_match
            else "sufficient" if total_available >= requested_quantity
            else "insufficient"
        ),
    }

    # Team assessment
    available_teams = [t for t in teams if t.get("status") == "available"]

    # Mission assessment
    active_missions = [m for m in missions if m.get("status") in ("ACTIVE", "READY")]
    conflicting_missions = []
    for m in active_missions:
        assigned = m.get("assigned_resources", [])
        for ar in assigned:
            if _resource_matches_need(ar, need_type):
                conflicting_missions.append(m)

    # Decision logic
    decision = "INSUFFICIENT_INFO"
    public_summary = "Unable to evaluate — insufficient information"
    private_factors = []
    constraints = []
    recommended_public_action = "No action recommended"

    if not unit_match and resource_facts:
        constraints.append("Resource and Need units require human verification")

    if total_available > 0 and available_teams and not conflicting_missions:
        decision = "SUITABLE"
        public_summary = f"Organization can provide {need_type} support"
        private_factors = [
            f"{total_available} compatible resources available",
            f"{len(available_teams)} teams available",
            f"{len(active_missions)} active missions (no conflicts)",
        ]
        recommended_public_action = f"Publish a {need_type} support offer"
    elif total_available > 0 and not available_teams:
        decision = "POTENTIALLY_SUITABLE"
        public_summary = f"Resources may be available but team assignment is uncertain"
        private_factors = [
            f"{total_available} compatible resources available",
            "No team currently available",
        ]
        constraints.append("Team availability requires verification")
        recommended_public_action = "Conditional offer pending team confirmation"
    elif total_available > 0 and conflicting_missions:
        decision = "CONFLICT"
        public_summary = f"Resources may conflict with active missions"
        private_factors = [
            f"{total_available} compatible resources available",
            f"{len(conflicting_missions)} mission(s) may require same resource type",
        ]
        constraints.append("Resource commitment may affect existing missions")
        recommended_public_action = "Review mission priorities before committing"
    else:
        decision = "UNAVAILABLE"
        public_summary = f"No available {need_type} resources in inventory"
        private_factors = [
            f"0 compatible resources available",
            f"{len(resources)} total resources (none matching or available)",
        ]
        recommended_public_action = "Cannot respond at this time"

    return {
        "proposal_id": proposal.get("id", ""),
        "org_id": org_id,
        "decision": decision,
        "public_summary": public_summary,
        "private_factors": private_factors,  # NEVER exposed to network
        "constraints": constraints,
        "recommended_public_action": recommended_public_action,
        "resource_assessment": {
            "total_resources": len(resources),
            "matching_available": len(matching_resources),
            "total_available_quantity": total_available,
            "matching_facts": matching_facts,
        },
        "team_assessment": {
            "total_teams": len(teams),
            "available_teams": len(available_teams),
        },
        "mission_assessment": {
            "active_missions": len(active_missions),
            "conflicting_missions": len(conflicting_missions),
        },
    }


def _resource_matches_need(resource: dict, need_type: str) -> bool:
    """Check if a resource matches a need type."""
    r_type = resource.get("type", resource.get("resource_type", "")).lower()
    n_type = need_type.lower()
    return types_match(n_type, r_type)
