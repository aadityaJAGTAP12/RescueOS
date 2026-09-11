"""
Medical Worker — Network-level medical situation analysis.

Reasons over: medical facilities, flood exposure, field reports.
Uses cautious language — never claims outbreaks without evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType


class MedicalAgent:
    """
    Network Specialist Agent responsible for evaluating medical urgency and facility readiness.
    """
    agent_id: str = "network_specialist_medical"
    name: str = "Network Medical Agent"
    domain: str = "medical"
    allowed_context: list[str] = ["shared_state"]
    allowed_tools: list[str] = ["field_intelligence_tool"]
    accepted_event_types: list[str] = [
        AgentEventType.NEED_CREATED.value,
        AgentEventType.FIELD_REPORT_CREATED.value,
        AgentEventType.ROAD_OVERRIDE_APPLIED.value,
    ]

    def analyze(self, repo: Any) -> list[AgentFinding]:
        """Run medical situation analysis and return structured AgentFindings."""
        raw = analyze_medical(repo)
        findings: list[AgentFinding] = []

        for f in raw.get("findings", []):
            findings.append(
                AgentFinding(
                    agent_id=self.agent_id,
                    domain=self.domain,
                    finding_type=f.get("type", "medical_concern"),
                    summary=f.get("summary", f.get("title", "")),
                    severity=f.get("severity", FindingSeverity.URGENT.value),
                    confidence=0.8,
                    provenance=FindingProvenance.OBSERVED,
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
                    summary="Medical facility or disease intelligence data missing",
                    severity=FindingSeverity.INFORMATION.value,
                    confidence=1.0,
                    provenance=FindingProvenance.UNKNOWN,
                    data_gaps=raw.get("data_gaps", []),
                    uncertainty=raw.get("uncertainty", []),
                )
            )

        return findings

    def handle_event(self, event: AgentEvent, repo: Any) -> list[AgentFinding]:
        """Process event related to medical urgency."""
        return self.analyze(repo)


def analyze_medical(repo) -> dict:
    """
    Analyze medical pressure based on available evidence.

    Returns cautious findings about potential health risks.
    """
    findings = []
    evidence = []
    uncertainty = []
    data_gaps = []
    recommendations = []

    # Check for medical facilities
    try:
        facilities = repo.list_medical_facilities() if hasattr(repo, 'list_medical_facilities') else []
    except Exception:
        facilities = []

    if not facilities:
        data_gaps.append({
            "item": "No medical facility data",
            "detail": "Medical facility inventory not available for analysis.",
        })

    # Check field reports for medical needs
    try:
        from agent.community_reports import get_all_reports
        all_reports = get_all_reports()
        medical_reports = [r for r in all_reports if 'medical' in (r.get('needs', []))]
    except Exception:
        medical_reports = []

    if medical_reports:
        evidence.append({
            "type": "field_reports",
            "detail": f"{len(medical_reports)} field reports mention medical needs",
            "count": len(medical_reports),
        })
        findings.append({
            "type": "medical_concern",
            "severity": "urgent" if len(medical_reports) >= 3 else "information",
            "title": f"{len(medical_reports)} field report(s) indicate medical needs",
            "summary": "Community reports mention medical requirements — verification recommended",
            "evidence_refs": ["field_reports:medical"],
        })

    # Check flood exposure for health risk indicators
    snapshots = repo.list_flood_snapshots() if hasattr(repo, 'list_flood_snapshots') else []
    if snapshots:
        evidence.append({
            "type": "flood_context",
            "detail": f"{len(snapshots)} flood snapshots available — standing water may increase health risks",
        })
        uncertainty.append("Flood-related health risks are potential, not confirmed — no disease outbreak data available")

    return _build_result(findings, evidence, uncertainty, data_gaps, recommendations)


def _build_result(findings, evidence, uncertainty, data_gaps, recommendations):
    return {
        "worker": "medical",
        "findings": findings,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "recommendations": recommendations,
    }
