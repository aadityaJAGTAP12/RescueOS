"""
ReliefOS Proactive Access Risk Detector — Phase 2B

Deterministic detector evaluating road/bridge blockages, route severance,
and operational transit conflicts.
Delegates to: ["access", "logistics", "medical"]
"""

from __future__ import annotations

from typing import Any
from agent.proactive.detectors.base import ProactiveDetector, ProactiveContext
from agent.proactive.models import ProactiveFinding
from agent.overrides import get_all_overrides


class AccessRiskDetector(ProactiveDetector):
    detector_id = "access_risk"
    domain = "access"
    relevant_specialists = ["access", "logistics", "medical"]
    description = "Detects road and bridge blockages that compromise operational access and supply corridors."

    def detect(self, context: ProactiveContext) -> list[ProactiveFinding]:
        findings: list[ProactiveFinding] = []
        repo = context.repo
        district_filter = context.district_filter

        # 1. Inspect active overrides on roads and bridges
        overrides = repo.list_overrides() if hasattr(repo, "list_overrides") else []
        if not overrides:
            overrides = get_all_overrides()

        def _get_prop(obj, name, default=""):
            if isinstance(obj, dict):
                return obj.get(name, default)
            return getattr(obj, name, default)

        active_road_blocks = [
            o for o in overrides
            if _get_prop(o, "target_type") in ("road", "bridge")
            and _get_prop(o, "override_status") in ("blocked", "flooded", "impassable", "restricted")
            and _get_prop(o, "active", True)
        ]

        # Active operations
        active_ops = repo.list_operations(status="ACTIVE") + repo.list_operations(status="PLANNING")
        if district_filter:
            active_ops = [op for op in active_ops if op.district_id and op.district_id.lower() == district_filter.lower()]

        for road_block in active_road_blocks:
            target_name = _get_prop(road_block, "target_id")
            target_type = _get_prop(road_block, "target_type")
            override_status = _get_prop(road_block, "override_status")
            reason = _get_prop(road_block, "reason")
            actor = _get_prop(road_block, "actor", "coordinator")

            # Check if any active operations mention or route through this road/bridge
            affected_ops = []
            for op in active_ops:
                op_route = op.route or []
                op_dest = op.destination or ""
                op_notes = op.notes or ""
                if (
                    target_name.lower() in op_dest.lower()
                    or target_name.lower() in op_notes.lower()
                    or any(target_name.lower() in str(r).lower() for r in op_route)
                ):
                    affected_ops.append(op)

            if affected_ops:
                op_ids = [op.id for op in affected_ops]
                severity = "critical" if any(op.operation_type == "evacuation" for op in affected_ops) else "high"
                title = f"Transit Route Compromised: {target_name}"
                summary = (
                    f"Active override reports '{target_name}' is {override_status}. "
                    f"{len(affected_ops)} active operation(s) ({', '.join(op_ids)}) transit or target this corridor."
                )
                evidence = {
                    "target_type": target_type,
                    "target_id": target_name,
                    "override_status": override_status,
                    "override_reason": reason,
                    "actor": actor,
                    "affected_operation_ids": op_ids,
                }
                uncertainty = ["Corridor alternate routing capability not evaluated"]
                data_gaps = [{"field": "detour_route_clearance", "description": "Verification required whether bypass roads are passable"}]
                suggested_action = {
                    "label": "Reroute Operations",
                    "action": "reroute_operation",
                    "panel_type": "operation",
                    "entity_id": op_ids[0],
                }
                findings.append(ProactiveFinding(
                    domain=self.domain,
                    detector_id=self.detector_id,
                    entity_type="road_blockage",
                    entity_id=target_name,
                    title=title,
                    summary=summary,
                    severity=severity,
                    evidence=evidence,
                    provenance="OBSERVED",
                    uncertainty=uncertainty,
                    data_gaps=data_gaps,
                    suggested_action=suggested_action,
                ))
            else:
                # Flag isolated road/bridge blockage as general access advisory
                title = f"Corridor Blockage: {target_name}"
                summary = f"Infrastructure {target_type} '{target_name}' is flagged {override_status}: {reason}."
                findings.append(ProactiveFinding(
                    domain=self.domain,
                    detector_id=self.detector_id,
                    entity_type=target_type,
                    entity_id=target_name,
                    title=title,
                    summary=summary,
                    severity="medium",
                    evidence={
                        "target_type": target_type,
                        "target_id": target_name,
                        "override_status": override_status,
                        "reason": reason,
                    },
                    provenance="OBSERVED",
                    suggested_action={
                        "label": "Review Access Status",
                        "action": "review_access",
                    },
                ))

        return findings
