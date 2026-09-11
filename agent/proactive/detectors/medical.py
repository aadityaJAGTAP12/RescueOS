"""
ReliefOS Proactive Medical Gap Detector — Phase 2B

Deterministic detector evaluating critical health emergencies, medical facility risks,
and shortages of medical personnel / supplies.
Delegates to: ["medical", "logistics"]
"""

from __future__ import annotations

from typing import Any
from agent.proactive.detectors.base import ProactiveDetector, ProactiveContext
from agent.proactive.models import ProactiveFinding


class MedicalGapDetector(ProactiveDetector):
    detector_id = "medical_gap"
    domain = "medical"
    relevant_specialists = ["medical", "logistics"]
    description = "Detects acute medical emergencies, inundated health centers, and unmet medical supply demands."

    def detect(self, context: ProactiveContext) -> list[ProactiveFinding]:
        findings: list[ProactiveFinding] = []
        repo = context.repo
        district_filter = context.district_filter

        # 1. Unmet critical/urgent medical needs
        open_needs = repo.list_needs(status="OPEN")
        if district_filter:
            open_needs = [n for n in open_needs if n.district_id and n.district_id.lower() == district_filter.lower()]

        medical_needs = [
            n for n in open_needs
            if n.need_type in ("medical", "medication", "first_aid", "ambulance", "casualty")
            or n.urgency in ("critical", "urgent")
        ]

        # Check available medical offers
        all_offers = repo.list_resource_offers(status="AVAILABLE") + repo.list_resource_offers(status="OFFERED")
        med_offers = [
            o for o in all_offers
            if o.resource_type in ("medical", "medication", "first_aid", "ambulance", "doctors", "nurses")
        ]

        for m_need in medical_needs:
            # Check if there is an active operation or offer targeting this need
            ops = repo.list_operations(district_id=m_need.district_id) if m_need.district_id else []
            need_ops = [op for op in ops if op.need_id == m_need.id and op.status in ("ACTIVE", "PLANNING")]
            
            district_med_offers = [o for o in med_offers if o.district_id == m_need.district_id]

            if not need_ops:
                severity = "critical" if m_need.urgency == "critical" else "high"
                title = f"Unassigned Medical Emergency: {m_need.title}"
                summary = (
                    f"Medical need '{m_need.title}' (urgency: {m_need.urgency}) in "
                    f"{m_need.district_id or 'unknown district'} has no active response operation. "
                    f"{len(district_med_offers)} local medical resource offer(s) available in district."
                )
                evidence = {
                    "need_id": m_need.id,
                    "need_title": m_need.title,
                    "urgency": m_need.urgency,
                    "need_type": m_need.need_type,
                    "district_id": m_need.district_id,
                    "available_district_medical_offers": len(district_med_offers),
                }
                uncertainty = ["Triage priority assessment based solely on reported need text"]
                data_gaps = [{"field": "patient_count", "description": "Exact number of patients requiring critical stabilization"}]
                suggested_action = {
                    "label": "Triage Medical Need",
                    "action": "triage_medical",
                    "panel_type": "need",
                    "entity_id": m_need.id,
                    "map_center": [m_need.lat, m_need.lon] if m_need.lat and m_need.lon else None,
                    "district_id": m_need.district_id,
                }
                findings.append(ProactiveFinding(
                    domain=self.domain,
                    detector_id=self.detector_id,
                    entity_type="need",
                    entity_id=m_need.id,
                    title=title,
                    summary=summary,
                    severity=severity,
                    evidence=evidence,
                    provenance="REPORTED",
                    uncertainty=uncertainty,
                    data_gaps=data_gaps,
                    suggested_action=suggested_action,
                ))

        # 2. Inundated or compromised medical facilities
        districts = repo.list_districts()
        if district_filter:
            districts = [d for d in districts if d.id.lower() == district_filter.lower()]

        for d in districts:
            facilities = repo.list_medical_facilities(district_id=d.id) if hasattr(repo, "list_medical_facilities") else []
            for fac in facilities:
                in_flood = getattr(fac, "in_flood_zone", False) or (fac.metadata and fac.metadata.get("in_flood_zone"))
                if in_flood:
                    title = f"Medical Facility Inundation Risk: {fac.name}"
                    summary = f"Healthcare facility '{fac.name}' ({fac.facility_type or 'clinic'}) in {d.name or d.id} is situated within an active flood zone."
                    findings.append(ProactiveFinding(
                        domain=self.domain,
                        detector_id=self.detector_id,
                        entity_type="medical_facility",
                        entity_id=fac.id,
                        title=title,
                        summary=summary,
                        severity="high",
                        evidence={
                            "facility_id": fac.id,
                            "facility_name": fac.name,
                            "facility_type": fac.facility_type,
                            "district_id": d.id,
                            "coordinates": [fac.lat, fac.lon] if fac.lat and fac.lon else None,
                        },
                        provenance="INFERRED",
                        suggested_action={
                            "label": "Inspect Facility Status",
                            "action": "view_facility",
                            "panel_type": "medical_facility",
                            "entity_id": fac.id,
                            "district_id": d.id,
                        },
                    ))

        return findings
