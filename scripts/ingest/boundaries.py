"""
ReliefOS Ingestion — District Boundaries

Acquires administrative boundaries for four Assam districts:
- Sivasagar
- Jorhat
- Charaideo
- Golaghat

Uses Nominatim API (OSM) with proper rate limiting and attribution.
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone

from scripts.ingest.base import (
    get_repo, setup_logging, SOURCES, SourceMetadata,
    IngestStats, geojson_to_wkt, rate_limit,
)
from agent.data.models import District, Provenance

logger = setup_logging("boundaries")

# ---------------------------------------------------------------------------
# District definitions
# ---------------------------------------------------------------------------

DISTRICTS = [
    {
        "id": "sivasagar",
        "name": "Sivasagar",
        "state": "Assam",
        "country": "India",
        "nominatim_query": "Sivasagar district, Assam, India",
    },
    {
        "id": "jorhat",
        "name": "Jorhat",
        "state": "Assam",
        "country": "India",
        "nominatim_query": "Jorhat district, Assam, India",
    },
    {
        "id": "charaideo",
        "name": "Charaideo",
        "state": "Assam",
        "country": "India",
        "nominatim_query": "Charaideo district, Assam, India",
    },
    {
        "id": "golaghat",
        "name": "Golaghat",
        "state": "Assam",
        "country": "India",
        "nominatim_query": "Golaghat district, Assam, India",
    },
]

# ---------------------------------------------------------------------------
# Nominatim API
# ---------------------------------------------------------------------------

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "ReliefOS/1.0 (research)"}


def fetch_district_boundary(nominatim_query: str) -> dict | None:
    """
    Fetch district boundary polygon from Nominatim.
    
    Returns GeoJSON geometry dict or None if not found.
    """
    params = {
        "q": nominatim_query,
        "format": "geojson",
        "polygon_geojson": 1,
        "limit": 1,
    }
    
    try:
        resp = requests.get(NOMINATIM_URL, params=params, 
                          headers=NOMINATIM_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if not data.get("features"):
            logger.warning(f"  No results for: {nominatim_query}")
            return None
        
        feature = data["features"][0]
        return feature.get("geometry")
    
    except Exception as e:
        logger.error(f"  Nominatim API error: {e}")
        return None


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_boundaries(repo=None):
    """Ingest district boundaries for all four districts."""
    if repo is None:
        repo = get_repo()
    
    stats = IngestStats()
    source = SOURCES["osm_nominatim"]
    
    logger.info("=" * 60)
    logger.info("INGESTING DISTRICT BOUNDARIES")
    logger.info("=" * 60)
    
    for district_def in DISTRICTS:
        district_id = district_def["id"]
        logger.info(f"\n[{district_id.upper()}] Fetching boundary...")
        
        # Check if district already has geometry
        existing = repo.get_district(district_id)
        if existing and existing.geometry_wkt:
            logger.info(f"  [{district_id}] Already has geometry, skipping")
            stats.record(district_id, "nominatim", "boundary", 0)
            continue
        
        # Fetch from Nominatim
        geometry = fetch_district_boundary(district_def["nominatim_query"])
        rate_limit(1.1)  # Nominatim rate limit: 1 req/sec
        
        if geometry is None:
            logger.warning(f"  [{district_id}] No boundary found, creating district without geometry")
            # Still create the district record
            district = District(
                id=district_id,
                name=district_def["name"],
                state=district_def["state"],
                country=district_def["country"],
                metadata={
                    "source": source.to_dict(),
                    "boundary_status": "unavailable",
                    "boundary_fetch_date": datetime.now(timezone.utc).isoformat(),
                },
            )
            repo.upsert_district(district)
            stats.record(district_id, "nominatim", "boundary", 0)
            continue
        
        # Convert to WKT
        geometry_wkt = geojson_to_wkt(geometry)
        
        # Create district with geometry
        district = District(
            id=district_id,
            name=district_def["name"],
            state=district_def["state"],
            country=district_def["country"],
            geometry_wkt=geometry_wkt,
            metadata={
                "source": source.to_dict(),
                "boundary_status": "available",
                "boundary_fetch_date": datetime.now(timezone.utc).isoformat(),
                "geometry_type": geometry.get("type"),
            },
        )
        repo.upsert_district(district)
        
        logger.info(f"  [{district_id}] ✓ Boundary ingested ({geometry.get('type')})")
        stats.record(district_id, "nominatim", "boundary", 1)
    
    logger.info("\n" + stats.summary())
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ingest_boundaries()
