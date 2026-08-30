"""
ReliefOS Ingestion Pipeline — Main Orchestrator

Runs all ingestion steps in the correct order:
1. District boundaries
2. Settlements
3. Flood snapshots (preserves existing, documents gaps)
4. OSM PBF ingestion (buildings, roads, medical, infrastructure)
5. Post-ingestion validation

Phase 5B.1: Step 4 replaces old Overpass-based ingestion with real PBF data.

Usage:
    export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos
    python -m scripts.ingest.all
"""

import os
import sys
import time
from datetime import datetime, timezone

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.ingest.base import get_repo, setup_logging
from scripts.ingest.boundaries import ingest_boundaries
from scripts.ingest.settlements import ingest_settlements
from scripts.ingest.flood import ingest_flood
from scripts.ingest.osm_pbf import run_osm_pbf_ingestion
from scripts.ingest.validate import run_validation

logger = setup_logging("ingest_all")


def run_all_ingestion():
    """Run all ingestion steps in order."""
    start_time = time.time()
    
    logger.info("=" * 70)
    logger.info("RELIEFOS PHASE 5B.1 — MULTI-DISTRICT INGESTION (OSM PBF)")
    logger.info("=" * 70)
    logger.info(f"Started at: {datetime.now(timezone.utc).isoformat()}")
    logger.info("")
    
    # Get repository
    repo = get_repo()
    
    # 1. District boundaries
    logger.info("\n" + "=" * 70)
    logger.info("STEP 1: DISTRICT BOUNDARIES")
    logger.info("=" * 70)
    ingest_boundaries(repo)
    
    # 2. Settlements
    logger.info("\n" + "=" * 70)
    logger.info("STEP 2: SETTLEMENTS")
    logger.info("=" * 70)
    ingest_settlements(repo)
    
    # 3. Flood snapshots
    logger.info("\n" + "=" * 70)
    logger.info("STEP 3: FLOOD SNAPSHOTS")
    logger.info("=" * 70)
    ingest_flood(repo)
    
    # 4. OSM PBF ingestion (buildings, roads, medical, infrastructure)
    logger.info("\n" + "=" * 70)
    logger.info("STEP 4: OSM PBF INGESTION")
    logger.info("=" * 70)
    run_osm_pbf_ingestion()
    
    # 5. Validation
    logger.info("\n" + "=" * 70)
    logger.info("STEP 5: POST-INGESTION VALIDATION")
    logger.info("=" * 70)
    run_validation()
    
    # Summary
    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 70)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Total time: {elapsed:.1f} seconds")
    logger.info(f"Completed at: {datetime.now(timezone.utc).isoformat()}")
    
    # Database summary
    from sqlalchemy import text
    with repo._engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                (SELECT count(*) FROM districts WHERE id IN ('sivasagar','jorhat','charaideo','golaghat')) as districts,
                (SELECT count(*) FROM settlements WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as settlements,
                (SELECT count(*) FROM buildings WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as buildings,
                (SELECT count(*) FROM roads WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as roads,
                (SELECT count(*) FROM medical_facilities WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as medical,
                (SELECT count(*) FROM flood_snapshots WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as flood_snapshots,
                (SELECT count(*) FROM field_reports WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as field_reports,
                (SELECT count(*) FROM overrides) as overrides
        """))
        row = result.fetchone()
        
        logger.info("\nDatabase Row Counts (4 districts):")
        logger.info(f"  Districts:         {row[0]}")
        logger.info(f"  Settlements:       {row[1]}")
        logger.info(f"  Buildings:         {row[2]}")
        logger.info(f"  Roads:             {row[3]}")
        logger.info(f"  Medical facilities:{row[4]}")
        logger.info(f"  Flood snapshots:   {row[5]}")
        logger.info(f"  Field reports:     {row[6]}")
        logger.info(f"  Overrides:         {row[7]}")


if __name__ == "__main__":
    run_all_ingestion()
