"""
Phase 3: Data Migration

Imports existing ReliefOS data into the generalized repository layer.

Migration sources:
1. data/sivasagar_flood.geojson → FloodSnapshot + District + Settlements
2. data/community_reports.json → FieldReport
3. data/overrides.json → Override
4. data/cache/*.json → preserved as-is (cache-first behavior maintained)

This module is idempotent — running it twice doesn't create duplicates.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

from agent.data.models import (
    District,
    Settlement,
    FloodSnapshot,
    FieldReport,
    Override,
    Provenance,
    VerificationState,
    make_flood_snapshot_id,
    make_settlement_id,
)
from agent.data.repository import DataRepository, get_repository


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FLOOD_GEOJSON_PATH = os.path.join(_BASE_DIR, "data", "sivasagar_flood.geojson")
_COMMUNITY_REPORTS_PATH = os.path.join(_BASE_DIR, "data", "community_reports.json")
_OVERRIDES_PATH = os.path.join(_BASE_DIR, "data", "overrides.json")


# ---------------------------------------------------------------------------
# Sivasagar seed data (synthetic district + known locations)
# ---------------------------------------------------------------------------

SIVASAGAR_DISTRICT = District(
    id="sivasagar",
    name="Sivasagar",
    state="Assam",
    country="India",
)

SIVASAGAR_SETTLEMENTS = [
    Settlement(
        id="sivasagar",
        name="Sivasagar",
        district_id="sivasagar",
        lat=26.9701,
        lon=94.6393,
        aliases=["sivasagar town", "sivasagar district headquarters"],
    ),
    Settlement(
        id="sivasagar_flood_zone",
        name="Sivasagar Flood Zone",
        district_id="sivasagar",
        lat=26.9894,
        lon=94.6698,
        aliases=["flood zone", "sivasagar flood area"],
    ),
    Settlement(
        id="sivasagar_settlement_flood",
        name="Sivasagar Settlement Flood",
        district_id="sivasagar",
        lat=27.0249,
        lon=94.6285,
        aliases=["settlement flood area"],
    ),
]


# ---------------------------------------------------------------------------
# Migration functions
# ---------------------------------------------------------------------------

def migrate_flood_data(repo: DataRepository = None) -> Optional[FloodSnapshot]:
    """
    Import data/sivasagar_flood.geojson into the generalized repository.

    Returns the created FloodSnapshot, or None if file not found.
    """
    if repo is None:
        repo = get_repository()

    # Ensure district exists
    if repo.get_district("sivasagar") is None:
        repo.upsert_district(SIVASAGAR_DISTRICT)

    # Ensure settlements exist
    for s in SIVASAGAR_SETTLEMENTS:
        if repo.get_settlement(s.id) is None:
            repo.upsert_settlement(s)

    # Load and import flood GeoJSON
    if not os.path.exists(_FLOOD_GEOJSON_PATH):
        print(f"  [MIGRATION] Flood GeoJSON not found: {_FLOOD_GEOJSON_PATH}")
        return None

    try:
        with open(_FLOOD_GEOJSON_PATH, "r") as f:
            geojson = json.load(f)
    except Exception as e:
        print(f"  [MIGRATION] Error loading flood GeoJSON: {e}")
        return None

    # Check if already imported (idempotent)
    snapshot_id = make_flood_snapshot_id("sivasagar", datetime(2026, 7, 1, tzinfo=timezone.utc))
    existing = repo.get_flood_snapshot(snapshot_id)
    if existing:
        print(f"  [MIGRATION] Flood snapshot already exists: {snapshot_id}")
        return existing

    # Import
    snapshot = repo.import_flood_geojson(
        geojson=geojson,
        district_id="sivasagar",
        source="Sentinel-1 SAR (Earth Engine export)",
        observed_at="2026-07-01T00:00:00+00:00",
    )
    print(f"  [MIGRATION] Imported flood snapshot: {snapshot.id} ({snapshot.polygon_count} polygons)")
    return snapshot


def migrate_community_reports(repo: DataRepository = None) -> list[FieldReport]:
    """
    Import data/community_reports.json into the generalized repository.

    Returns list of created FieldReports.
    """
    if repo is None:
        repo = get_repository()

    if not os.path.exists(_COMMUNITY_REPORTS_PATH):
        print(f"  [MIGRATION] Community reports file not found: {_COMMUNITY_REPORTS_PATH}")
        return []

    try:
        with open(_COMMUNITY_REPORTS_PATH, "r") as f:
            raw_reports = json.load(f)
    except Exception as e:
        print(f"  [MIGRATION] Error loading community reports: {e}")
        return []

    imported = []
    for raw in raw_reports:
        report_id = raw.get("id", "")
        # Skip if already imported
        existing = repo.get_field_report(report_id)
        if existing:
            continue

        # Parse timestamp
        ts_str = raw.get("timestamp", "")
        try:
            observed_at = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            observed_at = datetime.now(timezone.utc)

        # Map source type
        source_type = raw.get("source", "community_report")
        provenance = Provenance.REAL
        if source_type == "field_intelligence_text":
            provenance = Provenance.REAL  # still real, just different source

        report = FieldReport(
            id=report_id,
            district_id="sivasagar",  # all existing reports are from Sivasagar
            lat=raw.get("lat"),
            lon=raw.get("lon"),
            source_type=source_type,
            raw_text=raw.get("raw_text", raw.get("note", "")),
            people_count=raw.get("people_count", 0),
            adults=raw.get("adults", 0),
            children=raw.get("children", 0),
            elderly=raw.get("elderly", 0),
            needs=raw.get("needs", []),
            location_description=raw.get("location_description"),
            verification_state=VerificationState.VERIFIED if raw.get("verified") else VerificationState.UNVERIFIED,
            extraction_confidence=raw.get("extraction_confidence", "low"),
            observed_at=observed_at,
            ingested_at=observed_at,
            provenance=provenance,
            metadata={
                "location_resolved": raw.get("location_resolved", False),
                "road_status_mentions": raw.get("road_status_mentions", []),
                "facility_status_mentions": raw.get("facility_status_mentions", []),
            },
        )
        repo.upsert_field_report(report)
        imported.append(report)

    print(f"  [MIGRATION] Imported {len(imported)} community reports ({len(raw_reports)} total, {len(raw_reports) - len(imported)} already existed)")
    return imported


def migrate_overrides(repo: DataRepository = None) -> list[Override]:
    """
    Import data/overrides.json into the generalized repository.

    Returns list of created Overrides.
    """
    if repo is None:
        repo = get_repository()

    if not os.path.exists(_OVERRIDES_PATH):
        print(f"  [MIGRATION] Overrides file not found: {_OVERRIDES_PATH}")
        return []

    try:
        with open(_OVERRIDES_PATH, "r") as f:
            raw_overrides = json.load(f)
    except Exception as e:
        print(f"  [MIGRATION] Error loading overrides: {e}")
        return []

    imported = []
    for raw in raw_overrides:
        override_id = raw.get("id", "")
        existing = repo.get_active_override(raw.get("target_type", ""), raw.get("target_id", ""))
        if existing and existing.id == override_id:
            continue

        try:
            created_at = datetime.fromisoformat(raw.get("timestamp", "").replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_at = datetime.now(timezone.utc)

        override = Override(
            id=override_id,
            target_type=raw.get("target_type", ""),
            target_id=raw.get("target_id", ""),
            override_status=raw.get("override_status", ""),
            reason=raw.get("reason", ""),
            actor=raw.get("actor", "coordinator"),
            system_status=raw.get("system_status", "unknown"),
            active=raw.get("active", True),
            created_at=created_at,
        )
        repo.upsert_override(override)
        imported.append(override)

    print(f"  [MIGRATION] Imported {len(imported)} overrides ({len(raw_overrides)} total)")
    return imported


def run_full_migration(repo: DataRepository = None) -> dict:
    """
    Run all migrations. Idempotent — safe to call multiple times.

    Returns summary of what was imported.
    """
    if repo is None:
        repo = get_repository()

    print("\n[PHASE 3 MIGRATION] Starting data migration...")

    flood = migrate_flood_data(repo)
    reports = migrate_community_reports(repo)
    overrides = migrate_overrides(repo)

    summary = {
        "flood_snapshot": flood.to_dict() if flood else None,
        "community_reports_imported": len(reports),
        "overrides_imported": len(overrides),
        "districts": [d.to_dict() for d in repo.list_districts()],
        "settlements": [s.to_dict() for s in repo.list_settlements()],
    }

    print("[PHASE 3 MIGRATION] Complete.")
    return summary
