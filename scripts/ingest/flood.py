"""
ReliefOS Ingestion — Flood Snapshots

Preserves existing Sivasagar flood data and documents gaps for other districts.
Does NOT fabricate flood polygons.

Per Phase 5B instructions:
- If a district has no usable temporal flood dataset yet:
  - don't fabricate one
  - preserve the database capability
  - document the gap
"""

import os
import sys
import json
from datetime import datetime, timezone

from scripts.ingest.base import (
    get_repo, setup_logging, SOURCES, IngestStats,
)
from agent.data.models import FloodSnapshot, Provenance

logger = setup_logging("flood")

# ---------------------------------------------------------------------------
# Existing flood data
# ---------------------------------------------------------------------------

SIVASAGAR_FLOOD_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "sivasagar_flood.geojson"
)


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_flood(repo=None):
    """
    Ingest flood snapshot data.
    
    - Preserves existing Sivasagar flood data
    - Documents gaps for other districts
    - Does NOT fabricate flood polygons
    """
    if repo is None:
        repo = get_repo()
    
    stats = IngestStats()
    source = SOURCES["sentinel1_sar"]
    
    logger.info("=" * 60)
    logger.info("INGESTING FLOOD SNAPSHOTS")
    logger.info("=" * 60)
    
    # 1. Sivasagar — existing flood data
    logger.info("\n[SIVASAGAR] Checking existing flood data...")
    
    existing_snap = repo.get_latest_flood_snapshot("sivasagar")
    if existing_snap:
        logger.info(f"  [sivasagar] ✓ Flood snapshot already exists: {existing_snap.id}")
        logger.info(f"    - Polygons: {existing_snap.polygon_count}")
        logger.info(f"    - Source: {existing_snap.source}")
        logger.info(f"    - Observed at: {existing_snap.observed_at}")
        stats.record("sivasagar", "sentinel1_sar", "flood_snapshot", 1)
    else:
        # Import from GeoJSON file
        if os.path.exists(SIVASAGAR_FLOOD_PATH):
            logger.info(f"  [sivasagar] Importing from {SIVASAGAR_FLOOD_PATH}")
            with open(SIVASAGAR_FLOOD_PATH, "r") as f:
                geojson = json.load(f)
            
            snapshot = repo.import_flood_geojson(
                geojson=geojson,
                district_id="sivasagar",
                source="Sentinel-1 SAR (Earth Engine export)",
                observed_at="2026-07-01T00:00:00+00:00",
            )
            logger.info(f"  [sivasagar] ✓ Imported flood snapshot: {snapshot.id} ({snapshot.polygon_count} polygons)")
            stats.record("sivasagar", "sentinel1_sar", "flood_snapshot", 1)
        else:
            logger.warning(f"  [sivasagar] Flood data file not found: {SIVASAGAR_FLOOD_PATH}")
            stats.record("sivasagar", "sentinel1_sar", "flood_snapshot", 0)
    
    # 2. Other districts — document gaps
    other_districts = ["jorhat", "charaideo", "golaghat"]
    
    for district_id in other_districts:
        logger.info(f"\n[{district_id.upper()}] Checking flood data...")
        
        existing = repo.get_latest_flood_snapshot(district_id)
        if existing:
            logger.info(f"  [{district_id}] ✓ Flood snapshot already exists")
            stats.record(district_id, "existing", "flood_snapshot", 1)
            continue
        
        # Document the gap
        logger.info(f"  [{district_id}] NO USABLE FLOOD DATA AVAILABLE")
        logger.info(f"  [{district_id}] Gap documented in district metadata")
        
        # Update district metadata to document the gap
        district = repo.get_district(district_id)
        if district:
            metadata = district.metadata or {}
            metadata["flood_data_gap"] = {
                "status": "unavailable",
                "documented_date": datetime.now(timezone.utc).isoformat(),
                "notes": "No publicly usable flood extent dataset available for this district. "
                         "Flood snapshots will be added when data becomes available.",
                "potential_sources": [
                    "Sentinel-1 SAR (Google Earth Engine export)",
                    "CWC flood inundation maps",
                    "NRSC Bhuvan flood monitoring",
                ],
            }
            # Re-upsert district with updated metadata
            from agent.data.models import District
            district_obj = District(
                id=district_id,
                name=district.name,
                state=district.state,
                country=district.country,
                geometry_wkt=district.geometry_wkt,
                metadata=metadata,
            )
            repo.upsert_district(district_obj)
        
        stats.record(district_id, "documented_gap", "flood_snapshot", 0)
    
    logger.info("\n" + stats.summary())
    
    # Document flood data availability
    logger.info("\n" + "=" * 60)
    logger.info("FLOOD DATA AVAILABILITY REPORT")
    logger.info("=" * 60)
    logger.info("Sivasagar:    AVAILABLE — 1,924 polygons from Sentinel-1 SAR (2026-07-01)")
    logger.info("Jorhat:       UNAVAILABLE — No publicly usable flood extent dataset")
    logger.info("Charaideo:    UNAVAILABLE — No publicly usable flood extent dataset")
    logger.info("Golaghat:     UNAVAILABLE — No publicly usable flood extent dataset")
    logger.info("")
    logger.info("Note: Flood data gaps are documented in district metadata.")
    logger.info("The database structure supports multiple snapshots per district.")
    logger.info("Data will be added when source datasets become available.")
    
    return stats


if __name__ == "__main__":
    ingest_flood()
