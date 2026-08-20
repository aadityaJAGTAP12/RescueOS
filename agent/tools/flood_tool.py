"""
Flood assessment tool: checks if location is flooded and measures flood extent.

Extracted from Step 1 of assess_disaster_priority.
"""

from strands import tool
from shapely.geometry import Point
from agent.config import KNOWN_LOCATIONS
from agent.data_loader import FLOOD_POLYGONS


@tool
def get_flood_status(location: str) -> dict:
    """
    Check if a location is within or near a flood polygon, and measure
    the nearest flood polygon's size.
    
    Returns:
        {
            "flooded": bool,
            "total_flood_polygons": int,
            "nearest_flood_polygon_km2": float,
            "detail": str
        }
    
    This is used to determine flood-scale risk and as an early gate:
    if not flooded, priority is automatically NONE.
    """
    print(f"  [Tool: get_flood_status] location='{location}'")
    
    # Validate location
    key = location.strip().lower()
    if key not in KNOWN_LOCATIONS:
        return {
            "flooded": False,
            "total_flood_polygons": len(FLOOD_POLYGONS),
            "nearest_flood_polygon_km2": 0.0,
            "detail": f"No coordinate data available for '{location}'.",
            "error": f"Location '{location}' not in KNOWN_LOCATIONS."
        }
    
    lon, lat = KNOWN_LOCATIONS[key]
    point = Point(lon, lat)
    
    # Check if point is inside or very close to any flood polygon
    is_flooded = any(
        poly.contains(point) or poly.distance(point) < 0.01 for poly in FLOOD_POLYGONS
    )
    
    total_flood_polygons = len(FLOOD_POLYGONS)
    
    # Find nearest flood polygon and its size
    nearest_flood_polygon_km2 = 0.0
    if FLOOD_POLYGONS:
        closest_poly = min(FLOOD_POLYGONS, key=lambda p: p.distance(point))
        nearest_flood_polygon_km2 = closest_poly.area * 111 * 111  # rough deg->km2
    
    detail = (
        f"FLOODING DETECTED: {total_flood_polygons} flood-affected areas in district"
        if is_flooded
        else f"NO FLOODING AT POINT: {total_flood_polygons} areas affected elsewhere in district"
    )
    
    return {
        "flooded": is_flooded,
        "total_flood_polygons": total_flood_polygons,
        "nearest_flood_polygon_km2": nearest_flood_polygon_km2,
        "detail": detail
    }
