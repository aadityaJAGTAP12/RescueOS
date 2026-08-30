"""
ReliefOS Ingestion — Buildings

Acquires building data from OpenStreetMap Overpass API for four Assam districts.
Uses bulk queries per district bounding box to minimize API calls.
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone
from shapely.geometry import shape, Point

from scripts.ingest.base import (
    get_repo, setup_logging, SOURCES, IngestStats, rate_limit,
)
from agent.data.models import Building, Provenance

logger = setup_logging("buildings")

# ---------------------------------------------------------------------------
# District bounding boxes (approximate, for Overpass queries)
# ---------------------------------------------------------------------------

DISTRICT_BBOXES = {
    "sivasagar": (26.7, 94.4, 27.1, 94.9),
    "jorhat": (26.5, 93.8, 27.0, 94.4),
    "charaideo": (26.9, 94.7, 27.3, 95.1),
    "golaghat": (26.3, 93.1, 26.9, 94.1),
}

# ---------------------------------------------------------------------------
# Overpass API
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 60  # seconds


def fetch_buildings_overpass(bbox: tuple[float, float, float, float],
                             district_id: str) -> list[dict]:
    """
    Fetch building data from Overpass API for a bounding box.
    
    Returns list of building dicts with OSM data.
    """
    south, west, north, east = bbox
    
    # Overpass QL query for buildings
    query = f"""
    [out:json][timeout:{OVERPASS_TIMEOUT}];
    (
      way["building"]({south},{west},{north},{east});
      relation["building"]({south},{west},{north},{east});
    );
    out center;
    """
    
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=OVERPASS_TIMEOUT + 30)
        resp.raise_for_status()
        data = resp.json()
        
        buildings = []
        for element in data.get("elements", []):
            # Get centroid from center (for ways) or from lat/lon (for nodes)
            lat = element.get("lat") or element.get("center", {}).get("lat")
            lon = element.get("lon") or element.get("center", {}).get("lon")
            
            if not lat or not lon:
                continue
            
            tags = element.get("tags", {})
            osm_id = element.get("id")
            
            buildings.append({
                "osm_id": osm_id,
                "lat": lat,
                "lon": lon,
                "tags": {
                    "building": tags.get("building", "yes"),
                    "name": tags.get("name", ""),
                    "amenity": tags.get("amenity", ""),
                    "height": tags.get("height", ""),
                    "levels": tags.get("building:levels", ""),
                },
            })
        
        return buildings
    
    except Exception as e:
        logger.error(f"  Overpass API error: {e}")
        return []


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_buildings(repo=None, max_per_district: int = 5000):
    """
    Ingest buildings for all four districts.
    
    Args:
        repo: PostgresRepository instance
        max_per_district: Maximum buildings to ingest per district (to avoid memory issues)
    """
    if repo is None:
        repo = get_repo()
    
    stats = IngestStats()
    source = SOURCES["osm_overpass"]
    
    logger.info("=" * 60)
    logger.info("INGESTING BUILDINGS FROM OVERPASS")
    logger.info("=" * 60)
    
    for district_id, bbox in DISTRICT_BBOXES.items():
        logger.info(f"\n[{district_id.upper()}] Fetching buildings...")
        
        # Check existing count
        existing = repo.get_buildings(district_id)
        if len(existing) > 0:
            logger.info(f"  [{district_id}] Already has {len(existing)} buildings, skipping")
            stats.record(district_id, "overpass", "building", 0)
            continue
        
        # Fetch from Overpass
        raw_buildings = fetch_buildings_overpass(bbox, district_id)
        logger.info(f"  [{district_id}] Fetched {len(raw_buildings)} buildings from Overpass")
        
        # Limit to max_per_district
        if len(raw_buildings) > max_per_district:
            raw_buildings = raw_buildings[:max_per_district]
            logger.info(f"  [{district_id}] Limited to {max_per_district} buildings")
        
        # Ingest in batches
        batch_size = 100
        ingested = 0
        for i in range(0, len(raw_buildings), batch_size):
            batch = raw_buildings[i:i+batch_size]
            buildings = []
            for b in batch:
                building = Building(
                    id=f"osm_{district_id}_{b['osm_id']}",
                    district_id=district_id,
                    osm_id=b["osm_id"],
                    lat=b["lat"],
                    lon=b["lon"],
                    tags=b["tags"],
                    in_flood_zone=False,  # Not set permanently
                    provenance=Provenance.REAL,
                )
                buildings.append(building)
            
            repo.upsert_buildings(buildings)
            ingested += len(buildings)
        
        logger.info(f"  [{district_id}] ✓ {ingested} buildings ingested")
        stats.record(district_id, "overpass", "building", ingested)
        
        # Rate limit between districts
        rate_limit(2.0)
    
    logger.info("\n" + stats.summary())
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ingest_buildings()
