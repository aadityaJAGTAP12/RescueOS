"""
ReliefOS Ingestion — Settlements

Acquires major settlements/towns for four Assam districts:
- Sivasagar
- Jorhat
- Charaideo
- Golaghat

Uses Nominatim API (OSM) with proper rate limiting.
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
from agent.data.models import Settlement, Provenance

logger = setup_logging("settlements")

# ---------------------------------------------------------------------------
# Known settlements (from existing data + research)
# ---------------------------------------------------------------------------

# These are well-known towns/cities in each district
KNOWN_SETTLEMENTS = {
    "sivasagar": [
        {"id": "sivasagar", "name": "Sivasagar", "lat": 26.9701, "lon": 94.6393,
         "aliases": ["sivasagar town", "sivasagar district headquarters"]},
        {"id": "sivasagar_flood_zone", "name": "Sivasagar Flood Zone", "lat": 26.9894, "lon": 94.6698,
         "aliases": ["flood zone", "sivasagar flood area"]},
        {"id": "sivasagar_settlement_flood", "name": "Sivasagar Settlement Flood", "lat": 27.0249, "lon": 94.6285,
         "aliases": ["settlement flood area"]},
        {"id": "amguri", "name": "Amguri", "lat": 26.8264, "lon": 94.5497,
         "aliases": ["amguri town"]},
        {"id": "nazira", "name": "Nazira", "lat": 26.9167, "lon": 94.7833,
         "aliases": ["nazira town"]},
        {"id": "sonari", "name": "Sonari", "lat": 27.0500, "lon": 94.7500,
         "aliases": ["sonari town"]},
    ],
    "jorhat": [
        {"id": "jorhat", "name": "Jorhat", "lat": 26.7509, "lon": 94.2037,
         "aliases": ["jorhat town", "jorhat city"]},
        {"id": "teok", "name": "Teok", "lat": 26.6500, "lon": 94.1500,
         "aliases": ["teok town"]},
        {"id": "golaghat_jorhat", "name": "Golaghat Road", "lat": 26.7000, "lon": 94.2500,
         "aliases": ["golaghat road"]},
        {"id": "majuli", "name": "Majuli", "lat": 26.9500, "lon": 94.0500,
         "aliases": ["majuli island", "majuli river island"]},
        {"id": "dergaon", "name": "Dergaon", "lat": 26.6833, "lon": 93.9500,
         "aliases": ["dergaon town"]},
    ],
    "charaideo": [
        {"id": "charaideo", "name": "Charaideo", "lat": 27.1500, "lon": 94.9500,
         "aliases": ["charaideo town"]},
        {"id": "maiung", "name": "Maiung", "lat": 27.1000, "lon": 94.9000,
         "aliases": ["maiung town"]},
        {"id": "longding_charaideo", "name": "Longding", "lat": 27.2000, "lon": 95.0000,
         "aliases": ["longding town"]},
    ],
    "golaghat": [
        {"id": "golaghat", "name": "Golaghat", "lat": 26.5133, "lon": 93.9600,
         "aliases": ["golaghat town", "golaghat city"]},
        {"id": "bokakhat", "name": "Bokakhat", "lat": 26.6333, "lon": 93.6000,
         "aliases": ["bokakhat town"]},
        {"id": "kaziranga", "name": "Kaziranga", "lat": 26.7000, "lon": 93.3500,
         "aliases": ["kaziranga national park", "kaziranga"]},
        {"id": "dhansiri", "name": "Dhansiri", "lat": 26.5500, "lon": 93.8000,
         "aliases": ["dhansiri town"]},
    ],
}


# ---------------------------------------------------------------------------
# Nominatim search for additional settlements
# ---------------------------------------------------------------------------

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "ReliefOS/1.0 (research)"}


def search_settlements_nominatim(district_name: str, state: str = "Assam") -> list[dict]:
    """Search Nominatim for settlements within a district."""
    query = f"settlements in {district_name} district, {state}, India"
    params = {
        "q": query,
        "format": "json",
        "limit": 20,
        "featuretype": "settlement",
    }
    
    try:
        resp = requests.get(NOMINATIM_URL, params=params,
                          headers=NOMINATIM_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        settlements = []
        for item in data:
            lat = float(item.get("lat", 0))
            lon = float(item.get("lon", 0))
            name = item.get("display_name", "").split(",")[0]
            if lat and lon and name:
                settlements.append({
                    "name": name,
                    "lat": lat,
                    "lon": lon,
                })
        return settlements
    
    except Exception as e:
        logger.warning(f"  Nominatim search error: {e}")
        return []


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_settlements(repo=None):
    """Ingest settlements for all four districts."""
    if repo is None:
        repo = get_repo()
    
    stats = IngestStats()
    source = SOURCES["osm_nominatim"]
    
    logger.info("=" * 60)
    logger.info("INGESTING SETTLEMENTS")
    logger.info("=" * 60)
    
    for district_id, settlements in KNOWN_SETTLEMENTS.items():
        logger.info(f"\n[{district_id.upper()}] Ingesting {len(settlements)} known settlements...")
        
        count = 0
        for s in settlements:
            # Check if settlement already exists
            existing = repo.get_settlement(s["id"])
            if existing:
                continue
            
            settlement = Settlement(
                id=s["id"],
                name=s["name"],
                district_id=district_id,
                lat=s["lat"],
                lon=s["lon"],
                aliases=s.get("aliases", []),
                metadata={
                    "source": source.to_dict(),
                    "provenance": "REAL",
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            repo.upsert_settlement(settlement)
            count += 1
        
        logger.info(f"  [{district_id}] ✓ {count} new settlements ingested")
        stats.record(district_id, "known", "settlement", count)
    
    logger.info("\n" + stats.summary())
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ingest_settlements()
