"""
Situation / Flood Worker — Network-level flood and situation analysis.

Reasons over: flood snapshots, districts, settlements, temporal data.
Deterministic: uses existing repository data, no LLM required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType


class SituationAgent:
    """
    Network Specialist Agent responsible for flood extent and situational monitoring.
    """
    agent_id: str = "network_specialist_situation"
    name: str = "Network Situation Agent"
    domain: str = "situation"
    allowed_context: list[str] = ["shared_state"]
    allowed_tools: list[str] = ["flood_tool", "region_scan_tool"]
    accepted_event_types: list[str] = [
        AgentEventType.FLOOD_SNAPSHOT_UPDATED.value,
        AgentEventType.NEED_CREATED.value,
    ]

    def analyze(self, repo: Any) -> list[AgentFinding]:
        """Run situation analysis and return structured AgentFindings."""
        raw = analyze_situation(repo)
        findings: list[AgentFinding] = []

        # Convert raw findings to typed AgentFinding objects
        for f in raw.get("findings", []):
            findings.append(
                AgentFinding(
                    agent_id=self.agent_id,
                    domain=self.domain,
                    finding_type=f.get("type", "situation_finding"),
                    summary=f.get("summary", f.get("title", "")),
                    severity=f.get("severity", FindingSeverity.INFORMATION.value),
                    confidence=0.9,
                    provenance=FindingProvenance.OBSERVED,
                    evidence=raw.get("evidence", []),
                    data_gaps=raw.get("data_gaps", []),
                    uncertainty=raw.get("uncertainty", []),
                    location=f.get("location"),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )

        # If there are data gaps but no findings, emit a data gap finding
        if not findings and raw.get("data_gaps"):
            findings.append(
                AgentFinding(
                    agent_id=self.agent_id,
                    domain=self.domain,
                    finding_type="data_gap",
                    summary="Incomplete or missing flood snapshot data",
                    severity=FindingSeverity.INFORMATION.value,
                    confidence=1.0,
                    provenance=FindingProvenance.UNKNOWN,
                    data_gaps=raw.get("data_gaps", []),
                    uncertainty=raw.get("uncertainty", []),
                )
            )

        return findings

    def handle_event(self, event: AgentEvent, repo: Any) -> list[AgentFinding]:
        """Process event related to flood snapshot updates."""
        all_findings = self.analyze(repo)
        if event.district:
            # Prioritize findings for the relevant district
            district_findings = [f for f in all_findings if f.location == event.district]
            if district_findings:
                return district_findings
        return all_findings


def analyze_situation(repo) -> dict:
    """
    Analyze the current flood situation across all districts.

    Returns structured findings about flood state, temporal coverage,
    and areas of concern.
    """
    findings = []
    evidence = []
    uncertainty = []
    data_gaps = []

    # Get districts
    districts = repo.list_districts() if hasattr(repo, 'list_districts') else []

    # Get flood snapshots
    snapshots = repo.list_flood_snapshots() if hasattr(repo, 'list_flood_snapshots') else []

    if not snapshots:
        data_gaps.append({
            "item": "No flood snapshots",
            "detail": "No flood observation data available for analysis.",
        })
        return _build_result(findings, evidence, uncertainty, data_gaps)

    # Analyze per-district flood state
    district_snapshots = {}
    for snap in snapshots:
        did = snap.district_id if hasattr(snap, 'district_id') else snap.get('district_id', '')
        district_snapshots.setdefault(did, []).append(snap)

    for did, snaps in district_snapshots.items():
        # Sort by observation date
        sorted_snaps = sorted(snaps, key=lambda s: s.observed_at if hasattr(s, 'observed_at') else s.get('observed_at', ''), reverse=True)
        latest = sorted_snaps[0]

        obs_date = latest.observed_at if hasattr(latest, 'observed_at') else latest.get('observed_at', '')
        polygon_count = latest.polygon_count if hasattr(latest, 'polygon_count') else latest.get('polygon_count', 0)
        source = latest.source if hasattr(latest, 'source') else latest.get('source', 'unknown')
        confidence = latest.confidence if hasattr(latest, 'confidence') else latest.get('confidence', 0)

        evidence.append({
            "type": "flood_snapshot",
            "detail": f"Latest flood snapshot for {did}: {obs_date}, {polygon_count} polygons",
            "source": source,
            "timestamp": obs_date,
            "district": did,
        })

        if polygon_count > 0:
            findings.append({
                "type": "flood_active",
                "severity": "urgent",
                "title": f"Flood extent observed in {did}",
                "summary": f"{polygon_count} flood polygons observed on {obs_date}",
                "location": did,
                "evidence_refs": [f"flood_snapshot:{did}"],
            })

        # Temporal analysis
        if len(sorted_snaps) > 1:
            prev = sorted_snaps[1]
            prev_count = prev.polygon_count if hasattr(prev, 'polygon_count') else prev.get('polygon_count', 0)
            if polygon_count > prev_count:
                findings.append({
                    "type": "flood_escalation",
                    "severity": "critical",
                    "title": f"Flood extent increased in {did}",
                    "summary": f"Polygons increased from {prev_count} to {polygon_count}",
                    "location": did,
                })
            elif polygon_count < prev_count:
                findings.append({
                    "type": "flood_deescalation",
                    "severity": "stable",
                    "title": f"Flood extent decreased in {did}",
                    "summary": f"Polygons decreased from {prev_count} to {polygon_count}",
                    "location": did,
                })
        else:
            uncertainty.append(f"Only one flood snapshot available for {did} — no temporal comparison possible")

    # Districts without flood data
    district_ids = [d.id if hasattr(d, 'id') else d.get('id', '') for d in districts]
    for did in district_ids:
        if did not in district_snapshots:
            data_gaps.append({
                "item": f"No flood data for {did}",
                "detail": f"District {did} has no flood snapshots in the database.",
            })

    return _build_result(findings, evidence, uncertainty, data_gaps)


def _build_result(findings, evidence, uncertainty, data_gaps, recommendations=None):
    return {
        "worker": "situation",
        "findings": findings,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "recommendations": recommendations or [],
    }
