"""
Building exposure tool: counts buildings within flood zone.

Extracted from Step 3 of assess_disaster_priority.
Includes cache-first pattern and error handling.
Accepts either a known location name or explicit lat/lon coordinates.
"""

import requests
from strands import tool
from shapely.geometry import Point
from agent.config import KNOWN_LOCATIONS, OVERPASS_URL, OVERPASS_HEADERS
from agent.data_loader import FLOOD_POLYGONS, _load_from_cache, _save_to_cache
from agent.tools.flood_tool import _resolve_location, _cache_key_for_coords


@tool
def get_building_exposure(location: str = None, lat: float = None, lon: float = None) -> dict:
    """
    Count buildings within 1.5km radius and determine how many are in flood zones.

    Accepts EITHER a known location name OR explicit lat/lon coordinates.

    Uses cache-first pattern: checks local cache before hitting Overpass API.
    On timeout/error, returns honest "UNAVAILABLE" message (not confirmed absence).

    Args:
        location: known location name (e.g. "sivasagar_flood_zone")
        lat: latitude coordinate (decimal degrees)
        lon: longitude coordinate (decimal degrees)

    Returns:
        {
            "location": str,
            "total_buildings": int,
            "exposed_count": int,
            "exposure_ratio": float (0.0-1.0),
            "detail": str,
            "data_available": bool
        }
    """
    print(f"  [Tool: get_building_exposure] location='{location}' lat={lat} lon={lon}")

    # Resolve location from name or coordinates
    point_lon, point_lat, location_label = _resolve_location(location, lat, lon)
    if point_lon is None:
        # location_label is the error dict
        return {
            "location": str(location or "unknown"),
            "total_buildings": 0,
            "exposed_count": 0,
            "exposure_ratio": 0.0,
            "detail": location_label.get("detail", "No location provided."),
            "data_available": False,
            "error": location_label.get("error", "No location provided.")
        }

    # Determine cache key: use name if known, coordinate string otherwise
    cache_key = location.strip().lower() if location else _cache_key_for_coords(point_lat, point_lon)

    radius_m = 1500  # 1.5km radius - tighter scope for localized exposure

    query = f"""
    [out:json][timeout:30];
    (
      way["building"](around:{radius_m},{point_lat},{point_lon});
    );
    out body;
    >;
    out skel qt;
    """

    # Try cache first
    cached_data = _load_from_cache("buildings", cache_key)

    if cached_data:
        data = cached_data
    else:
        try:
            response = requests.post(
                OVERPASS_URL,
                data={"data": query},
                headers=OVERPASS_HEADERS,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            _save_to_cache("buildings", cache_key, data)
        except requests.exceptions.Timeout:
            return {
                "location": location_label,
                "total_buildings": 0,
                "exposed_count": 0,
                "exposure_ratio": 0.0,
                "detail": "Building exposure: TIMEOUT on Overpass API. Treat as unknown, not as confirmed absence.",
                "data_available": False,
                "error": "TIMEOUT on Overpass API (building exposure)"
            }
        except Exception as e:
            print(f"    [DEBUG] Building exposure API error: {type(e).__name__}: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"    [DEBUG] HTTP Status: {e.response.status_code}")
            return {
                "location": location_label,
                "total_buildings": 0,
                "exposed_count": 0,
                "exposure_ratio": 0.0,
                "detail": f"Building exposure: API ERROR ({type(e).__name__}). Treat as unknown, not as confirmed absence.",
                "data_available": False,
                "error": f"API ERROR: {type(e).__name__}: {str(e)}"
            }

    # Parse buildings
    buildings = [el for el in data.get("elements", []) if el.get("type") == "way"]
    total_buildings = len(buildings)

    exposed_count = 0

    if total_buildings > 0:
        for building in buildings:
            node_coords = [
                (n["lon"], n["lat"])
                for n in data["elements"]
                if n.get("type") == "node" and n["id"] in building.get("nodes", [])
            ]
            if not node_coords:
                continue
            centroid_lon = sum(c[0] for c in node_coords) / len(node_coords)
            centroid_lat = sum(c[1] for c in node_coords) / len(node_coords)
            b_point = Point(centroid_lon, centroid_lat)
            if any(poly.contains(b_point) for poly in FLOOD_POLYGONS):
                exposed_count += 1

    exposure_ratio = exposed_count / total_buildings if total_buildings else 0.0

    detail = f"Building exposure: {total_buildings} buildings, {exposed_count} exposed ({exposure_ratio*100:.0f}%)"

    return {
        "location": location_label,
        "total_buildings": total_buildings,
        "exposed_count": exposed_count,
        "exposure_ratio": exposure_ratio,
        "detail": detail,
        "data_available": total_buildings > 0
    }
