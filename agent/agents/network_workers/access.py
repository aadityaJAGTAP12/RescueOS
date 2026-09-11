"""
Access / Routing Worker — Network-level access and routing analysis.

Reuses existing road status, bridge status, overrides, and routing capabilities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType


class AccessAgent:
    """
    Network Specialist Agent responsible for evaluating road closures and routing feasibility.
    """
    agent_id: str = "network_specialist_access"
    name: str = "Network Access Agent"
    domain: str = "access"
    allowed_context: list[str] = ["shared_state"]
    allowed_tools: list[str] = ["road_status_tool", "routing_tool", "accessibility_tool"]
    accepted_event_types: list[str] = [
        AgentEventType.ROAD_OVERRIDE_APPLIED.value,
        AgentEventType.BRIDGE_OVERRIDE_APPLIED.value,
        AgentEventType.OPERATION_CREATED.value,
    ]

    def analyze(self, repo: Any) -> list[AgentFinding]:
        """Run access analysis and return structured AgentFindings."""
        raw = analyze_access(repo)
        findings: list[AgentFinding] = []

        for f in raw.get("findings", []):
            findings.append(
                AgentFinding(
                    agent_id=self.agent_id,
                    domain=self.domain,
                    finding_type=f.get("type", "access_blocked"),
                    summary=f.get("summary", f.get("title", "")),
                    severity=f.get("severity", FindingSeverity.URGENT.value),
                    confidence=0.95,
                    provenance=FindingProvenance.USER_PROVIDED,
                    evidence=raw.get("evidence", []),
                    data_gaps=raw.get("data_gaps", []),
                    uncertainty=raw.get("uncertainty", []),
                    location=f.get("location"),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )

        return findings

    def handle_event(self, event: AgentEvent, repo: Any) -> list[AgentFinding]:
        """Process event related to road or bridge overrides."""
        all_findings = self.analyze(repo)
        target_id = event.metadata.get("target_id")
        if target_id:
            specific = [f for f in all_findings if f.location == target_id]
            if specific:
                return specific
        return all_findings


def analyze_access(repo) -> dict:
    """
    Analyze access and routing conditions based on road/bridge status
    and active overrides.
    """
    findings = []
    evidence = []
    uncertainty = []
    data_gaps = []
    recommendations = []

    # Get active overrides
    try:
        from agent.overrides import get_all_overrides
        overrides = get_all_overrides()
        active_overrides = [o for o in overrides if o.get("active", True)]
    except Exception:
        active_overrides = []

    road_overrides = [o for o in active_overrides if o.get("target_type") == "road"]

    evidence.append({
        "type": "override_summary",
        "detail": f"{len(road_overrides)} active road/bridge overrides",
    })

    # Analyze blocked routes
    blocked = [o for o in road_overrides if o.get("override_status") in ("blocked", "submerged", "damaged")]
    if blocked:
        for override in blocked:
            findings.append({
                "type": "access_blocked",
                "severity": "urgent",
                "title": f"Route blocked: {override.get('target_id', 'unknown')}",
                "summary": f"Override status: {override.get('override_status')} — {override.get('reason', 'no reason given')}",
                "location": override.get("target_id", ""),
            })

    # Check operations affected by blocked routes
    try:
        active_ops = repo.list_operations(status="ACTIVE") + repo.list_operations(status="PLANNING")
        for op in active_ops:
            op_district = op.district_id if hasattr(op, 'district_id') else op.get('district_id', '')
            for override in blocked:
                if override.get("target_id", "") in (op_district or ""):
                    uncertainty.append(f"Operation '{op.name if hasattr(op, 'name') else op.get('name', '')}' may be affected by blocked route")
    except Exception:
        pass

    # Unknown road conditions
    if not active_overrides:
        uncertainty.append("No road status overrides in system — actual road conditions unknown")

    return _build_result(findings, evidence, uncertainty, data_gaps, recommendations)


def _build_result(findings, evidence, uncertainty, data_gaps, recommendations):
    return {
        "worker": "access",
        "findings": findings,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "recommendations": recommendations,
    }
