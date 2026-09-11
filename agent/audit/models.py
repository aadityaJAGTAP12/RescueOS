"""
ReliefOS Consequential Action Audit Models — Production Hardening

Defines domain contracts for audit records capturing who did what, when,
to which entity, and from what state to what state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class AuditLog:
    """
    Immutable audit record for a consequential human or administrative action.
    """
    id: str = field(default_factory=lambda: f"aud_{str(uuid.uuid4())[:12]}")
    timestamp: Optional[datetime] = None
    actor_id: str = "system"
    organization_id: Optional[str] = None
    action: str = ""  # e.g. publish_offer, approve_proposal, decline_proposal, status_change, override_applied
    entity_type: str = ""  # need | offer | operation | proposal | override | user | membership
    entity_id: str = ""
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    ip_address: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "actor_id": self.actor_id,
            "organization_id": self.organization_id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "details": self.details,
            "ip_address": self.ip_address,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditLog:
        def _parse_dt(val):
            if val is None or isinstance(val, datetime):
                return val
            try:
                return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except Exception:
                return None

        return cls(
            id=data.get("id") or f"aud_{str(uuid.uuid4())[:12]}",
            timestamp=_parse_dt(data.get("timestamp")),
            actor_id=data.get("actor_id", "system"),
            organization_id=data.get("organization_id"),
            action=data.get("action", ""),
            entity_type=data.get("entity_type", ""),
            entity_id=data.get("entity_id", ""),
            from_state=data.get("from_state"),
            to_state=data.get("to_state"),
            details=data.get("details", {}),
            ip_address=data.get("ip_address"),
        )
