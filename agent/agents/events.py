"""
ReliefOS Typed Agent Events — Phase 2A Runtime Architecture

Defines the machine-facing trigger representation (AgentEvent) that drives
deterministic routing, persistent outbox storage, and Main Agent delegation.

Preserves the clear three-way distinction:
- ActivityEvent: Historical operational audit record (PostgreSQL/PostGIS)
- Notification: Human-facing alert/signal
- AgentEvent: Machine-facing trigger for agent evaluation with explicit lifecycle
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class EventStatus(str, Enum):
    """Lifecycle states for durable AgentEvents."""
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"


class AgentEventType(str, Enum):
    """Authoritative domain event types supported by ReliefOS."""
    NEED_CREATED = "need.created"
    NEED_STATUS_CHANGED = "need.status_changed"
    OFFER_CREATED = "offer.created"
    OFFER_STATUS_CHANGED = "offer.status_changed"
    OPERATION_CREATED = "operation.created"
    OPERATION_STATUS_CHANGED = "operation.status_changed"
    FLOOD_SNAPSHOT_UPDATED = "flood.snapshot_updated"
    ROAD_OVERRIDE_APPLIED = "road.override.applied"
    BRIDGE_OVERRIDE_APPLIED = "bridge.override.applied"
    FIELD_REPORT_CREATED = "field_report.created"
    COORDINATION_PROPOSAL_CREATED = "coordination.proposal_created"
    COORDINATION_PROPOSAL_RECEIVED = "coordination.proposal_received"
    COORDINATION_PROPOSAL_UPDATED = "coordination.proposal_updated"


@dataclass
class AgentEvent:
    """
    Lightweight, typed domain event that references authoritative entities
    without duplicating the entire database state.
    """
    event_id: str = field(default_factory=lambda: f"evt_{str(uuid.uuid4())[:12]}")
    event_type: str = AgentEventType.NEED_CREATED.value
    entity_type: str = "need"  # need | offer | operation | flood_snapshot | road_override | bridge_override | field_report | coordination_proposal
    entity_id: str = ""
    status: str = EventStatus.PENDING.value
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "system"
    priority: str = "urgent"  # critical | urgent | information | stable
    district: Optional[str] = None
    organization_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3
    created_at: Optional[str] = None
    claimed_at: Optional[str] = None
    processed_at: Optional[str] = None
    error_detail: Optional[str] = None
    execution_result: Optional[dict[str, Any]] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = self.timestamp or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "id": self.event_id,
            "event_id": self.event_id,
            "event_type": self.event_type if isinstance(self.event_type, str) else self.event_type.value,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "status": self.status if isinstance(self.status, str) else self.status.value,
            "timestamp": self.timestamp,
            "created_at": self.created_at,
            "source": self.source,
            "priority": self.priority,
            "district": self.district,
            "organization_id": self.organization_id,
            "metadata": self.metadata,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "processed_at": self.processed_at,
            "error_detail": self.error_detail,
            "execution_result": self.execution_result,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentEvent:
        """Construct AgentEvent from dictionary."""
        event_id = data.get("event_id") or data.get("id") or f"evt_{str(uuid.uuid4())[:12]}"
        return cls(
            event_id=event_id,
            event_type=data.get("event_type", AgentEventType.NEED_CREATED.value),
            entity_type=data.get("entity_type", "need"),
            entity_id=data.get("entity_id", ""),
            status=data.get("status", EventStatus.PENDING.value),
            timestamp=data.get("timestamp", data.get("created_at", datetime.now(timezone.utc).isoformat())),
            source=data.get("source", "system"),
            priority=data.get("priority", "urgent"),
            district=data.get("district"),
            organization_id=data.get("organization_id"),
            metadata=data.get("metadata", {}),
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 3)),
            created_at=data.get("created_at"),
            processed_at=data.get("processed_at"),
            error_detail=data.get("error_detail"),
            execution_result=data.get("execution_result"),
        )


# ---------------------------------------------------------------------------
# Factory helpers for common domain events
# ---------------------------------------------------------------------------

def make_need_created_event(need_id: str, district: Optional[str] = None, priority: str = "urgent", metadata: Optional[dict] = None) -> AgentEvent:
    return AgentEvent(
        event_type=AgentEventType.NEED_CREATED.value,
        entity_type="need",
        entity_id=need_id,
        district=district,
        priority=priority,
        metadata=metadata or {},
    )


def make_need_status_changed_event(need_id: str, old_status: str, new_status: str, district: Optional[str] = None, priority: str = "urgent", metadata: Optional[dict] = None) -> AgentEvent:
    meta = {"old_status": old_status, "new_status": new_status, **(metadata or {})}
    return AgentEvent(
        event_type=AgentEventType.NEED_STATUS_CHANGED.value,
        entity_type="need",
        entity_id=need_id,
        district=district,
        priority=priority,
        metadata=meta,
    )


def make_offer_created_event(offer_id: str, org_id: Optional[str] = None, district: Optional[str] = None, priority: str = "urgent", metadata: Optional[dict] = None) -> AgentEvent:
    return AgentEvent(
        event_type=AgentEventType.OFFER_CREATED.value,
        entity_type="offer",
        entity_id=offer_id,
        district=district,
        organization_id=org_id,
        priority=priority,
        metadata=metadata or {},
    )


def make_offer_status_changed_event(offer_id: str, old_status: str, new_status: str, org_id: Optional[str] = None, district: Optional[str] = None, priority: str = "urgent", metadata: Optional[dict] = None) -> AgentEvent:
    meta = {"old_status": old_status, "new_status": new_status, **(metadata or {})}
    return AgentEvent(
        event_type=AgentEventType.OFFER_STATUS_CHANGED.value,
        entity_type="offer",
        entity_id=offer_id,
        district=district,
        organization_id=org_id,
        priority=priority,
        metadata=meta,
    )


def make_operation_created_event(operation_id: str, district: Optional[str] = None, org_id: Optional[str] = None, priority: str = "urgent", metadata: Optional[dict] = None) -> AgentEvent:
    return AgentEvent(
        event_type=AgentEventType.OPERATION_CREATED.value,
        entity_type="operation",
        entity_id=operation_id,
        district=district,
        organization_id=org_id,
        priority=priority,
        metadata=metadata or {},
    )


def make_operation_status_changed_event(operation_id: str, old_status: str, new_status: str, district: Optional[str] = None, org_id: Optional[str] = None, priority: str = "urgent", metadata: Optional[dict] = None) -> AgentEvent:
    meta = {"old_status": old_status, "new_status": new_status, **(metadata or {})}
    return AgentEvent(
        event_type=AgentEventType.OPERATION_STATUS_CHANGED.value,
        entity_type="operation",
        entity_id=operation_id,
        district=district,
        organization_id=org_id,
        priority=priority,
        metadata=meta,
    )


def make_flood_snapshot_event(snapshot_id: str, district: str, priority: str = "urgent", metadata: Optional[dict] = None) -> AgentEvent:
    return AgentEvent(
        event_type=AgentEventType.FLOOD_SNAPSHOT_UPDATED.value,
        entity_type="flood_snapshot",
        entity_id=snapshot_id,
        district=district,
        priority=priority,
        metadata=metadata or {},
    )


def make_road_override_event(override_id: str, target_id: str, district: Optional[str] = None, priority: str = "urgent", metadata: Optional[dict] = None) -> AgentEvent:
    return AgentEvent(
        event_type=AgentEventType.ROAD_OVERRIDE_APPLIED.value,
        entity_type="road_override",
        entity_id=override_id,
        district=district,
        priority=priority,
        metadata={"target_id": target_id, **(metadata or {})},
    )


def make_bridge_override_event(override_id: str, target_id: str, district: Optional[str] = None, priority: str = "urgent", metadata: Optional[dict] = None) -> AgentEvent:
    return AgentEvent(
        event_type=AgentEventType.BRIDGE_OVERRIDE_APPLIED.value,
        entity_type="bridge_override",
        entity_id=override_id,
        district=district,
        priority=priority,
        metadata={"target_id": target_id, **(metadata or {})},
    )


def make_field_report_event(report_id: str, district: Optional[str] = None, priority: str = "information", metadata: Optional[dict] = None) -> AgentEvent:
    return AgentEvent(
        event_type=AgentEventType.FIELD_REPORT_CREATED.value,
        entity_type="field_report",
        entity_id=report_id,
        district=district,
        priority=priority,
        metadata=metadata or {},
    )


def make_coordination_proposal_created_event(proposal_id: str, org_id: Optional[str] = None, need_id: Optional[str] = None, priority: str = "urgent", metadata: Optional[dict] = None) -> AgentEvent:
    return AgentEvent(
        event_type=AgentEventType.COORDINATION_PROPOSAL_CREATED.value,
        entity_type="coordination_proposal",
        entity_id=proposal_id,
        organization_id=org_id,
        priority=priority,
        metadata={"need_id": need_id, **(metadata or {})},
    )


def make_proposal_received_event(proposal_id: str, org_id: str, need_id: Optional[str] = None, priority: str = "urgent", metadata: Optional[dict] = None) -> AgentEvent:
    return AgentEvent(
        event_type=AgentEventType.COORDINATION_PROPOSAL_RECEIVED.value,
        entity_type="coordination_proposal",
        entity_id=proposal_id,
        organization_id=org_id,
        priority=priority,
        metadata={"need_id": need_id, **(metadata or {})},
    )


def make_coordination_proposal_updated_event(proposal_id: str, org_id: Optional[str] = None, need_id: Optional[str] = None, priority: str = "urgent", metadata: Optional[dict] = None) -> AgentEvent:
    return AgentEvent(
        event_type=AgentEventType.COORDINATION_PROPOSAL_UPDATED.value,
        entity_type="coordination_proposal",
        entity_id=proposal_id,
        organization_id=org_id,
        priority=priority,
        metadata={"need_id": need_id, **(metadata or {})},
    )
