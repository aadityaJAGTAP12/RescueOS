"""
Publication — Convert approved NGO evaluation into public Resource Offer.

Phase 7H: When the human approves publication, the approved result
is converted into an existing public Resource Offer.

Only fields explicitly approved for publication cross the boundary.
"""

from __future__ import annotations


def create_public_offer_from_proposal(
    proposal: dict,
    org_evaluation: dict,
    org_id: str,
    repo=None,
) -> dict:
    """
    Create a public Resource Offer from an approved coordination proposal.

    This is the critical privacy boundary: only approved public fields
    are used. Private factors are NEVER included.

    Returns:
        {
            "offer": {...},  # The created Resource Offer
            "proposal_id": str,
            "message": str,
        }
    """
    if repo is None:
        from agent.data.repository import get_repository
        repo = get_repository()

    import uuid
    from agent.data.models import ResourceOffer, ActivityEvent

    need_id = proposal.get("need_id", "")
    proposal_type = proposal.get("proposal_type", "other")
    constraints = proposal.get("constraints", [])

    # Determine resource type and quantity from evaluation
    resource_assessment = org_evaluation.get("resource_assessment", {})
    matching_available = resource_assessment.get("matching_available", 0)

    if matching_available <= 0:
        return {"offer": None, "proposal_id": proposal.get("id"), "message": "No available resources to publish"}

    # Create the public offer — ONLY approved public fields
    offer_id = f"offer_{str(uuid.uuid4())[:8]}"
    offer = ResourceOffer(
        id=offer_id,
        organization_id=org_id,
        resource_type=proposal_type,
        quantity=min(matching_available, 1),  # Conservative: publish 1 unit unless specified
        unit="units",
        lat=None,  # Not published from private state
        lon=None,
        location_name=None,  # Not published from private state
        district_id=None,
        status="OFFERED",
        notes=f"Coordination response to Need {need_id}" + (f" — Constraints: {'; '.join(constraints)}" if constraints else ""),
    )
    result = repo.create_resource_offer(offer)

    # Record activity
    repo.append_activity_event(ActivityEvent(
        id=f"evt_{str(uuid.uuid4())[:8]}",
        entity_type="resource_offer",
        entity_id=offer_id,
        event_type="resource_offered",
        actor=org_id,
        detail=f"Published coordination offer: {offer.quantity} {offer.resource_type} (proposal: {proposal.get('id', '')})",
    ))

    return {
        "offer": result.to_dict(),
        "proposal_id": proposal.get("id"),
        "message": "Offer published to network",
    }


def extract_public_fields(evaluation: dict) -> dict:
    """
    Extract only the public fields from an NGO evaluation.

    This ensures private factors never cross the boundary.
    """
    return {
        "decision": evaluation.get("decision", ""),
        "public_summary": evaluation.get("public_summary", ""),
        "constraints": evaluation.get("constraints", []),
        "recommended_public_action": evaluation.get("recommended_public_action", ""),
        "resource_assessment": {
            "matching_available": evaluation.get("resource_assessment", {}).get("matching_available", 0),
        },
        # NOTE: private_factors are EXCLUDED
    }
