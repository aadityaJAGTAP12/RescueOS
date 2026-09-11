"""
ReliefOS Audit Logging Service — Production Hardening

Captures tamper-evident records of consequential human actions (approvals, declines,
resource allocations, overrides, membership changes) in durable storage.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional
from flask import g, request

from agent.audit.models import AuditLog
from agent.validation.validators import sanitize_sensitive_data

if TYPE_CHECKING:
    from agent.data.repository import Repository

logger = logging.getLogger("reliefos.audit")


def get_current_actor_id() -> str:
    """Resolve current actor ID from Flask request context if available."""
    try:
        if hasattr(g, "principal") and g.principal is not None:
            return g.principal.user_id
        if hasattr(g, "current_user") and g.current_user is not None:
            return g.current_user.id
    except Exception:
        pass
    return "system"


def get_current_ip() -> Optional[str]:
    """Extract client IP from request headers or remote address."""
    try:
        if request:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
            return request.remote_addr
    except Exception:
        pass
    return None


def record_audit_log(
    repository: Repository,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    from_state: Optional[str] = None,
    to_state: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """
    Persist an audit entry for a consequential state mutation or decision.
    """
    resolved_actor = actor_id or get_current_actor_id()
    resolved_ip = ip_address or get_current_ip()
    safe_details = sanitize_sensitive_data(details or {})

    log_entry = AuditLog(
        actor_id=resolved_actor,
        organization_id=organization_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        from_state=from_state,
        to_state=to_state,
        details=safe_details,
        ip_address=resolved_ip,
    )

    saved_entry = repository.create_audit_log(log_entry)
    logger.info(
        f"[AUDIT] actor={saved_entry.actor_id} org={saved_entry.organization_id} "
        f"action={saved_entry.action} {saved_entry.entity_type}:{saved_entry.entity_id} "
        f"({saved_entry.from_state} -> {saved_entry.to_state})"
    )
    return saved_entry
