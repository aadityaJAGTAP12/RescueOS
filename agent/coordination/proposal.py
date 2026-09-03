"""
CoordinationProposal — Structured coordination between Network and NGO.

Phase 7H: The coordination proposal sits above the existing collaboration
lifecycle (Need → Offer → Match → Confirm → Operation).

Lifecycle:
    PROPOSED → PENDING_ORG_REVIEW → ORG_RECOMMENDED → PENDING_HUMAN_APPROVAL
    → PUBLISHED → CONFIRMED → COMPLETED

    Or: DECLINED / EXPIRED at any point before PUBLISHED.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PROPOSALS_FILE = os.path.join(_DATA_DIR, "coordination_proposals.json")


def _load_proposals() -> list[dict]:
    if not os.path.exists(PROPOSALS_FILE):
        return []
    try:
        with open(PROPOSALS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_proposals(proposals: list[dict]) -> None:
    os.makedirs(os.path.dirname(PROPOSALS_FILE), exist_ok=True)
    with open(PROPOSALS_FILE, "w") as f:
        json.dump(proposals, f, indent=2)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_proposal(
    need_id: str,
    organization_id: str,
    organization_name: str,
    proposal_type: str,
    summary: str,
    public_evidence: list[dict] = None,
    network_findings: list[dict] = None,
    constraints: list[str] = None,
    uncertainty: list[str] = None,
    recommended_action: str = "",
) -> dict:
    """Create a new coordination proposal."""
    proposal = {
        "id": f"prop_{str(uuid.uuid4())[:8]}",
        "need_id": need_id,
        "organization_id": organization_id,
        "organization_name": organization_name,
        "proposal_type": proposal_type,  # "resource_support" | "medical_support" | "logistics_support" | "other"
        "summary": summary,
        "public_evidence": public_evidence or [],
        "network_findings": network_findings or [],
        "constraints": constraints or [],
        "uncertainty": uncertainty or [],
        "recommended_action": recommended_action,
        "status": "PROPOSED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "approved_at": None,
        "approved_by": None,
        "published_offer_id": None,
        "operation_id": None,
        "org_evaluation": None,  # Private evaluation from NGO (never exposed to network)
        "private_factors": None,  # Private factors from NGO (never exposed to network)
    }
    proposals = _load_proposals()
    proposals.append(proposal)
    _save_proposals(proposals)
    return proposal


def get_proposal(proposal_id: str) -> Optional[dict]:
    """Get a specific proposal."""
    proposals = _load_proposals()
    for p in proposals:
        if p["id"] == proposal_id:
            return p
    return None


def list_proposals(
    need_id: str = None,
    organization_id: str = None,
    status: str = None,
) -> list[dict]:
    """List proposals with optional filters."""
    proposals = _load_proposals()
    if need_id:
        proposals = [p for p in proposals if p["need_id"] == need_id]
    if organization_id:
        proposals = [p for p in proposals if p["organization_id"] == organization_id]
    if status:
        proposals = [p for p in proposals if p["status"] == status]
    return proposals


def update_proposal(proposal_id: str, updates: dict) -> Optional[dict]:
    """Update a proposal."""
    proposals = _load_proposals()
    for p in proposals:
        if p["id"] == proposal_id:
            p.update(updates)
            p["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_proposals(proposals)
            return p
    return None


def send_to_org(proposal_id: str) -> Optional[dict]:
    """Send proposal to NGO for evaluation (transitions to PENDING_ORG_REVIEW)."""
    return update_proposal(proposal_id, {"status": "PENDING_ORG_REVIEW"})


def record_org_evaluation(
    proposal_id: str,
    evaluation: dict,
    private_factors: list[str],
) -> Optional[dict]:
    """
    Record NGO's private evaluation.

    IMPORTANT: private_factors are stored but NEVER exposed to the network.
    Only the public parts of the evaluation cross the boundary.
    """
    return update_proposal(proposal_id, {
        "status": "ORG_RECOMMENDED",
        "org_evaluation": evaluation,
        "private_factors": private_factors,
    })


def approve_publication(proposal_id: str, approved_by: str = "human") -> Optional[dict]:
    """Human approves publication (transitions to PENDING_HUMAN_APPROVAL → PUBLISHED)."""
    return update_proposal(proposal_id, {
        "status": "PUBLISHED",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": approved_by,
    })


def decline_proposal(proposal_id: str) -> Optional[dict]:
    """Decline a proposal."""
    return update_proposal(proposal_id, {"status": "DECLINED"})


def expire_proposal(proposal_id: str) -> Optional[dict]:
    """Expire a proposal."""
    return update_proposal(proposal_id, {"status": "EXPIRED"})


def link_offer(proposal_id: str, offer_id: str) -> Optional[dict]:
    """Link a published Resource Offer to the proposal."""
    return update_proposal(proposal_id, {
        "published_offer_id": offer_id,
        "status": "CONFIRMED",
    })


def link_operation(proposal_id: str, operation_id: str) -> Optional[dict]:
    """Link an Operation to the proposal."""
    return update_proposal(proposal_id, {"operation_id": operation_id})


# ---------------------------------------------------------------------------
# Public view (safe for network)
# ---------------------------------------------------------------------------

def get_public_view(proposal: dict) -> dict:
    """
    Return only the public parts of a proposal.
    Strips private_factors and org_evaluation details.
    """
    return {
        "id": proposal.get("id"),
        "need_id": proposal.get("need_id"),
        "organization_id": proposal.get("organization_id"),
        "organization_name": proposal.get("organization_name"),
        "proposal_type": proposal.get("proposal_type"),
        "summary": proposal.get("summary"),
        "public_evidence": proposal.get("public_evidence", []),
        "network_findings": proposal.get("network_findings", []),
        "constraints": proposal.get("constraints", []),
        "uncertainty": proposal.get("uncertainty", []),
        "recommended_action": proposal.get("recommended_action"),
        "status": proposal.get("status"),
        "created_at": proposal.get("created_at"),
        "updated_at": proposal.get("updated_at"),
        "published_offer_id": proposal.get("published_offer_id"),
        "operation_id": proposal.get("operation_id"),
        # NOTE: org_evaluation and private_factors are EXCLUDED
    }


def get_org_view(proposal: dict) -> dict:
    """
    Return the proposal view for the NGO (includes evaluation status).
    Still excludes raw private_factors in the public response.
    """
    public = get_public_view(proposal)
    # Add evaluation status (not the raw private data)
    if proposal.get("org_evaluation"):
        public["org_evaluation_status"] = proposal["org_evaluation"].get("decision", "PENDING")
    return public
