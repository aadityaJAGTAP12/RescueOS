"""
ReliefOS Proactive Detectors Registry — Phase 2B

Central registry and deterministic selection engine for all proactive detectors.
"""

from __future__ import annotations

from typing import Optional
from agent.proactive.detectors.base import ProactiveDetector, ProactiveContext
from agent.proactive.detectors.exposure import ExposureRiskDetector
from agent.proactive.detectors.access import AccessRiskDetector
from agent.proactive.detectors.medical import MedicalGapDetector
from agent.proactive.detectors.logistics import LogisticsGapDetector
from agent.proactive.detectors.coordination import CoordinationGapDetector
from agent.proactive.detectors.field_conflict import FieldConflictDetector


ALL_DETECTORS: list[ProactiveDetector] = [
    ExposureRiskDetector(),
    AccessRiskDetector(),
    MedicalGapDetector(),
    LogisticsGapDetector(),
    CoordinationGapDetector(),
    FieldConflictDetector(),
]

_DETECTOR_MAP: dict[str, ProactiveDetector] = {
    d.detector_id: d for d in ALL_DETECTORS
}


def list_detectors() -> list[ProactiveDetector]:
    """Return all registered proactive detectors."""
    return list(ALL_DETECTORS)


def get_detector(detector_id: str) -> Optional[ProactiveDetector]:
    """Retrieve a detector by its unique identifier."""
    return _DETECTOR_MAP.get(detector_id)


def select_relevant_detectors(context: ProactiveContext) -> list[ProactiveDetector]:
    """
    Deterministically select which detectors should execute for the given scan context.
    If scope specifies a domain, only detectors for that domain run.
    If scope specifies specific detector_ids, only those run.
    Otherwise, all detectors run.
    """
    if context.scope and isinstance(context.scope, dict):
        # Specific detector IDs requested
        detector_ids = context.scope.get("detector_ids") or context.scope.get("detectors")
        if detector_ids:
            return [d for d in ALL_DETECTORS if d.detector_id in detector_ids]

        # Specific domain requested
        domain = context.scope.get("domain")
        if domain:
            return [d for d in ALL_DETECTORS if d.domain.lower() == domain.lower()]

    return list(ALL_DETECTORS)
