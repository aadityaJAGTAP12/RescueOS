"""
NGO Logistics Specialist Agent — Organization-level transport & access constraint evaluation.

Evaluates road overrides, access conditions, and delivery feasibility for private NGO deployments.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType


class NGOLogisticsAgent:
    """
    NGO Specialist Agent responsible for evaluating transport feasibility and access constraints.
    """
    agent_id: str = "ngo_specialist_logistics"
    name: str = "NGO Logistics Agent"
    domain: str = "logistics"
    allowed_context: list[str] = ["org_private_state", "shared_state"]
    allowed_tools: list[str] = ["road_status_tool"]
    accepted_event_types: list[str] = [
        AgentEventType.ROAD_OVERRIDE_APPLIED.value,
        AgentEventType.BRIDGE_OVERRIDE_APPLIED.value,
        AgentEventType.NEED_CREATED.value,
    ]

    def __init__(self, org_id: str):
        self.org_id = org_id

    def evaluate_access(self, shared_ctx: Any, location_name: Optional[str] = None) -> dict[str, Any]:
        """Check active road overrides affecting operations."""
        overrides = getattr(shared_ctx, "relevant_overrides", []) or []
        road_overrides = [o for o in overrides if o.get("target_type") == "road" and o.get("active", True)]
        blocked = [o for o in road_overrides if o.get("override_status") in ("blocked", "submerged", "damaged")]
        return {
            "total_overrides": len(road_overrides),
            "blocked_overrides": len(blocked),
            "blocked_details": blocked,
        }

    def analyze(self, shared_ctx: Any) -> list[AgentFinding]:
        """Analyze road/access conditions relevant to the organization."""
        access_info = self.evaluate_access(shared_ctx)
        blocked_count = access_info["blocked_overrides"]

        severity = FindingSeverity.URGENT.value if blocked_count > 0 else FindingSeverity.STABLE.value
        summary = f"{blocked_count} blocked road/corridor overrides in shared network picture" if blocked_count > 0 else "All monitored transit corridors passable"

        finding = AgentFinding(
            agent_id=self.agent_id,
            domain=self.domain,
            finding_type="access_evaluation",
            summary=summary,
            severity=severity,
            confidence=0.9,
            provenance=FindingProvenance.USER_PROVIDED,
            evidence=[{"blocked_count": blocked_count}],
        )
        return [finding]

    def handle_event(self, event: AgentEvent, shared_ctx: Any) -> list[AgentFinding]:
        """Process event affecting access or logistics."""
        return self.analyze(shared_ctx)
