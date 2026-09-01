"""
AI Coordinator — Read-Only Operational Findings (Phase 7B v1)

Provides deterministic, evidence-based analysis of shared operational state.
Detects three finding types:

1. Coordination Gap — needs with no responders beyond an age threshold
2. Duplicate Response — multiple organizations responding to the same need
3. Consequence Alert — active overrides affecting active operation routes

Design principles:
- READ-ONLY: never creates/modifies needs, offers, operations, or records
- District-agnostic: reasons from database state, no hardcoded names
- Evidence-based: every finding includes concrete evidence
- Honest about uncertainty and data gaps
- Human-in-the-loop: suggestions are advisory only
"""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Age threshold (hours) before a need is considered a coordination gap
COORDINATION_GAP_THRESHOLD_HOURS = 1.0


# ---------------------------------------------------------------------------
# Finding data structures
# ---------------------------------------------------------------------------

def _finding(
    type: str,
    severity: str,
    title: str,
    summary: str,
    location: str | None,
    evidence: dict,
    suggested_action: dict | None = None,
    review_target: dict | None = None,
    uncertainty: list[str] | None = None,
    data_gaps: list[str] | None = None,
) -> dict:
    """
    Build a standardized finding dict.

    review_target tells the frontend exactly how to navigate:
    {
        "panel_type": "need" | "operation" | "road",
        "entity_id": str,          # ID of the object to open
        "entity_data": dict | None, # full object dict (optional, for direct use)
        "map_center": [lat, lon] | None,  # where to move the map
        "district_id": str | None,  # district filter to apply
    }
    """
    return {
        "type": type,
        "severity": severity,
        "title": title,
        "summary": summary,
        "location": location,
        "evidence": evidence,
        "suggested_action": suggested_action,
        "review_target": review_target,
        "uncertainty": uncertainty or [],
        "data_gaps": data_gaps or [],
    }


def _severity_from_urgency(urgency: str) -> str:
    """Map need urgency to finding severity."""
    return {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }.get(urgency, "medium")


# ---------------------------------------------------------------------------
# Detector 1: Coordination Gap
# ---------------------------------------------------------------------------

def detect_coordination_gaps(
    repo,
    threshold_hours: float = COORDINATION_GAP_THRESHOLD_HOURS,
    now: datetime | None = None,
) -> list[dict]:
    """
    Detect OPEN needs that have no offers or operations associated with them
    beyond the configured age threshold.

    Args:
        repo: DataRepository instance
        threshold_hours: hours before a need is flagged
        now: current time (for testability)

    Returns:
        List of coordination_gap finding dicts
    """
    if now is None:
        now = datetime.now(timezone.utc)

    findings = []
    open_needs = repo.list_needs(status="OPEN")

    for need in open_needs:
        # Calculate age
        created = need.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = now - created
        age_hours = age.total_seconds() / 3600.0

        if age_hours < threshold_hours:
            continue

        # Check for associated offers (same district, OFFERED/ACCEPTED/DEPLOYED)
        offers = repo.list_resource_offers(district_id=need.district_id)
        relevant_offers = [
            o for o in offers
            if o.status in ("OFFERED", "ACCEPTED", "DEPLOYED")
        ]

        # Check for associated operations (linked to this need)
        all_ops = repo.list_operations(district_id=need.district_id)
        relevant_ops = [
            o for o in all_ops
            if o.need_id == need.id and o.status in ("PLANNING", "ACTIVE")
        ]

        # No responders at all → coordination gap
        if len(relevant_offers) == 0 and len(relevant_ops) == 0:
            age_str = _format_age(age_hours)
            severity = _severity_from_urgency(need.urgency)

            # Build review target: the frontend should open this need
            need_dict = need.to_dict()
            review_target = {
                "panel_type": "need",
                "entity_id": need.id,
                "entity_data": need_dict,
                "map_center": [need.lat, need.lon] if need.lat and need.lon else None,
                "district_id": need.district_id,
            }

            findings.append(_finding(
                type="coordination_gap",
                severity=severity,
                title=f"Uncovered {need.need_type} request",
                summary=(
                    f"A {need.need_type}-supply need has remained without a "
                    f"responder for {age_str}."
                ),
                location=need.location_name or need.district_id or "Unknown",
                evidence={
                    "need_id": need.id,
                    "need_title": need.title,
                    "need_type": need.need_type,
                    "need_urgency": need.urgency,
                    "need_age_hours": round(age_hours, 1),
                    "created_at": need.created_at.isoformat(),
                    "district_id": need.district_id,
                    "offers": len(relevant_offers),
                    "operations": len(relevant_ops),
                },
                suggested_action={
                    "label": "Review Need",
                    "action": "review_need",
                },
                review_target=review_target,
            ))

    # Sort by severity (critical first), then by age descending
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: (
        severity_order.get(f["severity"], 9),
        -f["evidence"]["need_age_hours"],
    ))

    return findings


# ---------------------------------------------------------------------------
# Detector 2: Duplicate Response
# ---------------------------------------------------------------------------

def detect_duplicate_responses(repo) -> list[dict]:
    """
    Detect needs where multiple organizations/offers/operations are responding
    in a way that may represent duplicated effort.

    A need is considered potentially duplicated if:
    - 2+ active operations are linked to it, OR
    - 2+ organizations have accepted/deployed offers for the same district need

    Args:
        repo: DataRepository instance

    Returns:
        List of duplicate_response finding dicts
    """
    findings = []
    open_needs = repo.list_needs(status="OPEN")
    responding_needs = repo.list_needs(status="RESPONDING")
    all_active_needs = open_needs + responding_needs

    # Group operations by need_id
    ops_by_need: dict[str, list] = {}
    active_ops = repo.list_operations(status="ACTIVE") + repo.list_operations(status="PLANNING")
    for op in active_ops:
        if op.need_id:
            ops_by_need.setdefault(op.need_id, []).append(op)

    # Find needs with multiple operations
    for need in all_active_needs:
        ops = ops_by_need.get(need.id, [])
        if len(ops) >= 2:
            org_ids = list(set(
                op.lead_organization_id for op in ops
                if op.lead_organization_id
            ))
            op_ids = [op.id for op in ops]

            need_dict = need.to_dict()
            review_target = {
                "panel_type": "need",
                "entity_id": need.id,
                "entity_data": need_dict,
                "map_center": [need.lat, need.lon] if need.lat and need.lon else None,
                "district_id": need.district_id,
            }

            findings.append(_finding(
                type="duplicate_response",
                severity="medium",
                title="Multiple responders on one need",
                summary=(
                    f"{len(ops)} operations appear to be responding to the "
                    f"same {need.need_type} request."
                ),
                location=need.location_name or need.district_id or "Unknown",
                evidence={
                    "need_id": need.id,
                    "need_title": need.title,
                    "need_type": need.need_type,
                    "organizations": org_ids,
                    "operation_ids": op_ids,
                    "operation_count": len(ops),
                },
                suggested_action={
                    "label": "Review Need",
                    "action": "review_need",
                },
                review_target=review_target,
            ))

    # Also check for multiple accepted/deployed offers in same district for same resource type
    # Group offers by district_id + resource_type
    all_offers = repo.list_resource_offers(status="ACCEPTED") + \
                 repo.list_resource_offers(status="DEPLOYED")
    offers_by_key: dict[str, list] = {}
    for offer in all_offers:
        key = f"{offer.district_id}:{offer.resource_type}"
        offers_by_key.setdefault(key, []).append(offer)

    # Only flag if there's an active need for that resource type in that district
    needs_by_key: dict[str, list] = {}
    for need in all_active_needs:
        key = f"{need.district_id}:{need.need_type}"
        needs_by_key.setdefault(key, []).append(need)

    for key, offers in offers_by_key.items():
        if len(offers) < 2:
            continue
        district_id, resource_type = key.split(":", 1)
        matching_needs = needs_by_key.get(key, [])

        # Skip if no need exists for this resource type in this district
        if not matching_needs:
            continue

        org_ids = list(set(o.organization_id for o in offers))
        if len(org_ids) < 2:
            continue  # Same org — not really duplicated

        need = matching_needs[0]  # Use the first matching need for context
        need_dict = need.to_dict()
        review_target = {
            "panel_type": "need",
            "entity_id": need.id,
            "entity_data": need_dict,
            "map_center": [need.lat, need.lon] if need.lat and need.lon else None,
            "district_id": need.district_id,
        }

        findings.append(_finding(
            type="duplicate_response",
            severity="medium",
            title=f"Multiple {resource_type} responses in {district_id}",
            summary=(
                f"{len(org_ids)} organizations have accepted/deployed "
                f"{resource_type} resources for the same area."
            ),
            location=district_id,
            evidence={
                "need_id": need.id,
                "need_type": need.need_type,
                "resource_type": resource_type,
                "organizations": org_ids,
                "offer_ids": [o.id for o in offers],
                "offer_count": len(offers),
                "district_id": district_id,
            },
            suggested_action={
                "label": "Review Need",
                "action": "review_need",
            },
            review_target=review_target,
        ))

    return findings


# ---------------------------------------------------------------------------
# Detector 3: Consequence Alert
# ---------------------------------------------------------------------------

def detect_consequence_alerts(repo) -> list[dict]:
    """
    Detect active overrides on roads/bridges that affect routes associated
    with active operations.

    Reuses the existing override → routing → route-safety foundation
    without creating a new routing system.

    Args:
        repo: DataRepository instance

    Returns:
        List of consequence_alert finding dicts
    """
    from agent.overrides import get_all_overrides
    from agent.tools.routing_tool import (
        check_route_override_status,
        _BLOCKED_STATUSES,
    )

    findings = []

    # Get all active overrides for roads
    all_overrides = get_all_overrides()
    blocked_overrides = [
        o for o in all_overrides
        if o.get("active", True)
        and o.get("target_type") == "road"
        and o.get("override_status") in _BLOCKED_STATUSES
    ]

    if not blocked_overrides:
        return findings

    # Get active operations
    active_ops = repo.list_operations(status="ACTIVE") + \
                 repo.list_operations(status="PLANNING")

    for op in active_ops:
        if op.lat is None or op.lon is None:
            continue

        # Check each blocked override to see if it's geographically relevant
        for override in blocked_overrides:
            road_name = override.get("target_id", "")
            override_status = override.get("override_status", "")
            override_reason = override.get("reason", "")

            # Use the existing override check to see if this operation's
            # location is affected. We create a minimal route geometry
            # (operation start → operation location) and check intersection.
            # Since we don't have the operation's planned route geometry,
            # we check if any blocked road is in the same district.
            op_district = op.district_id

            # Find the road in the repository to check district
            if op_district:
                roads = repo.get_roads(op_district)
                for road in roads:
                    if road.name == road_name or road.id == road_name:
                        # Found a blocked road in the same district as the operation
                        is_bridge = road.is_bridge or (road.tags or {}).get("bridge") == "yes"
                        segment_type = "bridge" if is_bridge else "road"

                        # Build review target: open the affected operation
                        op_dict = op.to_dict()
                        review_target = {
                            "panel_type": "operation",
                            "entity_id": op.id,
                            "entity_data": op_dict,
                            "map_center": [op.lat, op.lon] if op.lat and op.lon else None,
                            "district_id": op.district_id,
                        }

                        findings.append(_finding(
                            type="consequence_alert",
                            severity="critical",
                            title="Active operation route may be blocked",
                            summary=(
                                f"A reported {segment_type} closure ({road_name}) "
                                f"may affect the planned route for active operation "
                                f"'{op.name}'."
                            ),
                            location=op.location_name or op.district_id or "Unknown",
                            evidence={
                                "operation_id": op.id,
                                "operation_name": op.name,
                                "operation_status": op.status,
                                "operation_district": op.district_id,
                                "override_id": override.get("id", ""),
                                "blocked_road": road_name,
                                "blocked_segment_type": segment_type,
                                "override_status": override_status,
                                "override_reason": override_reason,
                                "route_valid": False,
                                "route_valid_reason": (
                                    f"Blocked {segment_type} ({road_name}) in same "
                                    f"district as active operation"
                                ),
                            },
                            suggested_action={
                                "label": "Review Operation",
                                "action": "review_operation",
                            },
                            review_target=review_target,
                            uncertainty=[
                                (
                                    "Route validity assessed by district proximity — "
                                    "exact operation route geometry is not stored, so "
                                    "this is an advisory alert, not a confirmed blockage."
                                ),
                            ],
                        ))
                        break  # Only one alert per override per operation

    # Deduplicate: if same operation + same road, keep only one
    seen = set()
    unique_findings = []
    for f in findings:
        key = (f["evidence"]["operation_id"], f["evidence"]["blocked_road"])
        if key not in seen:
            seen.add(key)
            unique_findings.append(f)

    return unique_findings


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------

def run_coordinator_analysis(repo=None) -> dict:
    """
    Run the full coordinator analysis and return structured findings.

    This is the main entry point called by the API endpoint.

    Args:
        repo: DataRepository instance (uses get_repository() if None)

    Returns:
        {
            "generated_at": ISO timestamp,
            "findings": [...],
            "summary": {total, critical, high, medium, low},
            "data_gaps": [...]
        }
    """
    if repo is None:
        from agent.data.repository import get_repository
        repo = get_repository()

    t_start = time.time()

    # Run all detectors
    gaps = detect_coordination_gaps(repo)
    duplicates = detect_duplicate_responses(repo)
    consequences = detect_consequence_alerts(repo)

    all_findings = gaps + duplicates + consequences

    # Compute summary
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in all_findings:
        sev = f.get("severity", "medium")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Collect data gaps from all findings
    all_data_gaps = []
    for f in all_findings:
        for gap in f.get("data_gaps", []):
            if gap not in all_data_gaps:
                all_data_gaps.append(gap)

    # Add general data gaps
    general_gaps = [
        {
            "item": "Operation route geometry",
            "status": "not_stored",
            "detail": (
                "Active operations do not store planned route geometry. "
                "Consequence alerts use district proximity as a proxy."
            ),
        },
        {
            "item": "Real-time field confirmation",
            "status": "not_connected",
            "detail": (
                "No real-time field reports confirm current road/bridge "
                "passability. Override status is coordinator-reported."
            ),
        },
    ]
    for gap in general_gaps:
        if gap["item"] not in [g.get("item", "") for g in all_data_gaps]:
            all_data_gaps.append(gap)

    t_end = time.time()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "findings": all_findings,
        "summary": {
            "total": len(all_findings),
            "critical": severity_counts["critical"],
            "high": severity_counts["high"],
            "medium": severity_counts["medium"],
            "low": severity_counts["low"],
        },
        "data_gaps": all_data_gaps,
        "analysis_time_ms": round((t_end - t_start) * 1000, 1),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_age(hours: float) -> str:
    """Format age in hours to a human-readable string."""
    if hours < 1:
        minutes = int(hours * 60)
        return f"{minutes}m"
    h = int(hours)
    m = int((hours - h) * 60)
    if h == 1:
        return f"1h {m}m"
    return f"{h}h {m}m"
