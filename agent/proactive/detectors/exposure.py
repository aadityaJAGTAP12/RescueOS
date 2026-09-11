"""
ReliefOS Proactive Exposure Risk Detector — Phase 2B

Deterministic detector evaluating flood inundation overlays against settlements,
critical facilities, and population clusters.
Delegates to: ["situation", "exposure", "evidence"]
"""

from __future__ import annotations

from typing import Any
from agent.proactive.detectors.base import ProactiveDetector, ProactiveContext
from agent.proactive.models import ProactiveFinding


class ExposureRiskDetector(ProactiveDetector):
    detector_id = "exposure_risk"
    domain = "exposure"
    relevant_specialists = ["situation", "exposure", "evidence"]
    description = "Detects flood inundation overlapping settlements and critical infrastructure."

    def detect(self, context: ProactiveContext) -> list[ProactiveFinding]:
        findings: list[ProactiveFinding] = []
        repo = context.repo
        district_filter = context.district_filter

        districts = repo.list_districts()
        if district_filter:
            districts = [d for d in districts if d.id.lower() == district_filter.lower()]

        for district in districts:
            # Fetch latest flood snapshot
            snapshot = repo.get_latest_flood_snapshot(district.id)
            if not snapshot:
                continue

            # Check settlements in district
            settlements = repo.list_settlements(district_id=district.id)
            for s in settlements:
                # Check if settlement is exposed
                # If PostGIS / spatial data exists, check in_flood_zone or calculate proximity
                is_exposed = getattr(s, "in_flood_zone", False) or getattr(s, "inundated", False)
                pop = getattr(s, "population", 0) or 0

                # Also check metadata or attributes
                if not is_exposed and s.metadata:
                    is_exposed = bool(s.metadata.get("in_flood_zone") or s.metadata.get("inundated"))

                if is_exposed:
                    severity = "critical" if pop >= 5000 else ("high" if pop >= 1000 else "medium")
                    title = f"Inundation Risk: {s.name} ({district.name or district.id})"
                    summary = (
                        f"Settlement '{s.name}' with estimated population {pop:,} is within the active "
                        f"flood inundation zone observed in snapshot '{snapshot.id}'."
                    )
                    evidence = {
                        "district_id": district.id,
                        "settlement_id": s.id,
                        "settlement_name": s.name,
                        "population": pop,
                        "snapshot_id": snapshot.id,
                        "snapshot_observed_at": snapshot.observed_at.isoformat() if hasattr(snapshot.observed_at, "isoformat") else str(snapshot.observed_at),
                        "coordinates": [s.lat, s.lon] if s.lat and s.lon else None,
                    }
                    uncertainty = ["Remote sensing timestamp latency", "Terrain elevation model resolution"]
                    data_gaps = [{"field": "ground_truth_depth", "description": "Actual flood water depth unverified by field scout"}]
                    suggested_action = {
                        "label": "Inspect Settlement Exposure",
                        "action": "view_exposure",
                        "panel_type": "settlement",
                        "entity_id": s.id,
                        "map_center": [s.lat, s.lon] if s.lat and s.lon else None,
                        "district_id": district.id,
                    }
                    findings.append(ProactiveFinding(
                        domain=self.domain,
                        detector_id=self.detector_id,
                        entity_type="settlement",
                        entity_id=s.id,
                        title=title,
                        summary=summary,
                        severity=severity,
                        evidence=evidence,
                        provenance="INFERRED",
                        uncertainty=uncertainty,
                        data_gaps=data_gaps,
                        suggested_action=suggested_action,
                    ))

            # Also check if overall district has high flooded area without recent situation updates
            flood_area = getattr(snapshot, "flood_area_sqkm", None) or (snapshot.metadata and snapshot.metadata.get("flood_area_sqkm")) or 0.0
            if flood_area > 50.0 or snapshot.polygon_count >= 5:
                title = f"Extensive Flood Inundation in {district.name or district.id}"
                summary = f"Satellite analysis indicates substantial submerged land in {district.name or district.id}."
                findings.append(ProactiveFinding(
                    domain=self.domain,
                    detector_id=self.detector_id,
                    entity_type="district",
                    entity_id=district.id,
                    title=title,
                    summary=summary,
                    severity="high",
                    evidence={
                        "district_id": district.id,
                        "flood_area_sqkm": flood_area,
                        "polygon_count": snapshot.polygon_count,
                        "snapshot_id": snapshot.id,
                    },
                    provenance="OBSERVED",
                    suggested_action={
                        "label": "Review District Flood Extent",
                        "action": "view_district_flood",
                        "district_id": district.id,
                    },
                ))

        return findings

