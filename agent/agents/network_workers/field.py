"""
Field Intelligence Worker — Network-level field report analysis.

Reuses existing field reports, deduplication, and evidence synthesis.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType


class FieldAgent:
    """
    Network Specialist Agent responsible for clustering and deduplicating field reports.
    """
    agent_id: str = "network_specialist_field"
    name: str = "Network Field Agent"
    domain: str = "field"
    allowed_context: list[str] = ["shared_state"]
    allowed_tools: list[str] = ["field_intelligence_tool"]
    accepted_event_types: list[str] = [
        AgentEventType.FIELD_REPORT_CREATED.value,
        AgentEventType.NEED_CREATED.value,
    ]

    def analyze(self, repo: Any) -> list[AgentFinding]:
        """Run field intelligence analysis and return structured AgentFindings."""
        raw = analyze_field_intelligence(repo)
        findings: list[AgentFinding] = []

        for f in raw.get("findings", []):
            findings.append(
                AgentFinding(
                    agent_id=self.agent_id,
                    domain=self.domain,
                    finding_type=f.get("type", "field_finding"),
                    summary=f.get("summary", f.get("title", "")),
                    severity=f.get("severity", FindingSeverity.INFORMATION.value),
                    confidence=0.8,
                    provenance=FindingProvenance.USER_PROVIDED,
                    evidence=raw.get("evidence", []),
                    data_gaps=raw.get("data_gaps", []),
                    uncertainty=raw.get("uncertainty", []),
                    location=f.get("location"),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )

        if not findings and raw.get("data_gaps"):
            findings.append(
                AgentFinding(
                    agent_id=self.agent_id,
                    domain=self.domain,
                    finding_type="data_gap",
                    summary="No community or field intelligence reports available",
                    severity=FindingSeverity.INFORMATION.value,
                    confidence=1.0,
                    provenance=FindingProvenance.UNKNOWN,
                    data_gaps=raw.get("data_gaps", []),
                    uncertainty=raw.get("uncertainty", []),
                )
            )

        return findings

    def handle_event(self, event: AgentEvent, repo: Any) -> list[AgentFinding]:
        """Process event related to new field reports."""
        return self.analyze(repo)


def analyze_field_intelligence(repo) -> dict:
    """
    Analyze field reports and intelligence for the network.
    Uses semantic deduplication from Phase 7D.
    """
    findings = []
    evidence = []
    uncertainty = []
    data_gaps = []
    recommendations = []

    # Get field reports
    try:
        from agent.community_reports import get_all_reports
        all_reports = get_all_reports()
    except Exception:
        all_reports = []

    if not all_reports:
        data_gaps.append({
            "item": "No field reports",
            "detail": "No community or field intelligence reports available.",
        })
        return _build_result(findings, evidence, uncertainty, data_gaps, recommendations)

    # Deduplicate reports
    try:
        from agent.delta import deduplicate_reports
        grouped = deduplicate_reports(all_reports)
    except Exception:
        grouped = []

    evidence.append({
        "type": "field_report_summary",
        "detail": f"{len(all_reports)} total reports, {len(grouped)} grouped events",
    })

    # Analyze grouped events
    for event in grouped:
        report_count = event.get("report_count", 0)
        verified = event.get("verified_count", 0)
        category = event.get("category", "general")

        if report_count >= 3:
            findings.append({
                "type": "clustered_reports",
                "severity": "urgent" if verified > 0 else "information",
                "title": f"Clustered reports: {category}",
                "summary": f"{report_count} reports ({verified} verified) describe similar event",
                "location": event.get("location_description", ""),
            })
        elif report_count >= 2:
            findings.append({
                "type": "grouped_reports",
                "severity": "information",
                "title": f"Grouped reports: {category}",
                "summary": f"{report_count} reports grouped as similar event",
                "location": event.get("location_description", ""),
            })

    # Unverified reports
    unverified = [r for r in all_reports if not r.get("verified", False)]
    if unverified:
        uncertainty.append(f"{len(unverified)} reports are unverified — field confirmation recommended")

    return _build_result(findings, evidence, uncertainty, data_gaps, recommendations)


def _build_result(findings, evidence, uncertainty, data_gaps, recommendations):
    return {
        "worker": "field",
        "findings": findings,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "recommendations": recommendations,
    }
