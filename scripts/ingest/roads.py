"""
ReliefOS Ingestion — Roads

Acquires road network data from OpenStreetMap Overpass API for four Assam districts.
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone

from scripts.ingest.base import (
    get_repo, setup_logging, SOURCES, IngestStats, rate_limit,
)
from agent.data.models import Road, Provenance

logger = setup_logging("roads")

# ---------------------------------------------------------------------------
# District bounding boxes
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
OVERPASS_TIMEOUT = 60


def fetch_roads_overpass(bbox: tuple[float, float, float, float],
                         district_id: str) -> list[dict]:
    """Fetch road data from Overpass API for a bounding box."""
    south, west, north, east = bbox
    
    # Query for major roads
    query = f"""
    [out:json][timeout:{OVERPASS_TIMEOUT}];
    (
      way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential)$"]({south},{west},{north},{east});
    );
    out body;
    >;
    out skel qt;
    """
    
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=OVERPASS_TIMEOUT + 30)
        resp.raise_for_status()
        data = resp.json()
        
        # Build node lookup
        nodes = {}
        for element in data.get("elements", []):
            if element["type"] == "node":
                nodes[element["id"]] = (element["lon"], element["lat"])
        
        roads = []
        for element in data.get("elements", []):
            if element["type"] != "way":
                continue
            
            tags = element.get("tags", {})
            node_ids = element.get("nodes", [])
            
            # Build geometry from nodes
            coords = []
            for nid in node_ids:
                if nid in nodes:
                    coords.append(nodes[nid])
            
            if len(coords) < 2:
                continue
            
            roads.append({
                "osm_id": element["id"],
                "name": tags.get("name", ""),
                "highway_type": tags.get("highway", "unclassified"),
                "geometry_coords": coords,
                "bridge": tags.get("bridge") == "yes",
                "tags": {
                    "name": tags.get("name", ""),
                    "highway": tags.get("highway", ""),
                    "surface": tags.get("surface", ""),
                    "bridge": tags.get("bridge", ""),
                },
            })
        
        return roads
    
    except Exception as e:
        logger.error(f"  Overpass API error: {e}")
        return []


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_roads(repo=None, max_per_district: int = 2000):
    """Ingest roads for all four districts."""
    if repo is None:
        repo = get_repo()
    
    stats = IngestStats()
    source = SOURCES["osm_overpass"]
    
    logger.info("=" * 60)
    logger.info("INGESTING ROADS FROM OVERPASS")
    logger.info("=" * 60)
    
    for district_id, bbox in DISTRICT_BBOXES.items():
        logger.info(f"\n[{district_id.upper()}] Fetching roads...")
        
        # Check existing
        existing = repo.get_roads(district_id)
        if len(existing) > 0:
            logger.info(f"  [{district_id}] Already has {len(existing)} roads, skipping")
            stats.record(district_id, "overpass", "road", 0)
            continue
        
        # Fetch from Overpass
        raw_roads = fetch_roads_overpass(bbox, district_id)
        logger.info(f"  [{district_id}] Fetched {len(raw_roads)} roads from Overpass")
        
        # Limit
        if len(raw_roads) > max_per_district:
            raw_roads = raw_roads[:max_per_district]
        
        # Ingest
        ingested = 0
        for road_data in raw_roads:
            road = Road(
                id=f"osm_{district_id}_{road_data['osm_id']}",
                district_id=district_id,
                name=road_data["name"],
                highway_type=road_data["highway_type"],
                osm_id=road_data["osm_id"],
                geometry_coords=road_data["geometry_coords"],
                flood_affected=False,  # Not set permanently
                provenance=Provenance.REAL,
            )
            repo.upsert_roads([road])
            ingested += 1
        
        logger.info(f"  [{district_id}] ✓ {ingested} roads ingested")
        stats.record(district_id, "overpass", "road", ingested)
        
        rate_limit(2.0)
    
    logger.info("\n" + stats.summary())
    return stats


if __name__ == "__main__":
    ingest_roads()
