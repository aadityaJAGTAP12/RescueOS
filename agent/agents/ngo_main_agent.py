"""
NGO Main Agent — Organization Operational Intelligence

Phase 1 Agent Runtime: The NGO Main Agent represents an organization's operational intelligence.
It reasons over PRIVATE organizational state + SHARED network state.

Architecture:
    PrivateOrganizationContext + SharedNetworkContext
        → NGO Main Agent
            ├── NGOInventoryAgent
            ├── NGOTeamAgent
            ├── NGOMissionAgent
            ├── NGOLogisticsAgent
            └── NGOFieldAgent
        → Recommendation / Explanation / Proposed Publication

Design principles:
- PRIVATE: inventory, teams, missions stay private
- PUBLIC: only published offers/operations are shared
- Human-in-the-loop: AI proposes, human approves
- LLM fallback: deterministic analysis when LLM unavailable
- Auditability: record operational rationale, not chain-of-thought
- Error isolation: specialist failure does not crash analysis
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType
from agent.agents.ngo_workers import (
    NGOFieldAgent,
    NGOInventoryAgent,
    NGOLogisticsAgent,
    NGOMissionAgent,
    NGOTeamAgent,
)
from agent.matching_core import compare_need_resource
from agent.reasoning.need_offer_judgment import judge_need_offer


# ---------------------------------------------------------------------------
# Context objects — explicit private/shared separation
# ---------------------------------------------------------------------------

class PrivateOrganizationContext:
    """Private organizational state that must NOT be exposed to the network."""

    def __init__(
        self,
        org_id: str,
        resources: list[dict] = None,
        teams: list[dict] = None,
        missions: list[dict] = None,
    ):
        self.org_id = org_id
        self.resources = resources or []
        self.teams = teams or []
        self.missions = missions or []

    def get_available_resources(self, resource_type: str = None) -> list[dict]:
        """Get resources that are available (not committed/deployed)."""
        available = [r for r in self.resources if r.get("status") == "available"]
        if resource_type:
            available = [r for r in available if r.get("type") == resource_type or r.get("resource_type") == resource_type]
        return available

    def get_available_teams(self) -> list[dict]:
        """Get teams that are available for assignment."""
        return [t for t in self.teams if t.get("status") == "available"]

    def get_active_missions(self) -> list[dict]:
        """Get missions that are currently active."""
        return [m for m in self.missions if m.get("status") in ("ACTIVE", "READY")]

    def get_committed_resources(self) -> list[dict]:
        """Get resources that are committed to operations."""
        return [r for r in self.resources if r.get("status") == "committed"]

    def has_resource_conflict(self, resource_type: str, quantity: int) -> tuple[bool, str]:
        """Check if publishing a resource would conflict with existing commitments."""
        available = self.get_available_resources(resource_type)
        total_available = sum(r.get("quantity", 0) for r in available)

        if total_available < quantity:
            return True, f"Only {total_available} {resource_type} available (need {quantity})"

        # Check if any active mission requires this resource type
        for mission in self.get_active_missions():
            assigned = mission.get("assigned_resources", [])
            for ar in assigned:
                if ar.get("type") == resource_type:
                    return True, f"Resource type '{resource_type}' is assigned to mission '{mission.get('name', 'unknown')}'"

        return False, "No conflict detected"

    def to_dict(self) -> dict:
        """Serialize for agent context (PRIVATE — never expose to network)."""
        return {
            "org_id": self.org_id,
            "resources": self.resources,
            "teams": self.teams,
            "missions": self.missions,
        }


class SharedNetworkContext:
    """Shared network state visible to all organizations."""

    def __init__(
        self,
        open_needs: list[dict] = None,
        active_operations: list[dict] = None,
        published_offers: list[dict] = None,
        relevant_overrides: list[dict] = None,
    ):
        self.open_needs = open_needs or []
        self.active_operations = active_operations or []
        self.published_offers = published_offers or []
        self.relevant_overrides = relevant_overrides or []

    def get_needs_for_resource_type(self, resource_type: str) -> list[dict]:
        """Get open needs that match a resource type."""
        matching = []
        for need in self.open_needs:
            need_type = need.get("need_type", "").lower()
            if resource_type.lower() in need_type or need_type in resource_type.lower():
                matching.append(need)
            # Also check requested_resources
            for rr in need.get("requested_resources", []):
                rr_type = rr.get("type", rr.get("resource_type", "")).lower()
                if resource_type.lower() in rr_type or rr_type in resource_type.lower():
                    if need not in matching:
                        matching.append(need)
        return matching

    def to_dict(self) -> dict:
        """Serialize for agent context (public state only)."""
        return {
            "open_needs": self.open_needs,
            "active_operations": self.active_operations,
            "published_offers": self.published_offers,
            "relevant_overrides": self.relevant_overrides,
        }


# ---------------------------------------------------------------------------
# NGO Main Agent
# ---------------------------------------------------------------------------

class NGOMainAgent:
    """
    The NGO Main Agent represents an organization's operational intelligence.

    It reasons over private organizational state + shared network state
    to produce recommendations that require human approval.
    """
    domain: str = "ngo"
    allowed_context: list[str] = ["org_private_state", "shared_state"]
    allowed_tools: list[str] = ["matching_core", "road_status_tool", "field_intelligence_tool"]
    accepted_event_types: list[str] = [
        AgentEventType.NEED_CREATED.value,
        AgentEventType.COORDINATION_PROPOSAL_RECEIVED.value,
        AgentEventType.OPERATION_CREATED.value,
        AgentEventType.OPERATION_STATUS_CHANGED.value,
        AgentEventType.ROAD_OVERRIDE_APPLIED.value,
        AgentEventType.BRIDGE_OVERRIDE_APPLIED.value,
        AgentEventType.FIELD_REPORT_CREATED.value,
    ]

    def __init__(self, org_id: str):
        self.org_id = org_id
        self.agent_id = f"ngo_main_agent_{org_id}"
        self.audit_log = []

        # Explicit NGO Specialist Agents
        self.inventory_agent = NGOInventoryAgent(org_id)
        self.team_agent = NGOTeamAgent(org_id)
        self.mission_agent = NGOMissionAgent(org_id)
        self.logistics_agent = NGOLogisticsAgent(org_id)
        self.field_agent = NGOFieldAgent(org_id)

        self._specialist_map = {
            "inventory": self.inventory_agent,
            "team": self.team_agent,
            "mission": self.mission_agent,
            "logistics": self.logistics_agent,
            "field": self.field_agent,
        }

    def handle_event(
        self,
        event: AgentEvent,
        private_ctx: PrivateOrganizationContext,
        shared_ctx: SharedNetworkContext,
    ) -> dict[str, Any]:
        """
        Process a machine-facing AgentEvent through deterministic NGO specialist delegation.

        Flow:
            AgentEvent
               ↓
            Determine relevant NGO specialists
               ↓
            Invoke specialists with failure isolation
               ↓
            Collect typed AgentFindings (Private to Org)
               ↓
            Synthesis & Private Recommendation
        """
        t_start = time.time()

        from agent.agents.event_router import EventRouter
        relevant_domains = EventRouter.route_ngo_event(event)

        collected_findings: list[AgentFinding] = []
        data_gaps: list[dict[str, Any]] = []
        worker_statuses: dict[str, str] = {}

        for domain in relevant_domains:
            specialist = self._specialist_map.get(domain)
            if not specialist:
                continue

            try:
                if domain in ("inventory", "team", "mission", "field"):
                    findings = specialist.handle_event(event, private_ctx)
                elif domain == "logistics":
                    findings = specialist.handle_event(event, shared_ctx)
                else:
                    findings = specialist.analyze(private_ctx)

                collected_findings.extend(findings)
                worker_statuses[domain] = "success"
            except Exception as e:
                worker_statuses[domain] = "failed"
                gap = {
                    "item": f"NGO specialist failure: {domain}",
                    "detail": f"Specialist '{domain}' failed during event handling: {str(e)}",
                }
                data_gaps.append(gap)
                collected_findings.append(
                    AgentFinding(
                        agent_id=f"ngo_specialist_{domain}_{self.org_id}",
                        domain=domain,
                        finding_type="data_gap",
                        summary=f"Worker {domain} failed to process event: {str(e)}",
                        severity=FindingSeverity.INFORMATION.value,
                        confidence=1.0,
                        provenance=FindingProvenance.UNKNOWN,
                        data_gaps=[gap],
                    )
                )

        severity_counts = {"critical": 0, "urgent": 0, "information": 0, "stable": 0}
        for f in collected_findings:
            sev = f.severity if isinstance(f.severity, str) else f.severity.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        elapsed_ms = round((time.time() - t_start) * 1000, 1)

        result = {
            "orchestrator": self.agent_id,
            "org_id": self.org_id,
            "event_id": event.event_id,
            "event_type": event.event_type if isinstance(event.event_type, str) else event.event_type.value,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "selected_specialists": relevant_domains,
            "worker_statuses": worker_statuses,
            "findings": [f.to_dict() for f in collected_findings],
            "severity_summary": severity_counts,
            "data_gaps": data_gaps,
            "processing_time_ms": elapsed_ms,
        }

        self._audit("handle_event", {
            "event_id": event.event_id,
            "event_type": result["event_type"],
            "findings_count": len(collected_findings),
        })

        return result

    def analyze_need(
        self,
        need: dict,
        private_ctx: PrivateOrganizationContext,
        shared_ctx: SharedNetworkContext,
    ) -> dict:
        """
        Analyze a specific network Need using private organizational context.

        Delegates domain evaluations to explicit specialist agents:
        - NGOInventoryAgent
        - NGOTeamAgent
        - NGOMissionAgent
        - NGOLogisticsAgent
        """
        t_start = time.time()

        need_type = need.get("need_type", "other")
        need_title = need.get("title", need_type)
        need_id = need.get("id", "unknown")
        requested = need.get("requested_resources", [])

        # Extract requested quantity
        requested_qty = 0
        for r in requested:
            qty = r.get("quantity", 0)
            if isinstance(qty, (int, float)):
                requested_qty += int(qty)

        # --- Inventory Specialist analysis ---
        inv_eval = self.inventory_agent.evaluate_resource_availability(need_type, requested, private_ctx)
        available_resources = inv_eval["available_resources"]
        total_available = inv_eval["total_available"]
        committed = private_ctx.get_committed_resources()
        requested_quantity = inv_eval["requested_quantity"]
        unit_match = inv_eval["unit_match"]
        type_match = inv_eval["type_match"]
        sufficiency = inv_eval["sufficiency"]

        matching_facts = {
            "available_quantity": total_available,
            "requested_quantity": requested_quantity,
            "requested_quantity_specified": requested_quantity is not None,
            "unit_match": unit_match,
            "unit_mismatch": not unit_match,
            "type_match": type_match,
            "sufficiency": sufficiency,
        }
        judgment = judge_need_offer(
            matching_facts,
            title=need_title,
            description=need.get("description", ""),
        )

        # --- Team Specialist analysis ---
        team_eval = self.team_agent.evaluate_team_readiness(private_ctx)
        available_teams = team_eval["available_teams"]

        # --- Mission Specialist analysis ---
        active_missions = private_ctx.get_active_missions()
        conflict, conflict_reason = self.mission_agent.evaluate_mission_conflicts(need_type, min(requested_qty, 1), private_ctx)

        # --- Logistics Specialist analysis ---
        logistics_eval = self.logistics_agent.evaluate_access(shared_ctx)
        relevant_overrides = logistics_eval["blocked_details"]

        # --- Synthesize recommendation ---
        recommendation = ""
        why = ""
        uncertainty = []
        proposed_publication = None
        action_required = "review"

        if requested_quantity is None:
            uncertainty.append("Need quantity is unspecified; available quantity is factual, not a confirmed requirement")
        if not unit_match:
            uncertainty.append("Need and available resource units do not match")
        if not type_match:
            uncertainty.append("Need and available resource types do not match")

        if total_available == 0:
            recommendation = f"Cannot respond — no available {need_type} resources."
            why = f"No {need_type} resources in inventory are currently available."
            action_required = "none"
        elif conflict:
            recommendation = f"Potential conflict — {need_type} resources may be needed for active mission."
            why = conflict_reason
            uncertainty.append("Mission resource requirements may have changed since last update")
        elif available_teams:
            # Can potentially respond
            offer_qty = min(total_available, requested_qty) if requested_qty > 0 else total_available
            unit = available_resources[0].get("unit", "units") if available_resources else "units"
            recommendation = f"Can potentially provide {offer_qty} {unit} of {need_type}."
            why = (
                f"{total_available} {unit} of {need_type} available in inventory. "
                f"{len(available_teams)} team(s) available. "
                f"No commitment conflicts detected."
            )
            proposed_publication = {
                "resource_type": need_type,
                "quantity": offer_qty,
                "unit": unit,
                "location_name": available_resources[0].get("location") if available_resources else None,
                "linked_need_id": need_id,
                "notes": f"Response to: {need_title}",
            }
        else:
            recommendation = f"May be able to provide {need_type}, but no team currently available."
            why = f"{total_available} {need_type}(s) available but no team for deployment."
            uncertainty.append("Team availability last checked at agent initialization")

        if relevant_overrides:
            uncertainty.append(f"{len(relevant_overrides)} active road overrides may affect access")

        elapsed_ms = round((time.time() - t_start) * 1000, 1)

        result = {
            "need_id": need_id,
            "need_title": need_title,
            "need_type": need_type,
            "recommendation": recommendation,
            "why": why,
            "matching_facts": matching_facts,
            "interpretation": judgment["interpretation"],
            "evidence": {
                "available_resources": len(available_resources),
                "total_available": total_available,
                "committed_resources": len(committed),
                "available_teams": len(available_teams),
                "active_missions": len(active_missions),
                "network_needs_match": len(shared_ctx.get_needs_for_resource_type(need_type)),
            },
            "private_factors": [
                f"{len(available_resources)} {need_type} resource(s) available",
                f"{len(available_teams)} team(s) available",
                f"{len(active_missions)} active mission(s)",
                f"{len(committed)} resource(s) committed",
            ],
            "uncertainty": uncertainty,
            "proposed_publication": proposed_publication,
            "action_required": action_required,
            "analysis_time_ms": elapsed_ms,
        }

        # Audit log
        self._audit("analyze_need", {
            "need_id": need_id,
            "recommendation": recommendation,
            "action_required": action_required,
        })

        return result

    def get_situation_summary(
        self,
        private_ctx: PrivateOrganizationContext,
        shared_ctx: SharedNetworkContext,
    ) -> dict:
        """
        Get a summary of the organization's current situation.
        """
        available_resources = private_ctx.get_available_resources()
        committed_resources = private_ctx.get_committed_resources()
        available_teams = private_ctx.get_available_teams()
        active_missions = private_ctx.get_active_missions()

        private_summary = {
            "total_resources": len(private_ctx.resources),
            "available_resources": len(available_resources),
            "committed_resources": len(committed_resources),
            "total_teams": len(private_ctx.teams),
            "available_teams": len(available_teams),
            "active_missions": len(active_missions),
        }

        network_summary = {
            "open_needs": len(shared_ctx.open_needs),
            "active_operations": len(shared_ctx.active_operations),
            "published_offers": len(shared_ctx.published_offers),
        }

        attention = []

        if available_resources:
            resource_types = set(r.get("type", r.get("resource_type", "")) for r in available_resources)
            for rt in resource_types:
                matching_needs = shared_ctx.get_needs_for_resource_type(rt)
                if matching_needs:
                    attention.append({
                        "type": "opportunity",
                        "detail": f"You have available {rt} and there are {len(matching_needs)} matching need(s) in the network",
                        "severity": "information",
                    })

        if committed_resources and active_missions:
            attention.append({
                "type": "status",
                "detail": f"{len(committed_resources)} resource(s) committed across {len(active_missions)} active mission(s)",
                "severity": "stable",
            })

        if available_teams and not active_missions:
            attention.append({
                "type": "status",
                "detail": f"{len(available_teams)} team(s) available with no active missions",
                "severity": "information",
            })

        return {
            "org_id": self.org_id,
            "private_summary": private_summary,
            "network_summary": network_summary,
            "attention": attention,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _audit(self, action: str, details: dict) -> None:
        """Record an audit event (operational rationale, not chain-of-thought)."""
        self.audit_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "org_id": self.org_id,
            "action": action,
            "details": details,
        })


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def analyze_need_for_org(
    org_id: str,
    need: dict,
    private_resources: list[dict] = None,
    private_teams: list[dict] = None,
    private_missions: list[dict] = None,
    network_needs: list[dict] = None,
    network_operations: list[dict] = None,
    network_overrides: list[dict] = None,
) -> dict:
    """
    Convenience function to analyze a need for an organization.
    """
    private_ctx = PrivateOrganizationContext(
        org_id=org_id,
        resources=private_resources or [],
        teams=private_teams or [],
        missions=private_missions or [],
    )

    shared_ctx = SharedNetworkContext(
        open_needs=network_needs or [],
        active_operations=network_operations or [],
        relevant_overrides=network_overrides or [],
    )

    agent = NGOMainAgent(org_id)
    return agent.analyze_need(need, private_ctx, shared_ctx)


def get_org_situation(
    org_id: str,
    private_resources: list[dict] = None,
    private_teams: list[dict] = None,
    private_missions: list[dict] = None,
    network_needs: list[dict] = None,
    network_operations: list[dict] = None,
    network_offers: list[dict] = None,
    network_overrides: list[dict] = None,
) -> dict:
    """
    Convenience function to get organization situation summary.
    """
    private_ctx = PrivateOrganizationContext(
        org_id=org_id,
        resources=private_resources or [],
        teams=private_teams or [],
        missions=private_missions or [],
    )

    shared_ctx = SharedNetworkContext(
        open_needs=network_needs or [],
        active_operations=network_operations or [],
        published_offers=network_offers or [],
        relevant_overrides=network_overrides or [],
    )

    agent = NGOMainAgent(org_id)
    return agent.get_situation_summary(private_ctx, shared_ctx)
