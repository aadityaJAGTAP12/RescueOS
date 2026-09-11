"""
Logistics Worker — Network-level logistics and resource matching analysis.

Reasons over: published offers, needs, operations, routing, accessibility.
Identifies logistical mismatches and coordination opportunities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType


class LogisticsAgent:
    """
    Network Specialist Agent responsible for evaluating open supply needs against public offers.
    """
    agent_id: str = "network_specialist_logistics"
    name: str = "Network Logistics Agent"
    domain: str = "logistics"
    allowed_context: list[str] = ["shared_state"]
    allowed_tools: list[str] = ["allocation_tool", "matching_core"]
    accepted_event_types: list[str] = [
        AgentEventType.NEED_CREATED.value,
        AgentEventType.OFFER_CREATED.value,
        AgentEventType.OPERATION_CREATED.value,
        AgentEventType.ROAD_OVERRIDE_APPLIED.value,
    ]

    def analyze(self, repo: Any) -> list[AgentFinding]:
        """Run logistics analysis and return structured AgentFindings."""
        raw = analyze_logistics(repo)
        findings: list[AgentFinding] = []

        for f in raw.get("findings", []):
            findings.append(
                AgentFinding(
                    agent_id=self.agent_id,
                    domain=self.domain,
                    finding_type=f.get("type", "logistics_finding"),
                    summary=f.get("summary", f.get("title", "")),
                    severity=f.get("severity", FindingSeverity.URGENT.value),
                    confidence=0.95,
                    provenance=FindingProvenance.OBSERVED,
                    evidence=raw.get("evidence", []),
                    data_gaps=raw.get("data_gaps", []),
                    uncertainty=raw.get("uncertainty", []),
                    location=f.get("location"),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )

        return findings

    def handle_event(self, event: AgentEvent, repo: Any) -> list[AgentFinding]:
        """Process event related to logistics changes."""
        return self.analyze(repo)


def analyze_logistics(repo) -> dict:
    """
    Analyze logistics: resource offers vs needs, routing constraints,
    coordination gaps.
    """
    findings = []
    evidence = []
    uncertainty = []
    data_gaps = []
    recommendations = []

    # Get shared state
    needs = repo.list_needs(status="OPEN") if hasattr(repo, 'list_needs') else []
    offers = repo.list_resource_offers(status="OFFERED") if hasattr(repo, 'list_resource_offers') else []
    operations = repo.list_operations() if hasattr(repo, 'list_operations') else []

    evidence.append({
        "type": "logistics_summary",
        "detail": f"{len(needs)} open needs, {len(offers)} published offers, {len(operations)} operations",
    })

    # Identify needs with no matching offers
    for need in needs:
        need_type = need.need_type if hasattr(need, 'need_type') else need.get('need_type', '')
        matching_offers = [
            o for o in offers
            if _types_match(need_type, o.resource_type if hasattr(o, 'resource_type') else o.get('resource_type', ''))
        ]
        if not matching_offers:
            findings.append({
                "type": "logistics_gap",
                "severity": "urgent",
                "title": f"No published offers for {need_type} need",
                "summary": f"Need '{need.title if hasattr(need, 'title') else need.get('title', '')}' has no matching public offers",
                "location": need.location_name if hasattr(need, 'location_name') else need.get('location_name', ''),
            })

    # Identify duplicate response coverage
    ops_by_need = {}
    for op in operations:
        nid = op.need_id if hasattr(op, 'need_id') else op.get('need_id')
        if nid:
            ops_by_need.setdefault(nid, []).append(op)

    for nid, ops in ops_by_need.items():
        if len(ops) >= 2:
            org_ids = list(set(
                (op.lead_organization_id if hasattr(op, 'lead_organization_id') else op.get('lead_organization_id', ''))
                for op in ops
                if (op.lead_organization_id if hasattr(op, 'lead_organization_id') else op.get('lead_organization_id'))
            ))
            if len(org_ids) >= 2:
                findings.append({
                    "type": "duplicate_response",
                    "severity": "information",
                    "title": f"Multiple operations for same need",
                    "summary": f"{len(ops)} operations from {len(org_ids)} organizations responding to the same need",
                })

    # Check for offers without matching needs
    for offer in offers:
        otype = offer.resource_type if hasattr(offer, 'resource_type') else offer.get('resource_type', '')
        matching_needs = [n for n in needs if _types_match(
            n.need_type if hasattr(n, 'need_type') else n.get('need_type', ''), otype
        )]
        if not matching_needs:
            uncertainty.append(f"Published {otype} offer has no matching open need — may be reserve capacity")

    return _build_result(findings, evidence, uncertainty, data_gaps, recommendations)


def _types_match(need_type: str, offer_type: str) -> bool:
    """Check if resource types are compatible."""
    if not need_type or not offer_type:
        return False
    n = need_type.lower()
    o = offer_type.lower()
    if n == o:
        return True
    if n in o or o in n:
        return True
    # Category mapping
    categories = {
        "boat": "transport", "vehicle": "transport", "transport": "transport",
        "medical_team": "medical", "medical": "medical",
        "food": "supplies", "water": "supplies", "rice": "supplies",
    }
    return categories.get(n) == categories.get(o) and categories.get(n) is not None


def _build_result(findings, evidence, uncertainty, data_gaps, recommendations):
    return {
        "worker": "logistics",
        "findings": findings,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "recommendations": recommendations,
    }
