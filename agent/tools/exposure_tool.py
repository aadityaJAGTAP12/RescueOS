"""
Building exposure tool: counts buildings within flood zone.

Extracted from Step 3 of assess_disaster_priority.
Includes cache-first pattern and error handling.
"""

import requests
from strands import tool
from shapely.geometry import Point
from agent.config import KNOWN_LOCATIONS, OVERPASS_URL, OVERPASS_HEADERS
from agent.data_loader import FLOOD_POLYGONS, _load_from_cache, _save_to_cache


@tool
def get_building_exposure(location: str) -> dict:
    """
    Count buildings within 1.5km radius and determine how many are in flood zones.
    
    Uses cache-first pattern: checks local cache before hitting Overpass API.
    On timeout/error, returns honest "UNAVAILABLE" message (not confirmed absence).
    
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
    print(f"  [Tool: get_building_exposure] location='{location}'")
    
    # Validate location
    key = location.strip().lower()
    if key not in KNOWN_LOCATIONS:
        return {
            "location": location,
            "total_buildings": 0,
            "exposed_count": 0,
            "exposure_ratio": 0.0,
            "detail": f"No coordinate data available for '{location}'.",
            "data_available": False,
            "error": f"Location '{location}' not in KNOWN_LOCATIONS."
        }
    
    lon, lat = KNOWN_LOCATIONS[key]
    radius_m = 1500  # 1.5km radius - tighter scope for localized exposure
    
    query = f"""
    [out:json][timeout:30];
    (
      way["building"](around:{radius_m},{lat},{lon});
    );
    out body;
    >;
    out skel qt;
    """
    
    # Try cache first
    cached_data = _load_from_cache("buildings", location)
    
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
            _save_to_cache("buildings", location, data)
        except requests.exceptions.Timeout:
            return {
                "location": location,
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
                "location": location,
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
        "location": location,
        "total_buildings": total_buildings,
        "exposed_count": exposed_count,
        "exposure_ratio": exposure_ratio,
        "detail": detail,
        "data_available": total_buildings > 0
    }
