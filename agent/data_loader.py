"""
Data loading module: FLOOD_POLYGONS initialization and helper functions.

FLOOD_POLYGONS is loaded once at module import time and cached in memory.
Caching helpers (cache-first pattern) avoid repeated Overpass API calls.

Phase 4: Repository-aware data access functions added.
Tools should call get_flood_polygons() / get_known_locations() instead
of importing FLOOD_POLYGONS / KNOWN_LOCATIONS directly.
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
# Phase 4: Repository-aware data access
# Tools should call these instead of importing module-level variables.
# Falls back to legacy file-based data when no repository data exists.
# ---------------------------------------------------------------------------

# Module-level cache for repository polygons (keyed by district_id)
_repo_polygon_cache: dict[str, list] = {}
_repo_data_cache: dict[str, dict] = {}


def get_flood_polygons(district_id: str = None, observed_at: str = None) -> list:
    """
    Get flood polygons for a district, with fallback to legacy file data.

    Priority:
    1. Repository flood snapshot for district/date
    2. Legacy FLOOD_POLYGONS from file

    Args:
        district_id: district to query (None = use legacy fallback)
        observed_at: optional ISO date string to filter snapshots

    Returns: list of Shapely polygons
    """
    if district_id is not None:
        try:
            from agent.data.repository import get_repository
            repo = get_repository()
            snapshot = repo.get_latest_flood_snapshot(district_id, observed_at=observed_at)
            if snapshot and snapshot.geometry_geojson:
                features = snapshot.geometry_geojson.get("features", [])
                return [shape(f["geometry"]) for f in features if "geometry" in f]
        except Exception:
            pass
    # Fallback to legacy file data
    return FLOOD_POLYGONS


def get_flood_data(district_id: str = None, observed_at: str = None) -> dict:
    """
    Get flood GeoJSON data for a district, with fallback to legacy.

    Returns: GeoJSON FeatureCollection dict
    """
    if district_id is not None:
        try:
            from agent.data.repository import get_repository
            repo = get_repository()
            snapshot = repo.get_latest_flood_snapshot(district_id, observed_at=observed_at)
            if snapshot and snapshot.geometry_geojson:
                return snapshot.geometry_geojson
        except Exception:
            pass
    return FLOOD_DATA


def get_known_locations(district_id: str = None) -> dict:
    """
    Get known locations for a district, with fallback to legacy KNOWN_LOCATIONS.

    Returns: dict of {name: (lon, lat)}
    """
    if district_id is not None:
        try:
            from agent.data.repository import get_repository
            repo = get_repository()
            settlements = repo.list_settlements(district_id=district_id)
            if settlements:
                return {s.id: (s.lon, s.lat) for s in settlements}
        except Exception:
            pass
    # Fallback to legacy KNOWN_LOCATIONS
    from agent.config import KNOWN_LOCATIONS
    return KNOWN_LOCATIONS


def get_all_known_locations() -> dict:
    """
    Get ALL known locations across all districts.

    Returns: dict of {name: (lon, lat)}
    """
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        settlements = repo.list_settlements()
        if settlements:
            return {s.id: (s.lon, s.lat) for s in settlements}
    except Exception:
        pass
    from agent.config import KNOWN_LOCATIONS
    return KNOWN_LOCATIONS


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
