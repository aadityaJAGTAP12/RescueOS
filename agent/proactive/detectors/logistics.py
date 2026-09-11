"""
ReliefOS Proactive Logistics Gap Detector — Phase 2B

Deterministic detector evaluating district-level supply imbalances, resource deficits,
and unmatched logistical requirements.
Delegates to: ["logistics", "coordination"]
"""

from __future__ import annotations

from typing import Any
from agent.proactive.detectors.base import ProactiveDetector, ProactiveContext
from agent.proactive.models import ProactiveFinding


class LogisticsGapDetector(ProactiveDetector):
    detector_id = "logistics_gap"
    domain = "logistics"
    relevant_specialists = ["logistics", "coordination"]
    description = "Detects resource deficits and unfulfilled logistical demands across operational zones."

    def detect(self, context: ProactiveContext) -> list[ProactiveFinding]:
        findings: list[ProactiveFinding] = []
        repo = context.repo
        district_filter = context.district_filter

        districts = repo.list_districts()
        if district_filter:
            districts = [d for d in districts if d.id.lower() == district_filter.lower()]

        for d in districts:
            needs = repo.list_needs(district_id=d.id, status="OPEN")
            offers = repo.list_resource_offers(district_id=d.id, status="AVAILABLE") + \
                     repo.list_resource_offers(district_id=d.id, status="OFFERED")

            # Group needs by need_type
            needs_by_type: dict[str, list] = {}
            for n in needs:
                ntype = n.need_type or "general"
                needs_by_type.setdefault(ntype, []).append(n)

            # Group offers by resource_type
            offers_by_type: dict[str, list] = {}
            for o in offers:
                rtype = o.resource_type or "general"
                offers_by_type.setdefault(rtype, []).append(o)

            for ntype, type_needs in needs_by_type.items():
                matching_offers = offers_by_type.get(ntype, [])
                total_demanded = 0
                for n in type_needs:
                    qty = getattr(n, "quantity", None)
                    if qty is None and n.requested_resources:
                        qty = sum(r.get("quantity", 1) for r in n.requested_resources if isinstance(r, dict))
                    total_demanded += (qty or 1)

                total_supplied = sum(getattr(o, "quantity", 1) or 1 for o in matching_offers)

                if total_supplied < total_demanded:
                    deficit = total_demanded - total_supplied
                    urgent_count = sum(1 for n in type_needs if n.urgency in ("critical", "high"))
                    severity = "critical" if urgent_count > 0 and total_supplied == 0 else ("high" if deficit > 5 else "medium")
                    
                    title = f"Logistics Deficit: {ntype.capitalize()} Shortage in {d.name or d.id}"
                    summary = (
                        f"District {d.name or d.id} faces a deficit of {deficit} units for '{ntype}'. "
                        f"{len(type_needs)} open need(s) demanding {total_demanded} vs {len(matching_offers)} offer(s) supplying {total_supplied}."
                    )
                    evidence = {
                        "district_id": d.id,
                        "resource_type": ntype,
                        "total_demanded": total_demanded,
                        "total_supplied": total_supplied,
                        "deficit": deficit,
                        "open_needs_count": len(type_needs),
                        "available_offers_count": len(matching_offers),
                        "urgent_needs_count": urgent_count,
                    }
                    uncertainty = ["Quantity units may not be standardized across reporting NGOs"]
                    data_gaps = [{"field": "warehouse_reserve_levels", "description": "Regional buffer stock inventory unrecorded"}]
                    suggested_action = {
                        "label": "Mobilize Resources",
                        "action": "mobilize_logistics",
                        "district_id": d.id,
                        "resource_type": ntype,
                    }
                    findings.append(ProactiveFinding(
                        domain=self.domain,
                        detector_id=self.detector_id,
                        entity_type="resource_deficit",
                        entity_id=f"{d.id}:{ntype}",
                        title=title,
                        summary=summary,
                        severity=severity,
                        evidence=evidence,
                        provenance="INFERRED",
                        uncertainty=uncertainty,
                        data_gaps=data_gaps,
                        suggested_action=suggested_action,
                    ))

        return findings
