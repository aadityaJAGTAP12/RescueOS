"""
ReliefOS Proactive Field Conflict & Report Gap Detector — Phase 2B

Deterministic detector evaluating field scout reports, trapped civilian intelligence,
and unverified community ground reports.
Delegates to: ["field", "medical", "evidence"]
"""

from __future__ import annotations

from typing import Any
from agent.proactive.detectors.base import ProactiveDetector, ProactiveContext
from agent.proactive.models import ProactiveFinding


class FieldConflictDetector(ProactiveDetector):
    detector_id = "field_conflict"
    domain = "field"
    relevant_specialists = ["field", "medical", "evidence"]
    description = "Detects urgent field report intelligence with missing operational coverage."

    def detect(self, context: ProactiveContext) -> list[ProactiveFinding]:
        findings: list[ProactiveFinding] = []
        repo = context.repo
        district_filter = context.district_filter

        districts = repo.list_districts()
        if district_filter:
            districts = [d for d in districts if d.id.lower() == district_filter.lower()]

        for d in districts:
            reports = repo.list_field_reports(district_id=d.id)
            for r in reports:
                people = getattr(r, "people_count", 0) or 0
                needs = getattr(r, "needs", []) or []
                verification_state = getattr(r, "verification_state", "UNVERIFIED")

                # Flag high-consequence reports (>= 10 people or urgent medical/trapped mentions)
                is_urgent = people >= 10 or any(n in ("rescue", "trapped", "medical", "first_aid") for n in needs)
                if not is_urgent:
                    continue

                # Check if there is an active operation nearby
                active_ops = repo.list_operations(district_id=d.id, status="ACTIVE")
                has_operation = False
                for op in active_ops:
                    if op.target_location and r.location_description and r.location_description.lower() in op.target_location.lower():
                        has_operation = True
                        break

                if not has_operation:
                    severity = "critical" if people >= 20 else ("high" if people >= 5 else "medium")
                    title = f"Urgent Field Report Unaddressed in {d.name or d.id}"
                    summary = (
                        f"Field report '{r.id}' indicates {people} persons requiring {', '.join(needs) or 'assistance'} "
                        f"at {r.location_description or 'unspecified location'} with no linked active operation."
                    )
                    evidence = {
                        "report_id": r.id,
                        "district_id": d.id,
                        "people_count": people,
                        "needs": needs,
                        "verification_state": str(verification_state),
                        "location_description": r.location_description,
                        "coordinates": [r.lat, r.lon] if r.lat and r.lon else None,
                    }
                    uncertainty = ["Report verification state: " + str(verification_state)]
                    data_gaps = [{"field": "ground_truth_verification", "description": "Needs field agent or local authority cross-verification"}]
                    suggested_action = {
                        "label": "Dispatch Field Team",
                        "action": "dispatch_field",
                        "panel_type": "field_report",
                        "entity_id": r.id,
                        "map_center": [r.lat, r.lon] if r.lat and r.lon else None,
                        "district_id": d.id,
                    }
                    findings.append(ProactiveFinding(
                        domain=self.domain,
                        detector_id=self.detector_id,
                        entity_type="field_report",
                        entity_id=r.id,
                        title=title,
                        summary=summary,
                        severity=severity,
                        evidence=evidence,
                        provenance=getattr(r, "provenance", "INFERRED") if isinstance(getattr(r, "provenance", None), str) else "INFERRED",
                        uncertainty=uncertainty,
                        data_gaps=data_gaps,
                        suggested_action=suggested_action,
                    ))

        return findings
