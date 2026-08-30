"""
Flood assessment tool: checks if location is flooded and measures flood extent.

Extracted from Step 1 of assess_disaster_priority.
Accepts either a known location name or explicit lat/lon coordinates.

Reports two distinct flood-proximity states:
- exactly_contained: point is genuinely inside a flood polygon (poly.contains)
- near_flood_zone: point is within ~1.1km of a polygon but NOT inside it
- flooded: true if either of the above (backward-compatible with existing callers)

Phase 4: Uses repository-backed flood data when available.
Falls back to legacy file-based FLOOD_POLYGONS when no repository data exists.
"""

from strands import tool
from shapely.geometry import Point
from agent.config import KNOWN_LOCATIONS
from agent.data_loader import FLOOD_POLYGONS, get_flood_polygons, get_known_locations


# Proximity buffer: 0.01 degrees ≈ 1.1km at this latitude
FLOOD_PROXIMITY_DEG = 0.01


def _resolve_location(location: str = None, lat: float = None, lon: float = None, district_id: str = None):
    """
    Resolve a location from either a name or raw lat/lon coordinates.

    Phase 4: Tries repository-backed location resolution first,
    falls back to legacy KNOWN_LOCATIONS.

    Returns:
        (point_lon, point_lat, location_label) on success,
        (None, None, error_dict) on failure.
    """
    if lat is not None and lon is not None:
        return lon, lat, f"({lat:.4f}, {lon:.4f})"
    elif location is not None:
        key = location.strip().lower()
        # Phase 4: Try repository-backed resolution first
        known_locs = get_known_locations(district_id)
        if key in known_locs:
            point_lon, point_lat = known_locs[key]
            return point_lon, point_lat, location
        # Fallback to legacy KNOWN_LOCATIONS
        if key in KNOWN_LOCATIONS:
            point_lon, point_lat = KNOWN_LOCATIONS[key]
            return point_lon, point_lat, location
        return None, None, {
            "flooded": False,
            "exactly_contained": False,
            "near_flood_zone": False,
            "total_flood_polygons": len(FLOOD_POLYGONS),
            "nearest_flood_polygon_km2": 0.0,
            "detail": f"No coordinate data available for '{location}'.",
            "error": f"Location '{location}' not in KNOWN_LOCATIONS."
        }
    else:
        return None, None, {
            "flooded": False,
            "exactly_contained": False,
            "near_flood_zone": False,
            "total_flood_polygons": 0,
            "nearest_flood_polygon_km2": 0.0,
            "detail": "Must provide either location name or lat/lon.",
            "error": "No location provided."
        }


def _cache_key_for_coords(lat: float, lon: float) -> str:
    """Generate a cache key string from lat/lon coordinates."""
    return f"{lat:.4f}_{lon:.4f}"


@tool
def get_flood_status(location: str = None, lat: float = None, lon: float = None, district_id: str = None) -> dict:
    """
    Check if a location is within or near a flood polygon, and measure
    the nearest flood polygon's size.

    Accepts EITHER a known location name OR explicit lat/lon coordinates.
    If both are provided, lat/lon takes precedence.

    Phase 4: Uses repository-backed flood data when available.
    Falls back to legacy FLOOD_POLYGONS when no repository data exists.

    Reports two distinct states:
    - exactly_contained: point is genuinely inside a flood polygon
    - near_flood_zone: point is within ~1.1km of a polygon but NOT inside it
    - flooded: true if either (backward-compatible)

    Args:
        location: known location name (e.g. "sivasagar_flood_zone")
        lat: latitude coordinate (decimal degrees)
        lon: longitude coordinate (decimal degrees)
        district_id: optional district for repository-backed flood data

    Returns:
        {
            "flooded": bool,
            "exactly_contained": bool,
            "near_flood_zone": bool,
            "total_flood_polygons": int,
            "nearest_flood_polygon_km2": float,
            "detail": str
        }

    This is used to determine flood-scale risk and as an early gate:
    if not flooded, priority is automatically NONE.
    """
    print(f"  [Tool: get_flood_status] location='{location}' lat={lat} lon={lon} district={district_id}")

    # Phase 4: Auto-resolve district_id from repository
    if district_id is None:
        try:
            from agent.data.repository import get_repository
            repo = get_repository()
            if location is not None:
                settlement = repo.resolve_location(name=location)
            elif lat is not None and lon is not None:
                settlement = repo.resolve_location(lat=lat, lon=lon)
            else:
                settlement = None
            if settlement:
                district_id = settlement.district_id
        except Exception:
            pass

    # Resolve location from name or coordinates
    point_lon, point_lat, location_label = _resolve_location(location, lat, lon, district_id)
    if point_lon is None:
        return location_label  # This is the error dict

    point = Point(point_lon, point_lat)

    # Phase 4: Get polygons from repository or legacy fallback
    polygons = get_flood_polygons(district_id)

    # Check containment and proximity separately
    exactly_contained = False
    near_flood_zone = False

    for poly in polygons:
        if poly.contains(point):
            exactly_contained = True
            break
        elif poly.distance(point) < FLOOD_PROXIMITY_DEG:
            near_flood_zone = True
            # Don't break — a later polygon might contain the point

    # flooded = either state (backward-compatible)
    is_flooded = exactly_contained or near_flood_zone

    total_flood_polygons = len(polygons)

    # Find nearest flood polygon and its size
    nearest_flood_polygon_km2 = 0.0
    if polygons:
        closest_poly = min(polygons, key=lambda p: p.distance(point))
        nearest_flood_polygon_km2 = closest_poly.area * 111 * 111  # rough deg->km2

    # Build honest detail string
    if exactly_contained:
        detail = f"EXACTLY CONTAINED: Point is inside a flood polygon ({total_flood_polygons} flood-affected areas in district)"
    elif near_flood_zone:
        detail = f"NEAR FLOOD ZONE: Point is within ~1.1km of a flood polygon but NOT inside one ({total_flood_polygons} areas in district)"
    else:
        detail = f"NOT FLOOD-AFFECTED: Point is outside all flood polygons ({total_flood_polygons} areas affected elsewhere in district)"

    return {
        "location": location_label,
        "flooded": is_flooded,
        "exactly_contained": exactly_contained,
        "near_flood_zone": near_flood_zone,
        "total_flood_polygons": total_flood_polygons,
        "nearest_flood_polygon_km2": nearest_flood_polygon_km2,
        "detail": detail
    }
