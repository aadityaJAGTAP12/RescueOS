"""
NGO Mission Specialist Agent — Organization-level mission status & conflict evaluation.

Operates strictly over PrivateOrganizationContext and prevents double-allocation of resources.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType


class NGOMissionAgent:
    """
    NGO Specialist Agent responsible for evaluating active missions, resource commitments,
    and operational conflicts.
    """
    agent_id: str = "ngo_specialist_mission"
    name: str = "NGO Mission Agent"
    domain: str = "mission"
    allowed_context: list[str] = ["org_private_state", "shared_state"]
    allowed_tools: list[str] = []
    accepted_event_types: list[str] = [
        AgentEventType.OPERATION_CREATED.value,
        AgentEventType.OPERATION_STATUS_CHANGED.value,
        AgentEventType.COORDINATION_PROPOSAL_RECEIVED.value,
    ]

    def __init__(self, org_id: str):
        self.org_id = org_id

    def evaluate_mission_conflicts(self, resource_type: str, quantity: int, private_ctx: Any) -> tuple[bool, str]:
        """Check if an operation or response would conflict with active missions."""
        return private_ctx.has_resource_conflict(resource_type, quantity)

    def analyze(self, private_ctx: Any) -> list[AgentFinding]:
        """Analyze overall mission load for the organization."""
        active = private_ctx.get_active_missions()
        committed = private_ctx.get_committed_resources()

        finding = AgentFinding(
            agent_id=self.agent_id,
            domain=self.domain,
            finding_type="mission_load_summary",
            summary=f"{len(active)} active missions with {len(committed)} committed resource allocations",
            severity=FindingSeverity.STABLE.value,
            confidence=1.0,
            provenance=FindingProvenance.OBSERVED,
            evidence=[{"active_missions": len(active), "committed_resources": len(committed)}],
        )
        return [finding]

    def handle_event(self, event: AgentEvent, private_ctx: Any, resource_type: Optional[str] = None, quantity: int = 1) -> list[AgentFinding]:
        """Check if an event generates a conflict with existing missions."""
        r_type = resource_type or event.metadata.get("resource_type", "other")
        qty = quantity or event.metadata.get("quantity", 1)

        has_conflict, reason = self.evaluate_mission_conflicts(r_type, qty, private_ctx)

        if has_conflict:
            finding = AgentFinding(
                agent_id=self.agent_id,
                domain=self.domain,
                finding_type="mission_conflict",
                summary=f"Mission conflict: {reason}",
                severity=FindingSeverity.URGENT.value,
                confidence=1.0,
                provenance=FindingProvenance.OBSERVED,
                evidence=[{"conflict_reason": reason}],
                related_entity_type=event.entity_type,
                related_entity_id=event.entity_id,
            )
        else:
            finding = AgentFinding(
                agent_id=self.agent_id,
                domain=self.domain,
                finding_type="mission_fit",
                summary="No conflict detected with active missions",
                severity=FindingSeverity.STABLE.value,
                confidence=1.0,
                provenance=FindingProvenance.OBSERVED,
                related_entity_type=event.entity_type,
                related_entity_id=event.entity_id,
            )

        return [finding]
