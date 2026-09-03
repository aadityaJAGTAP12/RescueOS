"""
Medical Worker — Network-level medical situation analysis.

Reasons over: medical facilities, flood exposure, field reports.
Uses cautious language — never claims outbreaks without evidence.
"""

from __future__ import annotations


def analyze_medical(repo) -> dict:
    """
    Analyze medical pressure based on available evidence.

    Returns cautious findings about potential health risks.
    """
    findings = []
    evidence = []
    uncertainty = []
    data_gaps = []
    recommendations = []

    # Check for medical facilities
    try:
        facilities = repo.list_medical_facilities() if hasattr(repo, 'list_medical_facilities') else []
    except Exception:
        facilities = []

    if not facilities:
        data_gaps.append({
            "item": "No medical facility data",
            "detail": "Medical facility inventory not available for analysis.",
        })

    # Check field reports for medical needs
    try:
        from agent.community_reports import get_all_reports
        all_reports = get_all_reports()
        medical_reports = [r for r in all_reports if 'medical' in (r.get('needs', []))]
    except Exception:
        medical_reports = []

    if medical_reports:
        evidence.append({
            "type": "field_reports",
            "detail": f"{len(medical_reports)} field reports mention medical needs",
            "count": len(medical_reports),
        })
        findings.append({
            "type": "medical_concern",
            "severity": "urgent" if len(medical_reports) >= 3 else "information",
            "title": f"{len(medical_reports)} field report(s) indicate medical needs",
            "summary": "Community reports mention medical requirements — verification recommended",
            "evidence_refs": ["field_reports:medical"],
        })

    # Check flood exposure for health risk indicators
    snapshots = repo.list_flood_snapshots() if hasattr(repo, 'list_flood_snapshots') else []
    if snapshots:
        evidence.append({
            "type": "flood_context",
            "detail": f"{len(snapshots)} flood snapshots available — standing water may increase health risks",
        })
        uncertainty.append("Flood-related health risks are potential, not confirmed — no disease outbreak data available")

    return _build_result(findings, evidence, uncertainty, data_gaps, recommendations)


def _build_result(findings, evidence, uncertainty, data_gaps, recommendations):
    return {
        "worker": "medical",
        "findings": findings,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "recommendations": recommendations,
    }
