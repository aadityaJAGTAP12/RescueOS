"""
Community Reports: stores and queries self-reported community needs.

This is a DISTINCT, clearly-flagged data source (self-reported, not
satellite-derived). Reports are never silently blended with deterministic
exposure data.

MVP implementation: JSON file storage.
"""

import json
import os
import uuid
from datetime import datetime
from agent.config import CACHE_DIR
from agent.tools.flood_tool import get_flood_status


REPORTS_FILE = os.path.join(os.path.dirname(CACHE_DIR), "community_reports.json")

# Controlled set of valid needs categories
VALID_NEEDS = [
    "medical", "food", "water", "sanitary_supplies",
    "infant_care", "shelter", "transport", "other"
]


def _load_reports() -> list[dict]:
    """Load all stored reports from JSON file."""
    if not os.path.exists(REPORTS_FILE):
        return []
    try:
        with open(REPORTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_reports(reports: list[dict]) -> None:
    """Save all reports to JSON file."""
    os.makedirs(os.path.dirname(REPORTS_FILE), exist_ok=True)
    with open(REPORTS_FILE, "w") as f:
        json.dump(reports, f, indent=2)


def submit_report(
    lat: float,
    lon: float,
    people_count: int,
    adults: int = 0,
    children: int = 0,
    elderly: int = 0,
    needs: list[str] = None,
    note: str = "",
    contact: str = None
) -> dict:
    """
    Store a new community report.

    Validates that lat/lon roughly falls within or near a known flood-affected
    area before accepting. Rejects reports from non-flood areas to reduce
    spam/errors.

    Args:
        lat: latitude of the report location
        lon: longitude of the report location
        people_count: total number of people needing help
        adults: number of adults (optional)
        children: number of children (optional)
        elderly: number of elderly (optional)
        needs: list of need categories from VALID_NEEDS
        note: free-text description of situation
        contact: optional contact info

    Returns:
        {"success": bool, "report_id": str, "message": str}
    """
    # Validate location is near a flood zone using the canonical flood_tool
    flood_status = get_flood_status(lat=lat, lon=lon)
    if not flood_status.get("near_flood_zone") and not flood_status.get("exactly_contained"):
        return {
            "success": False,
            "report_id": None,
            "message": (
                f"Report rejected: location ({lat:.4f}, {lon:.4f}) does not appear to be "
                f"near any known flood-affected area. Reports are only accepted from "
                f"flood zones to reduce spam and errors."
            )
        }

    # Validate needs
    if needs is None:
        needs = []
    invalid_needs = [n for n in needs if n not in VALID_NEEDS]
    if invalid_needs:
        return {
            "success": False,
            "report_id": None,
            "message": f"Report rejected: invalid need categories: {invalid_needs}. Valid: {VALID_NEEDS}"
        }

    # Create report
    report_id = str(uuid.uuid4())[:8]
    report = {
        "id": report_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "lat": lat,
        "lon": lon,
        "people_count": people_count,
        "adults": adults,
        "children": children,
        "elderly": elderly,
        "needs": needs,
        "note": note,
        "contact": contact,
        "source": "community_report",
        "verified": False
    }

    # Save
    reports = _load_reports()
    reports.append(report)
    _save_reports(reports)

    return {
        "success": True,
        "report_id": report_id,
        "message": (
            f"Report accepted: {people_count} people at ({lat:.4f}, {lon:.4f}) "
            f"needing {', '.join(needs) if needs else 'no specific supplies listed'}. "
            f"NOTE: This is self-reported and unverified data."
        )
    }


def get_reports_near(lat: float, lon: float, radius_km: float = 3.0) -> list[dict]:
    """
    Returns all stored reports within radius_km of a point.

    Args:
        lat: center latitude
        lon: center longitude
        radius_km: search radius in km (default 3.0)

    Returns: list of report dicts within radius
    """
    from agent.data_loader import haversine_km

    reports = _load_reports()
    nearby = []

    for report in reports:
        dist = haversine_km(lon, lat, report["lon"], report["lat"])
        if dist <= radius_km:
            report_copy = dict(report)
            report_copy["distance_km"] = round(dist, 2)
            nearby.append(report_copy)

    # Sort by distance
    nearby.sort(key=lambda r: r["distance_km"])
    return nearby


def get_all_reports() -> list[dict]:
    """Returns all stored reports (for debugging/admin)."""
    return _load_reports()


def clear_reports() -> None:
    """Clear all stored reports (for testing)."""
    _save_reports([])
