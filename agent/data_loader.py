"""
Data loading module: FLOOD_POLYGONS initialization and helper functions.

FLOOD_POLYGONS is loaded once at module import time and cached in memory.
Caching helpers (cache-first pattern) avoid repeated Overpass API calls.
"""

import json
import os
import math
from shapely.geometry import shape
from agent.config import CACHE_DIR

# ---------------------------------------------------------------------------
# Load flood data from geojson at module import (load once, cache in memory)
# Uses path relative to this file's directory so tests can import safely.
# ---------------------------------------------------------------------------

_FLOOD_GEOJSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "sivasagar_flood.geojson",
)

try:
    with open(_FLOOD_GEOJSON, "r") as f:
        FLOOD_DATA = json.load(f)
    FLOOD_POLYGONS = [shape(feature["geometry"]) for feature in FLOOD_DATA["features"]]
except FileNotFoundError:
    FLOOD_DATA = {"features": []}
    FLOOD_POLYGONS = []


# ---------------------------------------------------------------------------
# Haversine distance helper
# ---------------------------------------------------------------------------

def haversine_km(lon1, lat1, lon2, lat2):
    """Straight-line distance in km between two lon/lat points."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Cache helpers: cache-first pattern for Overpass API responses
# Keys and file naming pattern must match existing cached files exactly
# ---------------------------------------------------------------------------

def _ensure_cache_dir():
    """Create cache directory if it doesn't exist."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)


def _get_cache_path(query_type: str, location: str) -> str:
    """Return the cache file path for a query.
    
    Examples:
        query_type='buildings', location='sivasagar'
        -> 'data/cache/buildings_sivasagar.json'
    """
    return os.path.join(CACHE_DIR, f"{query_type}_{location.lower()}.json")


def _load_from_cache(query_type: str, location: str) -> dict | None:
    """Load cached Overpass response, if it exists.
    
    Returns None if cache miss or load error. Prints status messages.
    """
    cache_path = _get_cache_path(query_type, location)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                print(f"    [CACHE HIT] Loading {query_type} data from {cache_path}")
                return json.load(f)
        except Exception as e:
            print(f"    [CACHE ERROR] Failed to load cache: {e}")
    return None


def _save_to_cache(query_type: str, location: str, data: dict) -> None:
    """Save Overpass response to local cache.
    
    Creates cache directory if needed. Prints status messages.
    Gracefully handles save errors (doesn't crash if cache write fails).
    """
    _ensure_cache_dir()
    cache_path = _get_cache_path(query_type, location)
    try:
        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"    [CACHE SAVE] Saved {query_type} data to {cache_path}")
    except Exception as e:
        print(f"    [CACHE ERROR] Failed to save cache: {e}")
