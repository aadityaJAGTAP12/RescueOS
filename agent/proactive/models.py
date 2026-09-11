"""
ReliefOS Proactive Intelligence Models — Phase 2B Runtime Architecture

Defines data contracts for server-side proactive disaster intelligence:
- ProactiveScan: Log of a discrete background examination cycle.
- ProactiveFinding: Stateful, fingerprint-deduplicated finding with lifecycle (NEW, ACTIVE, RESOLVED).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ScanStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class FindingLifecycleStatus(str, Enum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


def generate_finding_fingerprint(
    domain: str,
    detector_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    finding_type: Optional[str] = None,
) -> str:
    """
    Generate a deterministic fingerprint for deduplicating proactive findings
    across subsequent heartbeat scans.
    """
    raw = f"{domain}:{detector_id}:{entity_type or ''}:{entity_id or ''}:{finding_type or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


@dataclass
class ProactiveFinding:
    """
    Stateful advisory finding produced during a proactive scan cycle.
    """
    id: str = field(default_factory=lambda: f"fnd_{str(uuid.uuid4())[:12]}")
    scan_id: Optional[str] = None
    fingerprint: str = ""
    domain: str = "general"
    detector_id: str = ""
    status: str = FindingLifecycleStatus.NEW.value
    severity: str = "medium"  # critical | urgent | high | medium | low | stable | information
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    title: str = ""
    summary: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    provenance: str = "INFERRED"
    uncertainty: list[str] = field(default_factory=list)
    data_gaps: list[dict[str, Any]] = field(default_factory=list)
    suggested_action: Optional[dict[str, Any]] = None
    first_detected_at: Optional[datetime] = None
    last_detected_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    notification_sent_at: Optional[datetime] = None
    severity_history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        now = datetime.now(timezone.utc)
        if self.first_detected_at is None:
            self.first_detected_at = now
        if self.last_detected_at is None:
            self.last_detected_at = now
        if not self.fingerprint:
            self.fingerprint = generate_finding_fingerprint(
                self.domain, self.detector_id, self.entity_type, self.entity_id, self.title
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "fingerprint": self.fingerprint,
            "domain": self.domain,
            "detector_id": self.detector_id,
            "status": self.status if isinstance(self.status, str) else self.status.value,
            "severity": self.severity,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "title": self.title,
            "summary": self.summary,
            "evidence": self.evidence,
            "provenance": self.provenance,
            "uncertainty": self.uncertainty,
            "data_gaps": self.data_gaps,
            "suggested_action": self.suggested_action,
            "first_detected_at": self.first_detected_at.isoformat() if self.first_detected_at else None,
            "last_detected_at": self.last_detected_at.isoformat() if self.last_detected_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "notification_sent_at": self.notification_sent_at.isoformat() if self.notification_sent_at else None,
            "severity_history": self.severity_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProactiveFinding:
        def _parse_dt(val):
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            try:
                return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except Exception:
                return None

        return cls(
            id=data.get("id") or f"fnd_{str(uuid.uuid4())[:12]}",
            scan_id=data.get("scan_id"),
            fingerprint=data.get("fingerprint", ""),
            domain=data.get("domain", "general"),
            detector_id=data.get("detector_id", ""),
            status=data.get("status", FindingLifecycleStatus.NEW.value),
            severity=data.get("severity", "medium"),
            entity_type=data.get("entity_type"),
            entity_id=data.get("entity_id"),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            evidence=data.get("evidence", {}),
            provenance=data.get("provenance", "INFERRED"),
            uncertainty=data.get("uncertainty", []),
            data_gaps=data.get("data_gaps", []),
            suggested_action=data.get("suggested_action"),
            first_detected_at=_parse_dt(data.get("first_detected_at")),
            last_detected_at=_parse_dt(data.get("last_detected_at")),
            resolved_at=_parse_dt(data.get("resolved_at")),
            notification_sent_at=_parse_dt(data.get("notification_sent_at")),
            severity_history=data.get("severity_history", []),
        )


@dataclass
class ProactiveScan:
    """
    Log record of a discrete proactive scan cycle.
    """
    id: str = field(default_factory=lambda: f"scan_{str(uuid.uuid4())[:12]}")
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    trigger: str = "scheduled"  # scheduled | manual_api | state_change
    status: str = ScanStatus.RUNNING.value
    scope: Optional[dict[str, Any]] = None
    detectors_run: list[str] = field(default_factory=list)
    specialists_invoked: list[str] = field(default_factory=list)
    findings_count: int = 0
    summary: Optional[str] = None
    metrics: Optional[dict[str, Any]] = None
    failures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "trigger": self.trigger,
            "status": self.status if isinstance(self.status, str) else self.status.value,
            "scope": self.scope,
            "detectors_run": self.detectors_run,
            "specialists_invoked": self.specialists_invoked,
            "findings_count": self.findings_count,
            "summary": self.summary,
            "metrics": self.metrics,
            "failures": self.failures,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProactiveScan:
        def _parse_dt(val):
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            try:
                return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except Exception:
                return None

        return cls(
            id=data.get("id") or f"scan_{str(uuid.uuid4())[:12]}",
            started_at=_parse_dt(data.get("started_at")) or datetime.now(timezone.utc),
            completed_at=_parse_dt(data.get("completed_at")),
            trigger=data.get("trigger", "scheduled"),
            status=data.get("status", ScanStatus.RUNNING.value),
            scope=data.get("scope"),
            detectors_run=data.get("detectors_run", []),
            specialists_invoked=data.get("specialists_invoked", []),
            findings_count=int(data.get("findings_count", 0)),
            summary=data.get("summary"),
            metrics=data.get("metrics"),
            failures=data.get("failures", []),
        )
