"""
NGO Team Specialist Agent — Organization-level personnel & deployment readiness.

Operates strictly over PrivateOrganizationContext and never leaks internal personnel names.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType


class NGOTeamAgent:
    """
    NGO Specialist Agent responsible for private team readiness and deployment capacity.
    """
    agent_id: str = "ngo_specialist_team"
    name: str = "NGO Team Agent"
    domain: str = "team"
    allowed_context: list[str] = ["org_private_state", "shared_state"]
    allowed_tools: list[str] = []
    accepted_event_types: list[str] = [
        AgentEventType.NEED_CREATED.value,
        AgentEventType.COORDINATION_PROPOSAL_RECEIVED.value,
        AgentEventType.OPERATION_CREATED.value,
    ]

    def __init__(self, org_id: str):
        self.org_id = org_id

    def evaluate_team_readiness(self, private_ctx: Any) -> dict[str, Any]:
        """Evaluate available teams for deployment."""
        available_teams = private_ctx.get_available_teams()
        total_teams = len(private_ctx.teams)
        return {
            "available_teams": available_teams,
            "available_count": len(available_teams),
            "total_count": total_teams,
        }

    def analyze(self, private_ctx: Any) -> list[AgentFinding]:
        """Analyze overall team state for the organization."""
        readiness = self.evaluate_team_readiness(private_ctx)
        avail = readiness["available_count"]
        total = readiness["total_count"]

        finding = AgentFinding(
            agent_id=self.agent_id,
            domain=self.domain,
            finding_type="team_readiness_summary",
            summary=f"{avail} of {total} teams available for deployment",
            severity=FindingSeverity.STABLE.value if avail > 0 else FindingSeverity.URGENT.value,
            confidence=1.0,
            provenance=FindingProvenance.OBSERVED,
            evidence=[{"available_teams": avail, "total_teams": total}],
        )
        return [finding]

    def handle_event(self, event: AgentEvent, private_ctx: Any) -> list[AgentFinding]:
        """Process event requiring team deployment checks."""
        readiness = self.evaluate_team_readiness(private_ctx)
        avail = readiness["available_count"]

        summary = f"{avail} team(s) ready for assignment" if avail > 0 else "No team currently available for deployment"
        severity = FindingSeverity.STABLE.value if avail > 0 else FindingSeverity.URGENT.value

        return [
            AgentFinding(
                agent_id=self.agent_id,
                domain=self.domain,
                finding_type="team_availability",
                summary=summary,
                severity=severity,
                confidence=1.0,
                provenance=FindingProvenance.OBSERVED,
                evidence=[{"available_teams": avail}],
                related_entity_type=event.entity_type,
                related_entity_id=event.entity_id,
            )
        ]
