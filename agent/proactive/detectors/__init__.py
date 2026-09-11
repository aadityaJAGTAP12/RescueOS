"""
ReliefOS Proactive Detectors Package — Phase 2B
"""

from agent.proactive.detectors.base import ProactiveDetector, ProactiveContext
from agent.proactive.detectors.exposure import ExposureRiskDetector
from agent.proactive.detectors.access import AccessRiskDetector
from agent.proactive.detectors.medical import MedicalGapDetector
from agent.proactive.detectors.logistics import LogisticsGapDetector
from agent.proactive.detectors.coordination import CoordinationGapDetector
from agent.proactive.detectors.field_conflict import FieldConflictDetector
from agent.proactive.detectors.registry import (
    list_detectors,
    get_detector,
    select_relevant_detectors,
    ALL_DETECTORS,
)

__all__ = [
    "ProactiveDetector",
    "ProactiveContext",
    "ExposureRiskDetector",
    "AccessRiskDetector",
    "MedicalGapDetector",
    "LogisticsGapDetector",
    "CoordinationGapDetector",
    "FieldConflictDetector",
    "list_detectors",
    "get_detector",
    "select_relevant_detectors",
    "ALL_DETECTORS",
]
