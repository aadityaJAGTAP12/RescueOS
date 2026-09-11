"""
NGO Inventory Specialist Agent — Organization-level resource & inventory evaluation.

Operates strictly over PrivateOrganizationContext and never leaks uncommitted inventory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType
from agent.matching_core import compare_need_resource


class NGOInventoryAgent:
    """
    NGO Specialist Agent responsible for private resource stock analysis,
    unit matching, and sufficiency calculations.
    """
    agent_id: str = "ngo_specialist_inventory"
    name: str = "NGO Inventory Agent"
    domain: str = "inventory"
    allowed_context: list[str] = ["org_private_state", "shared_state"]
    allowed_tools: list[str] = ["matching_core"]
    accepted_event_types: list[str] = [
        AgentEventType.NEED_CREATED.value,
        AgentEventType.COORDINATION_PROPOSAL_RECEIVED.value,
    ]

    def __init__(self, org_id: str):
        self.org_id = org_id

    def evaluate_resource_availability(
        self,
        need_type: str,
        requested_resources: list[dict],
        private_ctx: Any,
    ) -> dict[str, Any]:
        """
        Evaluate availability, unit compatibility, and sufficiency for a need type.
        """
        available_resources = private_ctx.get_available_resources(need_type)
        total_available = sum(r.get("quantity", 0) for r in available_resources)
        committed = private_ctx.get_committed_resources()

        # Deterministic comparison using matching_core
        resource_facts = [
            compare_need_resource(
                requested_resources,
                r.get("type", r.get("resource_type", "")),
                r.get("quantity", 0),
                r.get("unit"),
                need_type,
            )
            for r in available_resources
        ]

        if resource_facts:
            first_facts = resource_facts[0]
            requested_quantity = first_facts.requested_quantity
            unit_match = all(f.unit_match for f in resource_facts)
            type_match = all(f.type_match for f in resource_facts)
        else:
            empty_facts = compare_need_resource(requested_resources, need_type, 0, None, need_type)
            requested_quantity = empty_facts.requested_quantity
            unit_match = empty_facts.unit_match
            type_match = empty_facts.type_match

        if not type_match or not unit_match:
            sufficiency = "insufficient"
        elif requested_quantity is None:
            sufficiency = "unknown"
        elif total_available >= requested_quantity:
            sufficiency = "sufficient"
        else:
            sufficiency = "insufficient"

        return {
            "available_resources": available_resources,
            "total_available": total_available,
            "committed_count": len(committed),
            "requested_quantity": requested_quantity,
            "unit_match": unit_match,
            "type_match": type_match,
            "sufficiency": sufficiency,
        }

    def analyze(self, private_ctx: Any) -> list[AgentFinding]:
        """Analyze overall inventory state for the organization."""
        available = private_ctx.get_available_resources()
        committed = private_ctx.get_committed_resources()
        total_qty = sum(r.get("quantity", 0) for r in available)

        findings = [
            AgentFinding(
                agent_id=self.agent_id,
                domain=self.domain,
                finding_type="inventory_summary",
                summary=f"{len(available)} available resource batches ({total_qty} total units), {len(committed)} committed batches",
                severity=FindingSeverity.STABLE.value if available else FindingSeverity.URGENT.value,
                confidence=1.0,
                provenance=FindingProvenance.OBSERVED,
                evidence=[{"total_available": total_qty, "batch_count": len(available)}],
            )
        ]
        return findings

    def handle_event(self, event: AgentEvent, private_ctx: Any, need_type: Optional[str] = None, requested_resources: Optional[list] = None) -> list[AgentFinding]:
        """Evaluate inventory response capability for a specific event."""
        n_type = need_type or event.metadata.get("need_type", "other")
        req = requested_resources or event.metadata.get("requested_resources", [])
        eval_result = self.evaluate_resource_availability(n_type, req, private_ctx)

        severity = FindingSeverity.STABLE.value if eval_result["sufficiency"] == "sufficient" else FindingSeverity.URGENT.value

        finding = AgentFinding(
            agent_id=self.agent_id,
            domain=self.domain,
            finding_type="resource_fit",
            summary=f"Inventory assessment for {n_type}: {eval_result['total_available']} units available ({eval_result['sufficiency']})",
            severity=severity,
            confidence=1.0,
            provenance=FindingProvenance.OBSERVED,
            evidence=[{
                "available_quantity": eval_result["total_available"],
                "requested_quantity": eval_result["requested_quantity"],
                "unit_match": eval_result["unit_match"],
                "sufficiency": eval_result["sufficiency"],
            }],
            related_entity_type=event.entity_type,
            related_entity_id=event.entity_id,
        )
        return [finding]
