"""
ReliefOS Proactive Detectors — Base Class & Context (Phase 2B)

Defines the contract for all deterministic domain detectors.
All detectors:
- Are READ-ONLY: never mutate shared or NGO operational state
- Produce structured ProactiveFinding instances with deterministic fingerprints
- Specify the specialist agents that should be invoked if deeper reasoning is needed
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from agent.data.repository import DataRepository
from agent.proactive.models import ProactiveFinding


@dataclass
class ProactiveContext:
    """
    Context passed to each proactive detector during a scan cycle.
    """
    repo: DataRepository
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scope: Optional[dict[str, Any]] = None  # e.g. {"district_id": "sivasagar", "domain": "exposure"}
    previous_findings: dict[str, ProactiveFinding] = field(default_factory=dict)  # fingerprint -> finding
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def district_filter(self) -> Optional[str]:
        if self.scope and isinstance(self.scope, dict):
            return self.scope.get("district_id") or self.scope.get("district")
        return None

    @property
    def domain_filter(self) -> Optional[str]:
        if self.scope and isinstance(self.scope, dict):
            return self.scope.get("domain")
        return None


class ProactiveDetector(ABC):
    """
    Abstract base class for all proactive risk, gap, and conflict detectors.
    """
    detector_id: str = "base_detector"
    domain: str = "general"
    relevant_specialists: list[str] = []
    description: str = ""

    @abstractmethod
    def detect(self, context: ProactiveContext) -> list[ProactiveFinding]:
        """
        Execute deterministic inspection against repository state.
        Returns a list of ProactiveFinding objects.
        """
        raise NotImplementedError
