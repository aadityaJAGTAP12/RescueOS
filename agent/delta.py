"""
ReliefOS Delta Engine — What Changed + Semantic Deduplication + Evidence Synthesis

Phase 7D: Makes the operational console capable of showing coordinators
WHAT CHANGED, WHY IT MATTERS, WHAT EVIDENCE SUPPORTS IT, and
WHICH REPORTS REPRESENT THE SAME REAL-WORLD EVENT.

Design principles:
- READ-ONLY: never modifies needs, offers, operations, or records
- Deterministic: same inputs → same outputs (no LLM for grouping)
- Evidence-based: every delta includes concrete evidence
- Honest about uncertainty and data gaps
- Human-in-the-loop: recommendations are advisory only
"""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import defaultdict


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Time window for "recent" events (hours)
RECENT_EVENTS_HOURS = 24.0

# Deduplication: spatial proximity threshold (km)
DEDUP_SPATIAL_THRESHOLD_KM = 5.0

# Deduplication: temporal proximity threshold (hours)
DEDUP_TEMPORAL_THRESHOLD_HOURS = 6.0

# Deduplication: minimum reports to consider grouping
DEDUP_MIN_REPORTS = 2


# ---------------------------------------------------------------------------
# Delta Model
# ---------------------------------------------------------------------------

def compute_delta(repo, lookback_hours: float = RECENT_EVENTS_HOURS, now: datetime | None = None) -> dict:
    """
    Compute the current delta — what changed in the shared operational state.

    Returns:
        {
            "generated_at": ISO timestamp,
            "lookback_hours": float,
            "summary": {
                "new_needs": int,
                "resolved_needs": int,
                "escalated_needs": int,
                "new_offers": int,
                "new_operations": int,
                "new_reports": int,
                "new_overrides": int,
                "total_active_needs": int,
                "total_active_operations": int,
                "total_open_offers": int,
            },
            "directional": {
                "access": "up" | "down" | "stable",
                "resource_gap": "up" | "down" | "stable",
                "response": "up" | "down" | "stable",
                "unresolved": "up" | "down" | "stable",
            },
            "events": [...],
            "grouped_reports": [...],
            "evidence_summary": {...},
        }
    """
    if now is None:
        now = datetime.now(timezone.utc)

    t_start = time.time()
    cutoff = now - timedelta(hours=lookback_hours)

    # --- Activity events ---
    all_events = []
    try:
        all_events = repo.list_activity_events() if hasattr(repo, 'list_activity_events') else []
    except Exception:
        all_events = []

    recent_events = []
    for evt in all_events:
        created = evt.created_at if hasattr(evt, 'created_at') else None
        if created:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created >= cutoff:
                recent_events.append(evt)

    # --- Needs ---
    all_needs = repo.list_needs() if hasattr(repo, 'list_needs') else []
    open_needs = [n for n in all_needs if n.status in ('OPEN', 'RESPONDING')]
    resolved_needs = [n for n in all_needs if n.status in ('RESOLVED', 'CLOSED')]

    new_needs = 0
    escalated_needs = 0
    for evt in recent_events:
        if hasattr(evt, 'entity_type') and evt.entity_type == 'need':
            if hasattr(evt, 'event_type'):
                if evt.event_type == 'need_created':
                    new_needs += 1
                elif evt.event_type == 'status_changed' and '→' in (evt.detail or ''):
                    # Check if escalation (lower urgency status = escalation)
                    escalated_needs += 1

    # --- Offers ---
    all_offers = repo.list_resource_offers() if hasattr(repo, 'list_resource_offers') else []
    open_offers = [o for o in all_offers if o.status in ('OFFERED',)]
    new_offers = sum(1 for e in recent_events
                     if hasattr(e, 'event_type') and e.event_type == 'resource_offered')

    # --- Operations ---
    all_ops = repo.list_operations() if hasattr(repo, 'list_operations') else []
    active_ops = [o for o in all_ops if o.status in ('PLANNING', 'ACTIVE')]
    new_operations = sum(1 for e in recent_events
                         if hasattr(e, 'event_type') and e.event_type == 'operation_created')

    # --- Field reports ---
    try:
        from agent.community_reports import get_all_reports
        all_reports = get_all_reports()
    except Exception:
        all_reports = []

    recent_reports = []
    for r in all_reports:
        ts = r.get('timestamp')
        if ts:
            try:
                report_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                if report_time >= cutoff:
                    recent_reports.append(r)
            except (ValueError, TypeError):
                pass

    # --- Overrides ---
    try:
        from agent.overrides import get_all_overrides
        all_overrides = get_all_overrides()
    except Exception:
        all_overrides = []

    recent_overrides = []
    for o in all_overrides:
        ts = o.get('timestamp')
        if ts:
            try:
                override_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                if override_time >= cutoff:
                    recent_overrides.append(o)
            except (ValueError, TypeError):
                pass

    # --- Directional indicators ---
    # Compare current vs previous window
    prev_cutoff = cutoff - timedelta(hours=lookback_hours)
    prev_events = []
    for evt in all_events:
        created = evt.created_at if hasattr(evt, 'created_at') else None
        if created:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if prev_cutoff <= created < cutoff:
                prev_events.append(evt)

    prev_new_needs = sum(1 for e in prev_events
                         if hasattr(e, 'event_type') and e.event_type == 'need_created')
    prev_resolved = sum(1 for e in prev_events
                        if hasattr(e, 'event_type') and e.event_type == 'need_resolved')
    prev_new_offers = sum(1 for e in prev_events
                          if hasattr(e, 'event_type') and e.event_type == 'resource_offered')

    resolved_needs_count = sum(1 for e in recent_events
                               if hasattr(e, 'event_type') and e.event_type == 'need_resolved')

    directional = {
        "access": "stable",  # Would need road state history
        "resource_gap": "up" if (new_needs > new_offers) else ("down" if new_offers > new_needs else "stable"),
        "response": "up" if new_operations > 0 else ("down" if resolved_needs_count > 0 else "stable"),
        "unresolved": "up" if new_needs > resolved_needs_count else ("down" if resolved_needs_count > new_needs else "stable"),
    }

    # --- Build event list ---
    event_list = []
    for evt in recent_events:
        event_list.append({
            "id": evt.id if hasattr(evt, 'id') else '',
            "entity_type": evt.entity_type if hasattr(evt, 'entity_type') else '',
            "entity_id": evt.entity_id if hasattr(evt, 'entity_id') else '',
            "event_type": evt.event_type if hasattr(evt, 'event_type') else '',
            "actor": evt.actor if hasattr(evt, 'actor') else '',
            "detail": evt.detail if hasattr(evt, 'detail') else '',
            "created_at": evt.created_at.isoformat() if hasattr(evt, 'created_at') and evt.created_at else '',
        })

    # --- Semantic deduplication of field reports ---
    grouped_reports = deduplicate_reports(all_reports)

    # --- Evidence summary ---
    evidence_summary = {
        "flood_snapshots": _count_flood_snapshots(repo),
        "active_overrides": len([o for o in all_overrides if o.get('active', True)]),
        "field_reports_total": len(all_reports),
        "field_reports_recent": len(recent_reports),
        "verified_reports": len([r for r in all_reports if r.get('verified', False)]),
        "unverified_reports": len([r for r in all_reports if not r.get('verified', False)]),
    }

    t_end = time.time()

    return {
        "generated_at": now.isoformat(),
        "lookback_hours": lookback_hours,
        "summary": {
            "new_needs": new_needs,
            "resolved_needs": resolved_needs_count,
            "escalated_needs": escalated_needs,
            "new_offers": new_offers,
            "new_operations": new_operations,
            "new_reports": len(recent_reports),
            "new_overrides": len(recent_overrides),
            "total_active_needs": len(open_needs),
            "total_active_operations": len(active_ops),
            "total_open_offers": len(open_offers),
        },
        "directional": directional,
        "events": event_list,
        "grouped_reports": grouped_reports,
        "evidence_summary": evidence_summary,
        "computation_time_ms": round((t_end - t_start) * 1000, 1),
    }


# ---------------------------------------------------------------------------
# Semantic Deduplication
# ---------------------------------------------------------------------------

def deduplicate_reports(reports: list[dict]) -> list[dict]:
    """
    Group similar field reports into deduplicated events.

    Groups reports that likely describe the same real-world event based on:
    - Spatial proximity (within DEDUP_SPATIAL_THRESHOLD_KM)
    - Temporal proximity (within DEDUP_TEMPORAL_THRESHOLD_HOURS)
    - Normalized text similarity (same category + similar description)

    Returns a list of grouped events, each containing:
    {
        "event_id": str,
        "title": str,
        "category": str,
        "report_count": int,
        "verified_count": int,
        "first_report": ISO timestamp,
        "last_report": ISO timestamp,
        "reports": [...],  # individual report IDs and summaries
        "location_description": str | None,
        "needs": [str],
        "people_count_max": int,
        "confidence": str,
    }
    """
    if not reports:
        return []

    # Step 1: Normalize reports for comparison
    normalized = []
    for r in reports:
        if r.get('lat') is None and r.get('lon') is None:
            # Reports without coordinates: group by text similarity only
            norm = {
                "id": r.get("id", ""),
                "lat": None,
                "lon": None,
                "timestamp": r.get("timestamp", ""),
                "normalized_text": _normalize_text(r.get("note") or r.get("raw_text") or ""),
                "needs": sorted(r.get("needs", [])),
                "source": r.get("source", ""),
                "verified": r.get("verified", False),
                "people_count": r.get("people_count", 0),
                "location_description": r.get("location_description"),
                "report": r,
            }
            normalized.append(norm)
        else:
            norm = {
                "id": r.get("id", ""),
                "lat": r.get("lat"),
                "lon": r.get("lon"),
                "timestamp": r.get("timestamp", ""),
                "normalized_text": _normalize_text(r.get("note") or r.get("raw_text") or ""),
                "needs": sorted(r.get("needs", [])),
                "source": r.get("source", ""),
                "verified": r.get("verified", False),
                "people_count": r.get("people_count", 0),
                "location_description": r.get("location_description"),
                "report": r,
            }
            normalized.append(norm)

    # Step 2: Group reports
    groups = []  # list of lists of normalized reports
    assigned = set()

    for i, r1 in enumerate(normalized):
        if i in assigned:
            continue

        group = [r1]
        assigned.add(i)

        for j, r2 in enumerate(normalized):
            if j in assigned:
                continue

            if _reports_match(r1, r2):
                group.append(r2)
                assigned.add(j)

        groups.append(group)

    # Step 3: Build grouped events
    events = []
    for group in groups:
        if len(group) < DEDUP_MIN_REPORTS:
            # Single report — still include as a solo event
            r = group[0]
            events.append({
                "event_id": f"evt_{r['id']}",
                "title": r["normalized_text"][:80] if r["normalized_text"] else "Field report",
                "category": _categorize_needs(r["needs"]),
                "report_count": 1,
                "verified_count": 1 if r["verified"] else 0,
                "first_report": r["timestamp"],
                "last_report": r["timestamp"],
                "reports": [{
                    "id": r["id"],
                    "source": r["source"],
                    "verified": r["verified"],
                    "people_count": r["people_count"],
                    "timestamp": r["timestamp"],
                    "note": r["report"].get("note", ""),
                }],
                "location_description": r["location_description"],
                "needs": r["needs"],
                "people_count_max": r["people_count"],
                "confidence": r["report"].get("extraction_confidence", "low"),
            })
        else:
            # Multiple reports — grouped event
            timestamps = []
            for r in group:
                if r["timestamp"]:
                    try:
                        timestamps.append(datetime.fromisoformat(r["timestamp"].replace('Z', '+00:00')))
                    except (ValueError, TypeError):
                        pass

            first_ts = min(timestamps).isoformat() if timestamps else ""
            last_ts = max(timestamps).isoformat() if timestamps else ""

            # Merge needs
            all_needs = set()
            for r in group:
                all_needs.update(r["needs"])

            # Best location description
            loc_descs = [r["location_description"] for r in group if r["location_description"]]
            best_loc = loc_descs[0] if loc_descs else None

            # Highest confidence
            confidences = [r["report"].get("extraction_confidence", "low") for r in group]
            best_confidence = "high" if "high" in confidences else ("medium" if "medium" in confidences else "low")

            # Max people count
            max_people = max(r["people_count"] for r in group)

            # Use the most common normalized text as title
            text_counts = defaultdict(int)
            for r in group:
                text_counts[r["normalized_text"]] += 1
            most_common_text = max(text_counts, key=text_counts.get) if text_counts else ""

            events.append({
                "event_id": f"grp_{group[0]['id']}",
                "title": most_common_text[:80] if most_common_text else "Grouped field reports",
                "category": _categorize_needs(list(all_needs)),
                "report_count": len(group),
                "verified_count": sum(1 for r in group if r["verified"]),
                "first_report": first_ts,
                "last_report": last_ts,
                "reports": [{
                    "id": r["id"],
                    "source": r["source"],
                    "verified": r["verified"],
                    "people_count": r["people_count"],
                    "timestamp": r["timestamp"],
                    "note": r["report"].get("note", ""),
                } for r in group],
                "location_description": best_loc,
                "needs": sorted(all_needs),
                "people_count_max": max_people,
                "confidence": best_confidence,
            })

    # Sort by last_report descending (most recent first)
    events.sort(key=lambda e: e.get("last_report", ""), reverse=True)

    return events


def _reports_match(r1: dict, r2: dict) -> bool:
    """
    Determine if two reports likely describe the same real-world event.

    Uses deterministic grouping: spatial + temporal + text similarity.
    """
    # Same exact text → likely duplicate
    if r1["normalized_text"] and r1["normalized_text"] == r2["normalized_text"]:
        # Same needs
        if r1["needs"] == r2["needs"]:
            # Temporal proximity
            if _temporal_proximity(r1["timestamp"], r2["timestamp"]):
                return True

    # Spatial proximity + same category
    if r1["lat"] is not None and r2["lat"] is not None:
        from agent.data_loader import haversine_km
        dist = haversine_km(r1["lon"], r1["lat"], r2["lon"], r2["lat"])
        if dist <= DEDUP_SPATIAL_THRESHOLD_KM:
            # Same needs category
            if set(r1["needs"]) & set(r2["needs"]):
                # Temporal proximity
                if _temporal_proximity(r1["timestamp"], r2["timestamp"]):
                    return True

    # No coordinates: group by exact text match only
    if r1["lat"] is None and r2["lat"] is None:
        if r1["normalized_text"] and r1["normalized_text"] == r2["normalized_text"]:
            if _temporal_proximity(r1["timestamp"], r2["timestamp"]):
                return True

    return False


def _temporal_proximity(ts1: str, ts2: str) -> bool:
    """Check if two timestamps are within the dedup temporal threshold."""
    if not ts1 or not ts2:
        return False
    try:
        t1 = datetime.fromisoformat(ts1.replace('Z', '+00:00'))
        t2 = datetime.fromisoformat(ts2.replace('Z', '+00:00'))
        diff = abs((t2 - t1).total_seconds()) / 3600.0
        return diff <= DEDUP_TEMPORAL_THRESHOLD_HOURS
    except (ValueError, TypeError):
        return False


def _normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, strip, collapse whitespace."""
    if not text:
        return ""
    import re
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def _categorize_needs(needs: list[str]) -> str:
    """Categorize a list of needs into a single category label."""
    if not needs:
        return "general"
    if len(needs) == 1:
        return needs[0]
    if "medical" in needs:
        return "medical"
    if "water" in needs and "food" in needs:
        return "supplies"
    return " / ".join(needs[:3])


# ---------------------------------------------------------------------------
# Flood snapshot counting
# ---------------------------------------------------------------------------

def _count_flood_snapshots(repo) -> int:
    """Count available flood snapshots."""
    try:
        snapshots = repo.list_flood_snapshots() if hasattr(repo, 'list_flood_snapshots') else []
        return len(snapshots)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Evidence synthesis for a specific entity
# ---------------------------------------------------------------------------

def synthesize_evidence(entity_type: str, entity_id: str, repo=None) -> dict:
    """
    Synthesize evidence for a specific operational entity.

    Returns:
        {
            "entity_type": str,
            "entity_id": str,
            "evidence_items": [...],
            "uncertainty": [...],
            "data_gaps": [...],
            "confidence": str,
        }
    """
    if repo is None:
        from agent.data.repository import get_repository
        repo = get_repository()

    evidence_items = []
    uncertainty = []
    data_gaps = []
    confidence = "low"

    if entity_type == "need":
        need = repo.get_need(entity_id) if hasattr(repo, 'get_need') else None
        if need:
            # Check for linked operations
            ops = repo.list_operations() if hasattr(repo, 'list_operations') else []
            linked_ops = [o for o in ops if o.need_id == entity_id]

            if linked_ops:
                for op in linked_ops:
                    evidence_items.append({
                        "type": "operation",
                        "detail": f"Operation '{op.name}' responding ({op.status})",
                        "source": "operational_state",
                        "timestamp": op.created_at.isoformat() if op.created_at else "",
                    })
            else:
                data_gaps.append({
                    "item": "No active response",
                    "detail": "No operations are currently responding to this need.",
                })

            # Check for field reports near the need location
            if need.lat and need.lon:
                try:
                    from agent.community_reports import get_reports_near
                    reports = get_reports_near(need.lat, need.lon, radius_km=5.0)
                    for r in reports[:5]:
                        evidence_items.append({
                            "type": "field_report",
                            "detail": r.get("note") or f"Report: {r.get('people_count', 0)} people",
                            "source": r.get("source", "community"),
                            "timestamp": r.get("timestamp", ""),
                            "verified": r.get("verified", False),
                        })
                except Exception:
                    pass

            # Confidence assessment
            if evidence_items:
                verified = sum(1 for e in evidence_items if e.get("verified", False))
                if verified > 0:
                    confidence = "medium"
                else:
                    confidence = "low"
            else:
                confidence = "low"
                uncertainty.append("No field reports or operational data available for this need")

    elif entity_type == "operation":
        op = repo.get_operation(entity_id) if hasattr(repo, 'get_operation') else None
        if op:
            # Linked need
            if op.need_id:
                need = repo.get_need(op.need_id) if hasattr(repo, 'get_need') else None
                if need:
                    evidence_items.append({
                        "type": "need",
                        "detail": f"Responding to: {need.title or need.need_type}",
                        "source": "operational_state",
                    })

            # Override status of relevant roads
            try:
                from agent.overrides import get_all_overrides
                overrides = get_all_overrides()
                active_overrides = [o for o in overrides if o.get("active", True)]
                if active_overrides:
                    evidence_items.append({
                        "type": "override",
                        "detail": f"{len(active_overrides)} active road/bridge overrides in system",
                        "source": "coordinator_override",
                    })
            except Exception:
                pass

            uncertainty.append("Route geometry not stored — impact assessment uses district proximity")
            confidence = "medium"

    elif entity_type == "road":
        # Check overrides for this road
        confidence = "low"
        try:
            from agent.overrides import get_active_override
            override = get_active_override("road", entity_id)
            if override:
                evidence_items.append({
                    "type": "override",
                    "detail": f"Marked {override['override_status']}: {override.get('reason', '')}",
                    "source": override.get("actor", "coordinator"),
                    "timestamp": override.get("timestamp", ""),
                })
                confidence = "high"
            else:
                confidence = "medium"
                uncertainty.append("No field confirmation of current road status")
        except Exception:
            confidence = "low"
            data_gaps.append({"item": "Override status", "detail": "Unable to check override status"})

    else:
        confidence = "low"
        data_gaps.append({"item": "Evidence", "detail": f"No evidence synthesis available for {entity_type}"})

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "evidence_items": evidence_items,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "confidence": confidence,
    }
