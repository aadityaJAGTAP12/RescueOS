"""
ReliefOS Agent Base Contracts — Phase 1 Runtime Architecture

Defines the common contract for ReliefOS agents:
- FindingProvenance (OBSERVED, DERIVED, USER_PROVIDED, ASSUMED, SYNTHETIC, UNKNOWN)
- FindingSeverity (CRITICAL, URGENT, INFORMATION, STABLE)
- AgentFinding (structured, evidence-backed finding output)
- Agent (base protocol/class for bounded analysis and event handling)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable


class FindingProvenance(str, Enum):
    """Origin and grounding classification for agent findings."""
    OBSERVED = "OBSERVED"        # Direct factual sensor/database data (e.g. satellite flood snapshot, PostGIS geometry)
    DERIVED = "DERIVED"          # Computed from other observations / spatial models
    USER_PROVIDED = "USER_PROVIDED"  # Explicit coordinator or citizen input (e.g. need request, road override)
    ASSUMED = "ASSUMED"          # Inferred or heuristic estimation based on available context
    SYNTHETIC = "SYNTHETIC"      # Synthetic data / test fixtures
    UNKNOWN = "UNKNOWN"          # Unverified or missing grounding


class FindingSeverity(str, Enum):
    """Standardized urgency/severity levels across all domains."""
    CRITICAL = "critical"
    URGENT = "urgent"
    INFORMATION = "information"
    STABLE = "stable"


@dataclass
class AgentFinding:
    """
    Typed, structured output produced by a ReliefOS agent.

    Confidence represents confidence in this finding given its evidence (0.0 to 1.0),
    NOT absolute truth.
    """
    agent_id: str
    domain: str
    finding_type: str
    summary: str
    severity: str = FindingSeverity.INFORMATION.value
    confidence: float = 1.0
    provenance: FindingProvenance = FindingProvenance.OBSERVED
    evidence: list[dict[str, Any]] = field(default_factory=list)
    data_gaps: list[dict[str, Any]] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    location: Optional[str] = None
    recommended_action: Optional[dict[str, Any] | str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert finding to standard dictionary representation."""
        return {
            "agent_id": self.agent_id,
            "domain": self.domain,
            "finding_type": self.finding_type,
            "summary": self.summary,
            "severity": self.severity,
            "confidence": self.confidence,
            "provenance": self.provenance.value if isinstance(self.provenance, FindingProvenance) else str(self.provenance),
            "evidence": self.evidence,
            "data_gaps": self.data_gaps,
            "uncertainty": self.uncertainty,
            "related_entity_type": self.related_entity_type,
            "related_entity_id": self.related_entity_id,
            "location": self.location,
            "recommended_action": self.recommended_action,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentFinding:
        """Construct an AgentFinding from a dictionary."""
        prov_val = data.get("provenance", FindingProvenance.OBSERVED.value)
        try:
            provenance = FindingProvenance(prov_val)
        except ValueError:
            provenance = FindingProvenance.UNKNOWN

        return cls(
            agent_id=data.get("agent_id", "unknown_agent"),
            domain=data.get("domain", "general"),
            finding_type=data.get("finding_type", "general_finding"),
            summary=data.get("summary", ""),
            severity=data.get("severity", FindingSeverity.INFORMATION.value),
            confidence=float(data.get("confidence", 1.0)),
            provenance=provenance,
            evidence=data.get("evidence", []),
            data_gaps=data.get("data_gaps", []),
            uncertainty=data.get("uncertainty", []),
            related_entity_type=data.get("related_entity_type"),
            related_entity_id=data.get("related_entity_id"),
            location=data.get("location"),
            recommended_action=data.get("recommended_action"),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


@runtime_checkable
class Agent(Protocol):
    """
    Standard contract for all ReliefOS agents (Network, NGO, and Specialists).

    Defines identity, domain responsibility, allowed context boundaries,
    allowed tools, and event triggers.
    """
    agent_id: str
    name: str
    domain: str
    allowed_context: list[str]
    allowed_tools: list[str]
    accepted_event_types: list[str]

    def analyze(self, context: Any) -> list[AgentFinding]:
        """Perform analysis over the provided context and return structured findings."""
        ...

    def handle_event(self, event: Any, context: Any) -> list[AgentFinding]:
        """Process an incoming AgentEvent and return relevant findings."""
        ...
