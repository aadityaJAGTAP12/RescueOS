"""
NGO Field Intelligence Specialist Agent — Organization-level local field report evaluation.

Evaluates field reports relevant to the NGO's target deployment sectors.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType


class NGOFieldAgent:
    """
    NGO Specialist Agent responsible for filtering and evaluating field reports
    near organization operations and resource sites.
    """
    agent_id: str = "ngo_specialist_field"
    name: str = "NGO Field Agent"
    domain: str = "field"
    allowed_context: list[str] = ["org_private_state", "shared_state"]
    allowed_tools: list[str] = ["field_intelligence_tool"]
    accepted_event_types: list[str] = [
        AgentEventType.FIELD_REPORT_CREATED.value,
        AgentEventType.NEED_CREATED.value,
    ]

    def __init__(self, org_id: str):
        self.org_id = org_id

    def evaluate_field_reports_near(self, lat: Optional[float], lon: Optional[float], radius_km: float = 5.0) -> list[dict]:
        """Fetch field reports near a given coordinate."""
        if lat is None or lon is None:
            return []
        try:
            from agent.community_reports import get_reports_near
            return get_reports_near(lat, lon, radius_km=radius_km)
        except Exception:
            return []

    def analyze(self, private_ctx: Any) -> list[AgentFinding]:
        """Analyze field reports relevant to active missions."""
        findings: list[AgentFinding] = []
        for mission in private_ctx.get_active_missions():
            lat = mission.get("lat")
            lon = mission.get("lon")
            if lat and lon:
                nearby = self.evaluate_field_reports_near(lat, lon)
                if nearby:
                    findings.append(
                        AgentFinding(
                            agent_id=self.agent_id,
                            domain=self.domain,
                            finding_type="field_intelligence_nearby",
                            summary=f"{len(nearby)} community reports near mission '{mission.get('name', 'unnamed')}'",
                            severity=FindingSeverity.INFORMATION.value,
                            confidence=0.85,
                            provenance=FindingProvenance.USER_PROVIDED,
                            evidence=[{"report_count": len(nearby)}],
                            related_entity_type="mission",
                            related_entity_id=mission.get("id"),
                        )
                    )
        return findings

    def handle_event(self, event: AgentEvent, private_ctx: Any) -> list[AgentFinding]:
        """Process event related to field intelligence."""
        return self.analyze(private_ctx)
