"""
Field Intelligence Worker — Network-level field report analysis.

Reuses existing field reports, deduplication, and evidence synthesis.
"""

from __future__ import annotations


def analyze_field_intelligence(repo) -> dict:
    """
    Analyze field reports and intelligence for the network.
    Uses semantic deduplication from Phase 7D.
    """
    findings = []
    evidence = []
    uncertainty = []
    data_gaps = []
    recommendations = []

    # Get field reports
    try:
        from agent.community_reports import get_all_reports
        all_reports = get_all_reports()
    except Exception:
        all_reports = []

    if not all_reports:
        data_gaps.append({
            "item": "No field reports",
            "detail": "No community or field intelligence reports available.",
        })
        return _build_result(findings, evidence, uncertainty, data_gaps, recommendations)

    # Deduplicate reports
    try:
        from agent.delta import deduplicate_reports
        grouped = deduplicate_reports(all_reports)
    except Exception:
        grouped = []

    evidence.append({
        "type": "field_report_summary",
        "detail": f"{len(all_reports)} total reports, {len(grouped)} grouped events",
    })

    # Analyze grouped events
    for event in grouped:
        report_count = event.get("report_count", 0)
        verified = event.get("verified_count", 0)
        category = event.get("category", "general")

        if report_count >= 3:
            findings.append({
                "type": "clustered_reports",
                "severity": "urgent" if verified > 0 else "information",
                "title": f"Clustered reports: {category}",
                "summary": f"{report_count} reports ({verified} verified) describe similar event",
                "location": event.get("location_description", ""),
            })
        elif report_count >= 2:
            findings.append({
                "type": "grouped_reports",
                "severity": "information",
                "title": f"Grouped reports: {category}",
                "summary": f"{report_count} reports grouped as similar event",
                "location": event.get("location_description", ""),
            })

    # Unverified reports
    unverified = [r for r in all_reports if not r.get("verified", False)]
    if unverified:
        uncertainty.append(f"{len(unverified)} reports are unverified — field confirmation recommended")

    return _build_result(findings, evidence, uncertainty, data_gaps, recommendations)


def _build_result(findings, evidence, uncertainty, data_gaps, recommendations):
    return {
        "worker": "field",
        "findings": findings,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "recommendations": recommendations,
    }
