"""
Access / Routing Worker — Network-level access and routing analysis.

Reuses existing road status, bridge status, overrides, and routing capabilities.
"""

from __future__ import annotations


def analyze_access(repo) -> dict:
    """
    Analyze access and routing conditions based on road/bridge status
    and active overrides.
    """
    findings = []
    evidence = []
    uncertainty = []
    data_gaps = []
    recommendations = []

    # Get active overrides
    try:
        from agent.overrides import get_all_overrides
        overrides = get_all_overrides()
        active_overrides = [o for o in overrides if o.get("active", True)]
    except Exception:
        active_overrides = []

    road_overrides = [o for o in active_overrides if o.get("target_type") == "road"]

    evidence.append({
        "type": "override_summary",
        "detail": f"{len(road_overrides)} active road/bridge overrides",
    })

    # Analyze blocked routes
    blocked = [o for o in road_overrides if o.get("override_status") in ("blocked", "submerged", "damaged")]
    if blocked:
        for override in blocked:
            findings.append({
                "type": "access_blocked",
                "severity": "urgent",
                "title": f"Route blocked: {override.get('target_id', 'unknown')}",
                "summary": f"Override status: {override.get('override_status')} — {override.get('reason', 'no reason given')}",
                "location": override.get("target_id", ""),
            })

    # Check operations affected by blocked routes
    try:
        active_ops = repo.list_operations(status="ACTIVE") + repo.list_operations(status="PLANNING")
        for op in active_ops:
            op_district = op.district_id if hasattr(op, 'district_id') else op.get('district_id', '')
            for override in blocked:
                if override.get("target_id", "") in (op_district or ""):
                    uncertainty.append(f"Operation '{op.name if hasattr(op, 'name') else op.get('name', '')}' may be affected by blocked route")
    except Exception:
        pass

    # Unknown road conditions
    if not active_overrides:
        uncertainty.append("No road status overrides in system — actual road conditions unknown")

    return _build_result(findings, evidence, uncertainty, data_gaps, recommendations)


def _build_result(findings, evidence, uncertainty, data_gaps, recommendations):
    return {
        "worker": "access",
        "findings": findings,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "recommendations": recommendations,
    }
