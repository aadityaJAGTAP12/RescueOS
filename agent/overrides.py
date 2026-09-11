"""
Local Knowledge Override — manual status overrides by coordinators.

A coordinator can mark a facility or road's status differently from what
the system (Overpass/cached) data says. The override is tracked alongside
the original data — never replacing it.

Design principles:
- Additive record only — never deletes or modifies underlying tool/cache data
- Both system_status and override are always accessible
- Override takes precedence for display, but original is never hidden

Storage (consolidated 2026-09-06):
All overrides are persisted through the shared data repository
(PostgresRepository when DATABASE_URL is set, InMemoryRepository for
tests/dev) — the same single source of truth as every other entity
(needs, offers, operations, field reports). This module previously used a
dedicated JSON file (data/overrides.json), which diverged from the
overrides DB table (the "split-brain" issue); the file is no longer read
or written by runtime code. agent/data/migration.py remains the one-time
importer that moved file contents into the DB.
"""

import uuid
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Repository access (single source of truth)
# ---------------------------------------------------------------------------

def _get_repo():
    from agent.data.repository import get_repository
    return get_repository()


def _record_to_model(record: dict):
    """Convert a legacy override dict into an Override model."""
    from agent.data.models import Override

    created_at = None
    raw_ts = record.get("timestamp") or record.get("created_at")
    if raw_ts:
        try:
            created_at = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_at = None

    return Override(
        id=record.get("id") or f"{uuid.uuid4()}"[:8],
        target_type=record.get("target_type", ""),
        target_id=record.get("target_id", ""),
        override_status=record.get("override_status", record.get("new_status", "")),
        reason=record.get("reason", ""),
        actor=record.get("actor", "coordinator"),
        system_status=record.get("system_status", "unknown"),
        active=record.get("active", True),
        created_at=created_at,
    )


def _load_overrides() -> list[dict]:
    """All override records (legacy dict shape) via the shared repository."""
    return [o.to_dict() for o in _get_repo().list_overrides()]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_override(
    target_type: str,
    target_id: str,
    new_status: str,
    reason: str,
    actor: str = "coordinator",
    system_status: str = "unknown",
) -> dict:
    """
    Records a manual override. Does NOT modify any underlying data.

    Args:
        target_type: "facility" or "road"
        target_id: identifier (e.g. facility name or road name)
        new_status: the new status value
        reason: why the coordinator is overriding
        actor: who is applying the override
        system_status: the current system status at time of override

    Returns:
        The override record that was stored.
    """
    record = {
        "id": f"{uuid.uuid4()}"[:8],
        "target_type": target_type,
        "target_id": target_id,
        "system_status": system_status,
        "override_status": new_status,
        "reason": reason,
        "actor": actor,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active": True,
    }

    repo = _get_repo()
    repo.upsert_override(_record_to_model(record))

    # Emit machine-facing AgentEvent
    try:
        from agent.agents.events import make_road_override_event, make_bridge_override_event
        if target_type == "road":
            repo.append_agent_event(make_road_override_event(
                override_id=record["id"],
                target_id=target_id,
                metadata={"new_status": new_status, "reason": reason, "actor": actor},
            ))
        elif target_type in ("bridge", "facility"):
            repo.append_agent_event(make_bridge_override_event(
                override_id=record["id"],
                target_id=target_id,
                metadata={"new_status": new_status, "reason": reason, "actor": actor},
            ))
    except Exception:
        pass

    return record


def _names_match(a: str, b: str) -> bool:
    """
    Case-insensitive substring match between two names.

    Returns True if either string contains the other AND the shorter name
    is at least half the length of the longer one. This handles the common
    case where a coordinator types "East Point Hospital" but Overpass stores
    "East Point Hospital And Research Centre", while preventing short names
    like "Mini PHC" from incorrectly matching both "Mini PHC, Charing" and
    "Mini PHC, Santak" (distinct facilities ~30 km apart).
    """
    a_low = a.strip().lower()
    b_low = b.strip().lower()

    # Exact match
    if a_low == b_low:
        return True

    # Substring match — allow if the shorter name is a prefix of the
    # longer one at a word boundary (handles truncations like
    # "East Point Hospital" vs "East Point Hospital And Research Centre")
    # or if the shorter name is at least 50 % of the longer one (avoids
    # short abbreviations colliding with multiple distinct facilities
    # sharing the same prefix, e.g. "Mini PHC" matching both
    # "Mini PHC, Charing" and "Mini PHC, Santak").
    if a_low in b_low or b_low in a_low:
        shorter, longer = (a_low, b_low) if len(a_low) <= len(b_low) else (b_low, a_low)
        if longer.startswith(shorter) and (len(shorter) == len(longer) or longer[len(shorter)] == ' '):
            return True
        if len(shorter) > len(longer) / 2:
            return True

    return False


def get_active_override(target_type: str, target_id: str) -> dict | None:
    """
    Returns the most recent active override for a target, if one exists.
    Uses case-insensitive substring matching so "East Point Hospital"
    matches "East Point Hospital And Research Centre".
    """
    overrides = _load_overrides()
    matching = [
        o for o in overrides
        if o["target_type"] == target_type
        and _names_match(o["target_id"], target_id)
        and o.get("active", True)
    ]
    if not matching:
        return None
    # Most recent by timestamp
    matching.sort(key=lambda o: o["timestamp"], reverse=True)
    return matching[0]


def get_operational_status(
    target_type: str,
    target_id: str,
    system_status: str,
) -> dict:
    """
    Returns the CURRENT operational view: if an override exists, it takes
    precedence for display purposes, but the response includes BOTH
    the system_status and the override (if any), never one replacing
    the other silently.

    Args:
        target_type: "facility" or "road"
        target_id: identifier
        system_status: current system-derived status

    Returns:
        {
            "operational_status": str,     # what's "true" for operations
            "system_status": str,          # what Overpass/cache says
            "override": {...} or null      # the active override, if any
        }
    """
    override = get_active_override(target_type, target_id)

    if override:
        return {
            "operational_status": override["override_status"],
            "system_status": system_status,
            "override": {
                "id": override["id"],
                "status": override["override_status"],
                "reason": override["reason"],
                "actor": override["actor"],
                "timestamp": override["timestamp"],
            },
        }
    else:
        return {
            "operational_status": system_status,
            "system_status": system_status,
            "override": None,
        }


def get_all_overrides() -> list[dict]:
    """Returns all overrides (for admin/debugging)."""
    return _load_overrides()


def clear_overrides() -> None:
    """
    Deactivate all overrides in the current store (testing helper).

    Note: rows are deactivated, not deleted — the repository API has no
    delete operation, preserving the audit trail.
    """
    repo = _get_repo()
    for o in repo.list_overrides():
        if o.active:
            o.active = False
            repo.upsert_override(o)
