"""
ReliefOS Proactive Coordination Gap & Duplicate Response Detector — Phase 2B

Deterministic detector identifying uncovered needs and redundant responder allocations.
Delegates to: ["coordination", "logistics"]
"""

from __future__ import annotations

from typing import Any
from agent.proactive.detectors.base import ProactiveDetector, ProactiveContext
from agent.proactive.models import ProactiveFinding
from agent.ai_coordinator import detect_coordination_gaps, detect_duplicate_responses


class CoordinationGapDetector(ProactiveDetector):
    detector_id = "coordination_gap"
    domain = "coordination"
    relevant_specialists = ["coordination", "logistics"]
    description = "Detects unassigned operational needs and duplicate NGO deployments."

    def detect(self, context: ProactiveContext) -> list[ProactiveFinding]:
        findings: list[ProactiveFinding] = []
        repo = context.repo
        district_filter = context.district_filter

        # 1. Coordination gaps (needs open with no responders)
        raw_gaps = detect_coordination_gaps(repo, threshold_hours=0.5, now=context.now)
        for g in raw_gaps:
            evidence = g.get("evidence", {})
            dist_id = evidence.get("district_id")
            if district_filter and dist_id and dist_id.lower() != district_filter.lower():
                continue

            findings.append(ProactiveFinding(
                domain=self.domain,
                detector_id=self.detector_id,
                entity_type="need",
                entity_id=evidence.get("need_id"),
                title=g.get("title", "Uncovered Operational Need"),
                summary=g.get("summary", ""),
                severity=g.get("severity", "medium"),
                evidence=evidence,
                provenance="INFERRED",
                uncertainty=g.get("uncertainty", []),
                data_gaps=g.get("data_gaps", []),
                suggested_action=g.get("suggested_action"),
            ))

        # 2. Duplicate responses (multiple orgs on one need)
        raw_dups = detect_duplicate_responses(repo)
        for d in raw_dups:
            evidence = d.get("evidence", {})
            dist_id = evidence.get("district_id")
            if district_filter and dist_id and dist_id.lower() != district_filter.lower():
                continue

            findings.append(ProactiveFinding(
                domain=self.domain,
                detector_id="duplicate_response",
                entity_type="need" if evidence.get("need_id") else "district",
                entity_id=evidence.get("need_id") or dist_id,
                title=d.get("title", "Duplicate Operational Deployment"),
                summary=d.get("summary", ""),
                severity=d.get("severity", "medium"),
                evidence=evidence,
                provenance="INFERRED",
                uncertainty=d.get("uncertainty", []),
                data_gaps=d.get("data_gaps", []),
                suggested_action=d.get("suggested_action"),
            ))

        return findings
