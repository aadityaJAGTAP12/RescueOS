"""
ReliefOS Ingestion — Medical Facilities

Acquires hospitals, clinics, and other medical facilities from OpenStreetMap.
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
from agent.data.models import MedicalFacility, Provenance

logger = setup_logging("medical")

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


def fetch_medical_overpass(bbox: tuple[float, float, float, float],
                           district_id: str) -> list[dict]:
    """Fetch medical facilities from Overpass API."""
    south, west, north, east = bbox
    
    query = f"""
    [out:json][timeout:{OVERPASS_TIMEOUT}];
    (
      node["amenity"~"^(hospital|clinic|doctors|pharmacy)$"]({south},{west},{north},{east});
      way["amenity"~"^(hospital|clinic|doctors|pharmacy)$"]({south},{west},{north},{east});
    );
    out center;
    """
    
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=OVERPASS_TIMEOUT + 30)
        resp.raise_for_status()
        data = resp.json()
        
        facilities = []
        for element in data.get("elements", []):
            lat = element.get("lat") or element.get("center", {}).get("lat")
            lon = element.get("lon") or element.get("center", {}).get("lon")
            
            if not lat or not lon:
                continue
            
            tags = element.get("tags", {})
            amenity = tags.get("amenity", "hospital")
            
            # Map OSM amenity to our facility type
            facility_type = "hospital"
            if amenity == "clinic":
                facility_type = "clinic"
            elif amenity == "doctors":
                facility_type = "clinic"
            elif amenity == "pharmacy":
                facility_type = "pharmacy"
            
            facilities.append({
                "osm_id": element.get("id"),
                "name": tags.get("name", f"Medical Facility {element.get('id')}"),
                "lat": lat,
                "lon": lon,
                "facility_type": facility_type,
                "tags": {
                    "name": tags.get("name", ""),
                    "amenity": amenity,
                    "healthcare": tags.get("healthcare", ""),
                    "operator": tags.get("operator", ""),
                },
            })
        
        return facilities
    
    except Exception as e:
        logger.error(f"  Overpass API error: {e}")
        return []


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_medical(repo=None):
    """Ingest medical facilities for all four districts."""
    if repo is None:
        repo = get_repo()
    
    stats = IngestStats()
    source = SOURCES["osm_overpass"]
    
    logger.info("=" * 60)
    logger.info("INGESTING MEDICAL FACILITIES FROM OVERPASS")
    logger.info("=" * 60)
    
    for district_id, bbox in DISTRICT_BBOXES.items():
        logger.info(f"\n[{district_id.upper()}] Fetching medical facilities...")
        
        # Check existing
        existing = repo.get_medical_facilities(district_id)
        if len(existing) > 0:
            logger.info(f"  [{district_id}] Already has {len(existing)} facilities, skipping")
            stats.record(district_id, "overpass", "medical", 0)
            continue
        
        # Fetch from Overpass
        raw_facilities = fetch_medical_overpass(bbox, district_id)
        logger.info(f"  [{district_id}] Fetched {len(raw_facilities)} facilities from Overpass")
        
        # Ingest
        if raw_facilities:
            facilities = []
            for f in raw_facilities:
                facility = MedicalFacility(
                    id=f"osm_{district_id}_{f['osm_id']}",
                    district_id=district_id,
                    name=f["name"],
                    lat=f["lat"],
                    lon=f["lon"],
                    facility_type=f["facility_type"],
                    osm_id=f["osm_id"],
                    provenance=Provenance.REAL,
                )
                facilities.append(facility)
            
            repo.upsert_medical_facilities(facilities)
            logger.info(f"  [{district_id}] ✓ {len(facilities)} medical facilities ingested")
            stats.record(district_id, "overpass", "medical", len(facilities))
        else:
            logger.info(f"  [{district_id}] No medical facilities found")
            stats.record(district_id, "overpass", "medical", 0)
        
        rate_limit(2.0)
    
    logger.info("\n" + stats.summary())
    return stats


if __name__ == "__main__":
    ingest_medical()
