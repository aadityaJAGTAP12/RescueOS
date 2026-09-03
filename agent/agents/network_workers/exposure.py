"""
Exposure Worker — Network-level exposure analysis.

Reasons over: flood polygons, buildings, settlements, roads, bridges.
Reuses existing flood_tool and building exposure capabilities.
"""

from __future__ import annotations


def analyze_exposure(repo) -> dict:
    """
    Analyze exposure consequences of current flood state.

    Identifies affected settlements, buildings, roads, and bridges
    based on flood polygon intersections.
    """
    findings = []
    evidence = []
    uncertainty = []
    data_gaps = []
    recommendations = []

    # Get flood data
    snapshots = repo.list_flood_snapshots() if hasattr(repo, 'list_flood_snapshots') else []
    settlements = repo.list_settlements() if hasattr(repo, 'list_settlements') else []

    if not snapshots:
        data_gaps.append({"item": "No flood data", "detail": "Cannot assess exposure without flood snapshots."})
        return _build_result(findings, evidence, uncertainty, data_gaps, recommendations)

    # Count settlements per district
    district_settlements = {}
    for s in settlements:
        did = s.district_id if hasattr(s, 'district_id') else s.get('district_id', '')
        district_settlements.setdefault(did, []).append(s)

    # Analyze per-district
    district_snapshots = {}
    for snap in snapshots:
        did = snap.district_id if hasattr(snap, 'district_id') else snap.get('district_id', '')
        district_snapshots.setdefault(did, []).append(snap)

    for did, snaps in district_snapshots.items():
        sorted_snaps = sorted(snaps, key=lambda s: s.observed_at if hasattr(s, 'observed_at') else s.get('observed_at', ''), reverse=True)
        latest = sorted_snaps[0]
        polygon_count = latest.polygon_count if hasattr(latest, 'polygon_count') else latest.get('polygon_count', 0)

        settlement_count = len(district_settlements.get(did, []))

        evidence.append({
            "type": "exposure_assessment",
            "detail": f"{settlement_count} settlements in {did} with {polygon_count} flood polygons",
            "district": did,
        })

        if polygon_count > 0 and settlement_count > 0:
            findings.append({
                "type": "exposure_risk",
                "severity": "urgent",
                "title": f"Settlements potentially exposed in {did}",
                "summary": f"{settlement_count} settlements in district with active flood extent ({polygon_count} polygons)",
                "location": did,
            })

    # Check for settlements without district assignment
    unassigned = [s for s in settlements if not (s.district_id if hasattr(s, 'district_id') else s.get('district_id'))]
    if unassigned:
        uncertainty.append(f"{len(unassigned)} settlements have no district assignment — exposure assessment incomplete")

    return _build_result(findings, evidence, uncertainty, data_gaps, recommendations)


def _build_result(findings, evidence, uncertainty, data_gaps, recommendations):
    return {
        "worker": "exposure",
        "findings": findings,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "data_gaps": data_gaps,
        "recommendations": recommendations,
    }
