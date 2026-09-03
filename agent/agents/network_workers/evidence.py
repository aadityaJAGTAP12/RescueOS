"""
Evidence Worker — Network-level evidence synthesis.

Reuses Phase 7D evidence synthesis where possible.
Ensures every important recommendation has supporting evidence.
"""

from __future__ import annotations


def synthesize_network_evidence(repo) -> dict:
    """
    Synthesize evidence across the network for the Network Main Agent.
    """
    findings = []
    evidence = []
    uncertainty = []
    data_gaps = []

    # Flood evidence
    try:
        snapshots = repo.list_flood_snapshots() if hasattr(repo, 'list_flood_snapshots') else []
        if snapshots:
            evidence.append({
                "type": "flood_evidence",
                "detail": f"{len(snapshots)} flood snapshots available",
                "coverage": len(set(s.district_id if hasattr(s, 'district_id') else s.get('district_id', '') for s in snapshots)),
            })
        else:
            data_gaps.append({"item": "No flood evidence", "detail": "No flood snapshots in database."})
    except Exception:
        data_gaps.append({"item": "Flood evidence", "detail": "Unable to access flood snapshot data."})

    # Field report evidence
    try:
        from agent.community_reports import get_all_reports
        reports = get_all_reports()
        verified = [r for r in reports if r.get("verified", False)]
        evidence.append({
            "type": "field_report_evidence",
            "detail": f"{len(reports)} total reports, {len(verified)} verified",
        })
        if not verified:
            uncertainty.append("No verified field reports — all reports are unverified")
    except Exception:
        data_gaps.append({"item": "Field reports", "detail": "Unable to access field report data."})

    # Override evidence
    try:
        from agent.overrides import get_all_overrides
        overrides = get_all_overrides()
        active = [o for o in overrides if o.get("active", True)]
        evidence.append({
            "type": "override_evidence",
            "detail": f"{len(active)} active overrides (coordinator-reported status)",
        })
    except Exception:
        data_gaps.append({"item": "Override evidence", "detail": "Unable to access override data."})

    return {
        "worker": "evidence",
        "findings": findings,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "recommendations": [],
    }
