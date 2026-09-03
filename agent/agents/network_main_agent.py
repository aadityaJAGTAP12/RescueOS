"""
Network Main Agent — Hierarchical Network Coordination

Phase 7G: The Network Main Agent reasons over the shared emergency
operating picture and coordinates with NGO Main Agents WITHOUT
accessing private NGO state.

Architecture:
    Network Main Agent
    ├── Situation/Flood Worker
    ├── Exposure Worker
    ├── Medical Worker
    ├── Logistics Worker
    ├── Access/Routing Worker
    ├── Field Intelligence Worker
    ├── Coordination Worker
    └── Evidence Worker

Design principles:
- SHARED STATE ONLY: never reads NGO private inventory/teams/missions
- Deterministic baseline: workers are deterministic when possible
- Human-in-the-loop: recommendations are proposals, not commands
- Evidence-based: every finding includes supporting evidence
- Honest about uncertainty and data gaps
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

# Import workers
from agent.agents.network_workers.situation import analyze_situation
from agent.agents.network_workers.exposure import analyze_exposure
from agent.agents.network_workers.medical import analyze_medical
from agent.agents.network_workers.logistics import analyze_logistics
from agent.agents.network_workers.access import analyze_access
from agent.agents.network_workers.field import analyze_field_intelligence
from agent.agents.network_workers.coordination import analyze_coordination
from agent.agents.network_workers.evidence import synthesize_network_evidence


# ---------------------------------------------------------------------------
# Network Main Agent
# ---------------------------------------------------------------------------

class NetworkMainAgent:
    """
    The Network Main Agent orchestrates network-level analysis
    over shared operational state.

    It does NOT access NGO private state.
    It produces recommendations that require human approval.
    """

    def __init__(self):
        self.audit_log = []

    def analyze_network(self, repo=None) -> dict:
        """
        Run full network analysis using all workers.

        Returns structured result with findings, evidence, uncertainty,
        data gaps, and recommended actions.
        """
        if repo is None:
            from agent.data.repository import get_repository
            repo = get_repository()

        t_start = time.time()

        # Run all workers
        worker_results = {}
        all_findings = []
        all_evidence = []
        all_uncertainty = []
        all_data_gaps = []
        all_recommendations = []

        workers = [
            ("situation", analyze_situation),
            ("exposure", analyze_exposure),
            ("medical", analyze_medical),
            ("logistics", analyze_logistics),
            ("access", analyze_access),
            ("field", analyze_field_intelligence),
            ("coordination", analyze_coordination),
            ("evidence", synthesize_network_evidence),
        ]

        for name, analyze_fn in workers:
            try:
                result = analyze_fn(repo)
                worker_results[name] = result
                all_findings.extend(result.get("findings", []))
                all_evidence.extend(result.get("evidence", []))
                all_uncertainty.extend(result.get("uncertainty", []))
                all_data_gaps.extend(result.get("data_gaps", []))
                all_recommendations.extend(result.get("recommendations", []))
            except Exception as e:
                all_data_gaps.append({
                    "item": f"Worker failure: {name}",
                    "detail": f"Worker '{name}' failed: {str(e)}",
                })

        # Compute summary
        severity_counts = {"critical": 0, "urgent": 0, "information": 0, "stable": 0}
        for f in all_findings:
            sev = f.get("severity", "information")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        # Identify priority needs (uncovered critical/urgent)
        priority_needs = [
            f for f in all_findings
            if f.get("type") in ("uncovered_need", "logistics_gap")
            and f.get("severity") in ("critical", "urgent")
        ]

        # Identify coordination opportunities
        coordination_opportunities = [
            f for f in all_findings
            if f.get("type") in ("surplus_offer", "duplicate_response")
        ]

        # Identify risks
        risks = [
            f for f in all_findings
            if f.get("severity") in ("critical", "urgent")
            and f.get("type") not in ("uncovered_need", "logistics_gap")
        ]

        # Generate recommended actions (proposals, not commands)
        recommended_actions = []
        for need_finding in priority_needs:
            recommended_actions.append({
                "type": "review_need",
                "detail": f"Review whether organizations can support: {need_finding.get('title', 'unknown need')}",
                "entity_type": need_finding.get("entity_type", "need"),
                "entity_id": need_finding.get("entity_id"),
            })

        for risk in risks:
            recommended_actions.append({
                "type": "review_risk",
                "detail": f"Review: {risk.get('title', 'unknown risk')}",
            })

        # Build summary text
        summary_parts = []
        if severity_counts.get("critical", 0) > 0:
            summary_parts.append(f"{severity_counts['critical']} critical findings")
        if severity_counts.get("urgent", 0) > 0:
            summary_parts.append(f"{severity_counts['urgent']} urgent findings")
        if priority_needs:
            summary_parts.append(f"{len(priority_needs)} uncovered needs")
        if coordination_opportunities:
            summary_parts.append(f"{len(coordination_opportunities)} coordination opportunities")
        summary = "; ".join(summary_parts) if summary_parts else "No significant issues detected"

        elapsed_ms = round((time.time() - t_start) * 1000, 1)

        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "situation": [
                f.get("title", "") for f in all_findings
                if f.get("type") in ("flood_active", "flood_escalation", "flood_deescalation", "exposure_risk")
            ],
            "priority_needs": priority_needs,
            "coordination_opportunities": coordination_opportunities,
            "risks": risks,
            "worker_findings": {
                name: {
                    "findings_count": len(wr.get("findings", [])),
                    "evidence_count": len(wr.get("evidence", [])),
                    "uncertainty_count": len(wr.get("uncertainty", [])),
                    "data_gaps_count": len(wr.get("data_gaps", [])),
                }
                for name, wr in worker_results.items()
            },
            "evidence": all_evidence,
            "uncertainty": all_uncertainty,
            "data_gaps": all_data_gaps,
            "recommended_actions": recommended_actions,
            "severity_summary": severity_counts,
            "analysis_time_ms": elapsed_ms,
        }

        # Audit
        self._audit("analyze_network", {
            "findings_count": len(all_findings),
            "severity_summary": severity_counts,
            "recommended_actions_count": len(recommended_actions),
        })

        return result

    def analyze_need_context(
        self,
        need: dict,
        repo=None,
    ) -> dict:
        """
        Analyze a specific need in the network context.

        Returns detailed analysis with evidence, access, coordination,
        and recommended actions.
        """
        if repo is None:
            from agent.data.repository import get_repository
            repo = get_repository()

        t_start = time.time()

        need_id = need.get("id", "")
        need_type = need.get("need_type", "")
        need_title = need.get("title", need_type)

        # Gather context
        evidence_items = []
        uncertainty = []
        data_gaps = []

        # Check matching offers
        offers = repo.list_resource_offers(status="OFFERED") if hasattr(repo, 'list_resource_offers') else []
        matching_offers = [
            o for o in offers
            if _types_match(need_type, o.resource_type if hasattr(o, 'resource_type') else o.get('resource_type', ''))
        ]

        if matching_offers:
            evidence_items.append({
                "type": "matching_offers",
                "detail": f"{len(matching_offers)} published offers match this need type",
            })
        else:
            data_gaps.append({
                "item": "No matching offers",
                "detail": f"No published offers for {need_type} resources",
            })

        # Check linked operations
        operations = repo.list_operations() if hasattr(repo, 'list_operations') else []
        linked_ops = [o for o in operations if (o.need_id if hasattr(o, 'need_id') else o.get('need_id')) == need_id]
        if linked_ops:
            evidence_items.append({
                "type": "linked_operations",
                "detail": f"{len(linked_ops)} operation(s) responding to this need",
            })

        # Check access conditions
        try:
            from agent.overrides import get_all_overrides
            overrides = get_all_overrides()
            active = [o for o in overrides if o.get("active", True) and o.get("target_type") == "road"]
            if active:
                uncertainty.append(f"{len(active)} active road overrides may affect access to this need")
        except Exception:
            pass

        # Check field reports near location
        lat = need.get("lat")
        lon = need.get("lon")
        if lat and lon:
            try:
                from agent.community_reports import get_reports_near
                nearby = get_reports_near(lat, lon, radius_km=5.0)
                if nearby:
                    evidence_items.append({
                        "type": "field_reports",
                        "detail": f"{len(nearby)} field reports near this location",
                    })
            except Exception:
                pass

        elapsed_ms = round((time.time() - t_start) * 1000, 1)

        return {
            "need_id": need_id,
            "need_title": need_title,
            "need_type": need_type,
            "evidence": evidence_items,
            "matching_offers": len(matching_offers),
            "linked_operations": len(linked_ops),
            "uncertainty": uncertainty,
            "data_gaps": data_gaps,
            "analysis_time_ms": elapsed_ms,
        }

    def _audit(self, action: str, details: dict) -> None:
        """Record an audit event."""
        self.audit_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": details,
        })


def _types_match(need_type: str, offer_type: str) -> bool:
    if not need_type or not offer_type:
        return False
    n, o = need_type.lower(), offer_type.lower()
    if n == o or n in o or o in n:
        return True
    categories = {"boat": "transport", "vehicle": "transport", "medical_team": "medical", "food": "supplies", "water": "supplies"}
    return categories.get(n) == categories.get(o) and categories.get(n) is not None


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def run_network_analysis(repo=None) -> dict:
    """Run full network analysis. Main entry point for API."""
    agent = NetworkMainAgent()
    return agent.analyze_network(repo)


def analyze_need_in_network(need: dict, repo=None) -> dict:
    """Analyze a specific need in network context. Main entry point for API."""
    agent = NetworkMainAgent()
    return agent.analyze_need_context(need, repo)
