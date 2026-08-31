"""
Phase 3 + 7D: Data Migration

Imports existing ReliefOS data into the generalized repository layer.

Migration sources:
1. data/sivasagar_flood.geojson → FloodSnapshot (Sivasagar)
2. data/raw/floods/jorhat_flood_2026-07-29_2026-07-30.geojson → FloodSnapshot (Jorhat)
3. data/raw/floods/charaideo_flood_2026-07-29_2026-07-30.geojson → FloodSnapshot (Charaideo)
4. data/raw/floods/golaghat_flood_2026-07-22_2026-07-23.geojson → FloodSnapshot (Golaghat)
5. data/community_reports.json → FieldReport
6. data/overrides.json → Override
7. data/cache/*.json → preserved as-is (cache-first behavior maintained)

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


# -----------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FLOOD_GEOJSON_PATH = os.path.join(_BASE_DIR, "data", "sivasagar_flood.geojson")
_COMMUNITY_REPORTS_PATH = os.path.join(_BASE_DIR, "data", "community_reports.json")
_OVERRIDES_PATH = os.path.join(_BASE_DIR, "data", "overrides.json")

# Real flood GeoJSON files for the 3 other districts
_RAW_FLOODS_DIR = os.path.join(_BASE_DIR, "data", "raw", "floods")


# -----------------------------------------------------------------------
# District definitions (all 4 real districts)
# -----------------------------------------------------------------------

# Each district needs: id, name, state, country, and its flood source file.
# The observation dates come from the actual Sentinel-1 data timestamps.
DISTRICT_FLOOD_SOURCES = {
    "sivasagar": {
        "file": _FLOOD_GEOJSON_PATH,
        "observed_at": "2026-07-01T00:00:00+00:00",
        "source": "Sentinel-1 SAR (Earth Engine export)",
    },
    "jorhat": {
        "file": os.path.join(_RAW_FLOODS_DIR, "jorhat_flood_2026-07-29_2026-07-30.geojson"),
        "observed_at": "2026-07-29T00:00:00+00:00",
        "source": "Sentinel-1 SAR (Earth Engine export)",
    },
    "charaideo": {
        "file": os.path.join(_RAW_FLOODS_DIR, "charaideo_flood_2026-07-29_2026-07-30.geojson"),
        "observed_at": "2026-07-29T00:00:00+00:00",
        "source": "Sentinel-1 SAR (Earth Engine export)",
    },
    "golaghat": {
        "file": os.path.join(_RAW_FLOODS_DIR, "golaghat_flood_2026-07-22_2026-07-23.geojson"),
        "observed_at": "2026-07-22T00:00:00+00:00",
        "source": "Sentinel-1 SAR (Earth Engine export)",
    },
}

# All four districts are in Assam, India
ALL_DISTRICTS = {
    "sivasagar": District(id="sivasagar", name="Sivasagar", state="Assam", country="India"),
    "jorhat": District(id="jorhat", name="Jorhat", state="Assam", country="India"),
    "charaideo": District(id="charaideo", name="Charaideo", state="Assam", country="India"),
    "golaghat": District(id="golaghat", name="Golaghat", state="Assam", country="India"),
}

# Settlements for Sivasagar (existing seed data, preserved)
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


# -----------------------------------------------------------------------
# Migration functions
# -----------------------------------------------------------------------

def ensure_districts(repo: DataRepository) -> list[District]:
    """Ensure all 4 districts exist in the database. Idempotent."""
    created = []
    for district in ALL_DISTRICTS.values():
        existing = repo.get_district(district.id)
        if existing is None:
            repo.upsert_district(district)
            created.append(district)
            print(f"  [MIGRATION] Created district: {district.id}")
    return created


def migrate_flood_data(repo: DataRepository = None) -> dict[str, Optional[FloodSnapshot]]:
    """
    Import all 4 real flood snapshots into the generalized repository.

    Uses the existing import_flood_geojson() which is idempotent via
    deterministic snapshot IDs and ON CONFLICT DO UPDATE.

    Returns dict mapping district_id → FloodSnapshot (or None if file missing).
    """
    if repo is None:
        repo = get_repository()

    # Ensure districts exist first
    ensure_districts(repo)

    # Ensure Sivasagar settlements exist (backward compat)
    for s in SIVASAGAR_SETTLEMENTS:
        if repo.get_settlement(s.id) is None:
            repo.upsert_settlement(s)

    results = {}

    for district_id, flood_info in DISTRICT_FLOOD_SOURCES.items():
        geojson_path = flood_info["file"]
        observed_at = flood_info["observed_at"]
        source = flood_info["source"]

        if not os.path.exists(geojson_path):
            print(f"  [MIGRATION] Flood GeoJSON not found for {district_id}: {geojson_path}")
            results[district_id] = None
            continue

        try:
            with open(geojson_path, "r") as f:
                geojson = json.load(f)
        except Exception as e:
            print(f"  [MIGRATION] Error loading flood GeoJSON for {district_id}: {e}")
            results[district_id] = None
            continue

        features = geojson.get("features", [])
        if not features:
            print(f"  [MIGRATION] Empty flood GeoJSON for {district_id}")
            results[district_id] = None
            continue

        # Check idempotency — skip if already imported
        snapshot_id = make_flood_snapshot_id(district_id, datetime.fromisoformat(observed_at))
        existing = repo.get_flood_snapshot(snapshot_id)
        if existing:
            print(f"  [MIGRATION] Flood snapshot already exists: {snapshot_id} ({existing.polygon_count} polygons)")
            results[district_id] = existing
            continue

        # Import using the existing idempotent method
        snapshot = repo.import_flood_geojson(
            geojson=geojson,
            district_id=district_id,
            source=source,
            observed_at=observed_at,
        )
        print(f"  [MIGRATION] Imported flood snapshot: {snapshot.id} ({snapshot.polygon_count} polygons) for {district_id}")
        results[district_id] = snapshot

    return results


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

    print("\n[PHASE 3+7D MIGRATION] Starting data migration...")

    # 1. Ensure districts exist
    ensure_districts(repo)

    # 2. Import all 4 flood snapshots
    flood_results = migrate_flood_data(repo)

    # 3. Import community reports
    reports = migrate_community_reports(repo)

    # 4. Import overrides
    overrides = migrate_overrides(repo)

    # Build summary
    flood_summary = {}
    for district_id, snapshot in flood_results.items():
        if snapshot:
            flood_summary[district_id] = {
                "id": snapshot.id,
                "polygon_count": snapshot.polygon_count,
                "observed_at": snapshot.observed_at.isoformat(),
                "source": snapshot.source,
            }

    summary = {
        "districts": [d.to_dict() for d in repo.list_districts()],
        "flood_snapshots": flood_summary,
        "settlements": [s.to_dict() for s in repo.list_settlements()],
        "community_reports_imported": len(reports),
        "overrides_imported": len(overrides),
    }

    print("[PHASE 3+7D MIGRATION] Complete.")
    return summary
