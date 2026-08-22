"""
Road status tool: checks whether roads near a location are flood-affected.

Queries OpenStreetMap for roads (highway=*) within a radius, then checks
which road segments intersect or pass very close to flood polygons.
Returns a summary of total roads found and how many appear flood-affected.
"""

import requests
from strands import tool
from shapely.geometry import Point, LineString
from agent.config import KNOWN_LOCATIONS, OVERPASS_URL, OVERPASS_HEADERS
from agent.data_loader import FLOOD_POLYGONS, _load_from_cache, _save_to_cache
from agent.tools.flood_tool import _resolve_location, _cache_key_for_coords


@tool
def get_road_status(
    location: str = None,
    lat: float = None,
    lon: float = None,
    radius_m: int = 2000
) -> dict:
    """
    Check road conditions near a location for flood impact.

    Queries OpenStreetMap for roads within radius_m of a point, then checks
    which road segments intersect or pass very close to flood polygons.

    Accepts EITHER a known location name OR explicit lat/lon coordinates.

    Args:
        location: known location name (e.g. "sivasagar_flood_zone")
        lat: latitude coordinate (decimal degrees)
        lon: longitude coordinate (decimal degrees)
        radius_m: search radius in meters (default 2000)

    Returns:
        {
            "location": str,
            "total_roads": int,
            "flood_affected_roads": int,
            "flood_affected_ratio": float (0.0-1.0),
            "road_names": list of str (major road names if tagged),
            "detail": str,
            "data_available": bool
        }
    """
    print(f"  [Tool: get_road_status] location='{location}' lat={lat} lon={lon} radius={radius_m}m")

    # Resolve location from name or coordinates
    point_lon, point_lat, location_label = _resolve_location(location, lat, lon)
    if point_lon is None:
        return {
            "location": str(location or "unknown"),
            "total_roads": 0,
            "flood_affected_roads": 0,
            "flood_affected_ratio": 0.0,
            "road_names": [],
            "detail": location_label.get("detail", "No location provided."),
            "data_available": False,
            "error": location_label.get("error", "No location provided.")
        }

    # Determine cache key
    cache_key = location.strip().lower() if location else _cache_key_for_coords(point_lat, point_lon)

    # Overpass query for roads
    query = f"""
    [out:json][timeout:30];
    (
      way["highway"](around:{radius_m},{point_lat},{point_lon});
    );
    out body;
    >;
    out skel qt;
    """

    # Try cache first
    cached_data = _load_from_cache("roads", cache_key)

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
            _save_to_cache("roads", cache_key, data)
        except requests.exceptions.Timeout:
            return {
                "location": location_label,
                "total_roads": 0,
                "flood_affected_roads": 0,
                "flood_affected_ratio": 0.0,
                "road_names": [],
                "detail": "Road status: TIMEOUT on Overpass API. Treat as unknown, not as confirmed absence.",
                "data_available": False,
                "error": "TIMEOUT on Overpass API (road status)"
            }
        except Exception as e:
            print(f"    [DEBUG] Road status API error: {type(e).__name__}: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"    [DEBUG] HTTP Status: {e.response.status_code}")
            return {
                "location": location_label,
                "total_roads": 0,
                "flood_affected_roads": 0,
                "flood_affected_ratio": 0.0,
                "road_names": [],
                "detail": f"Road status: API ERROR ({type(e).__name__}). Treat as unknown, not as confirmed absence.",
                "data_available": False,
                "error": f"API ERROR: {type(e).__name__}: {str(e)}"
            }

    # Parse roads (ways with highway tag)
    roads = [el for el in data.get("elements", []) if el.get("type") == "way"]
    total_roads = len(roads)

    flood_affected = 0
    road_names = []

    # Flood proximity threshold: ~50m in degrees (0.00045 degrees ≈ 50m)
    FLOOD_PROXIMITY_DEG = 0.00045

    for road in roads:
        # Get road node coordinates
        node_coords = [
            (n["lon"], n["lat"])
            for n in data["elements"]
            if n.get("type") == "node" and n["id"] in road.get("nodes", [])
        ]

        if len(node_coords) < 2:
            continue

        # Check if any segment of the road is near a flood polygon
        road_is_flooded = False
        for i in range(len(node_coords) - 1):
            seg_start = Point(node_coords[i])
            seg_end = Point(node_coords[i + 1])

            for poly in FLOOD_POLYGONS:
                # Check if either endpoint is near the polygon
                if (poly.distance(seg_start) < FLOOD_PROXIMITY_DEG or
                    poly.distance(seg_end) < FLOOD_PROXIMITY_DEG):
                    road_is_flooded = True
                    break
                # Check if the segment intersects the polygon
                try:
                    segment = LineString([node_coords[i], node_coords[i + 1]])
                    if poly.intersects(segment) or poly.distance(segment) < FLOOD_PROXIMITY_DEG:
                        road_is_flooded = True
                        break
                except Exception:
                    pass
            if road_is_flooded:
                break

        if road_is_flooded:
            flood_affected += 1
            # Collect road name if tagged
            name = road.get("tags", {}).get("name")
            if name and name not in road_names:
                road_names.append(name)

    flood_ratio = flood_affected / total_roads if total_roads > 0 else 0.0

    detail = (
        f"Road status: {total_roads} roads found, {flood_affected} appear flood-affected "
        f"({flood_ratio*100:.0f}%)"
        if total_roads > 0
        else "Road status: No roads found within search radius."
    )

    return {
        "location": location_label,
        "total_roads": total_roads,
        "flood_affected_roads": flood_affected,
        "flood_affected_ratio": flood_ratio,
        "road_names": road_names,
        "detail": detail,
        "data_available": total_roads > 0
    }
