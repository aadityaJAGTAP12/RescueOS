"""
Evidence Worker — Network-level evidence synthesis.

Reuses Phase 7D evidence synthesis where possible.
Ensures every important recommendation has supporting evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType


class EvidenceAgent:
    """
    Network Specialist Agent responsible for cross-domain evidence grounding and provenance synthesis.
    """
    agent_id: str = "network_specialist_evidence"
    name: str = "Network Evidence Agent"
    domain: str = "evidence"
    allowed_context: list[str] = ["shared_state"]
    allowed_tools: list[str] = []
    accepted_event_types: list[str] = [
        AgentEventType.FLOOD_SNAPSHOT_UPDATED.value,
        AgentEventType.NEED_CREATED.value,
        AgentEventType.FIELD_REPORT_CREATED.value,
    ]

    def analyze(self, repo: Any) -> list[AgentFinding]:
        """Run evidence synthesis and return structured AgentFindings."""
        raw = synthesize_network_evidence(repo)
        findings: list[AgentFinding] = []

        if raw.get("uncertainty"):
            for unc in raw.get("uncertainty", []):
                findings.append(
                    AgentFinding(
                        agent_id=self.agent_id,
                        domain=self.domain,
                        finding_type="uncertainty_note",
                        summary=unc,
                        severity=FindingSeverity.INFORMATION.value,
                        confidence=1.0,
                        provenance=FindingProvenance.UNKNOWN,
                        evidence=raw.get("evidence", []),
                        data_gaps=raw.get("data_gaps", []),
                        uncertainty=raw.get("uncertainty", []),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                )

        if raw.get("data_gaps"):
            for gap in raw.get("data_gaps", []):
                findings.append(
                    AgentFinding(
                        agent_id=self.agent_id,
                        domain=self.domain,
                        finding_type="data_gap",
                        summary=gap.get("detail", gap.get("item", "Data gap identified")),
                        severity=FindingSeverity.INFORMATION.value,
                        confidence=1.0,
                        provenance=FindingProvenance.UNKNOWN,
                        evidence=raw.get("evidence", []),
                        data_gaps=raw.get("data_gaps", []),
                        uncertainty=raw.get("uncertainty", []),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                )

        return findings

    def handle_event(self, event: AgentEvent, repo: Any) -> list[AgentFinding]:
        """Process event related to evidence updates."""
        return self.analyze(repo)


def synthesize_network_evidence(repo) -> dict:
    """
    Synthesize evidence across the network for the Network Main Agent.
    """
    findings = []
    evidence = []
    uncertainty = []
    data_gaps = []

    # Flood evidence
    try:
        snapshots = repo.list_flood_snapshots() if hasattr(repo, 'list_flood_snapshots') else []
        if snapshots:
            evidence.append({
                "type": "flood_evidence",
                "detail": f"{len(snapshots)} flood snapshots available",
                "coverage": len(set(s.district_id if hasattr(s, 'district_id') else s.get('district_id', '') for s in snapshots)),
            })
        else:
            data_gaps.append({"item": "No flood evidence", "detail": "No flood snapshots in database."})
    except Exception:
        data_gaps.append({"item": "Flood evidence", "detail": "Unable to access flood snapshot data."})

    # Field report evidence
    try:
        from agent.community_reports import get_all_reports
        reports = get_all_reports()
        verified = [r for r in reports if r.get("verified", False)]
        evidence.append({
            "type": "field_report_evidence",
            "detail": f"{len(reports)} total reports, {len(verified)} verified",
        })
        if not verified:
            uncertainty.append("No verified field reports — all reports are unverified")
    except Exception:
        data_gaps.append({"item": "Field reports", "detail": "Unable to access field report data."})

    # Override evidence
    try:
        from agent.overrides import get_all_overrides
        overrides = get_all_overrides()
        active = [o for o in overrides if o.get("active", True)]
        evidence.append({
            "type": "override_evidence",
            "detail": f"{len(active)} active overrides (coordinator-reported status)",
        })
    except Exception:
        data_gaps.append({"item": "Override evidence", "detail": "Unable to access override data."})

    return {
        "worker": "evidence",
        "findings": findings,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "recommendations": [],
    }
