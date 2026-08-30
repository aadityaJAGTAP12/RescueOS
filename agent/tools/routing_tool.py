"""
OSRM Routing Tool

Provides real road-network routing via OSRM backend, with graceful
fallback to straight-line (haversine) distance when OSRM is unavailable.

Key principle: If OSRM is unreachable, we NEVER silently pretend a
straight-line approximation is a real route. The response explicitly
indicates which method was used.

Phase 2: Flood-aware routing — detects whether a route passes through
or near any flood polygon. Returns warning information alongside every
route. OSRM does NOT support per-query polygon avoidance, so this is
DETECTION + WARNING only (not automatic avoidance).
"""

import os
import json
import math
import requests
from typing import Optional
from shapely.geometry import LineString
from shapely.strtree import STRtree
from agent.data_loader import haversine_km, FLOOD_POLYGONS, get_flood_polygons


# OSRM configuration
OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "http://localhost:5001")
OSRM_TIMEOUT_SECONDS = 10  # Reasonable timeout for routing requests

# ---------------------------------------------------------------------------
# Spatial index for flood-crossing detection (built once at module load)
# Phase 4: Falls back to repository polygons via get_flood_polygons()
# ---------------------------------------------------------------------------

_FLOOD_TREE = STRtree(FLOOD_POLYGONS) if FLOOD_POLYGONS else None


def check_route_flood_intersection(route_geometry: list, district_id: str = None) -> dict:
    """
    Given a route's geometry (list of [lon, lat] coordinate pairs from OSRM),
    checks whether the route passes through or near any flood polygon.

    Phase 4: Uses repository-backed flood polygons when available.
    Falls back to legacy FLOOD_POLYGONS.

    Uses STRtree spatial indexing (same approach as exposure_tool.py) for
    O(log n) candidate selection, then verifies actual intersection.

    Args:
        route_geometry: List of [lon, lat] coordinate pairs.
        district_id: optional district for repository-backed flood data

    Returns:
        {
            "crosses_flood_zone": bool,
            "intersecting_polygons": [
                {"polygon_area_km2": float, "approximate_location": [lat, lon]}
            ],
            "warning": str or None
        }
    """
    # Phase 4: Get polygons from repository or legacy fallback
    flood_polys = get_flood_polygons(district_id)
    flood_tree = STRtree(flood_polys) if flood_polys else None

    if flood_tree is None or not route_geometry or len(route_geometry) < 2:
        return {
            "crosses_flood_zone": False,
            "intersecting_polygons": [],
            "warning": None,
        }

    try:
        route_line = LineString(route_geometry)
    except Exception:
        # Degenerate geometry (e.g. all points identical)
        return {
            "crosses_flood_zone": False,
            "intersecting_polygons": [],
            "warning": None,
        }

    # Use STRtree for fast candidate selection
    candidates = flood_tree.query(route_line)

    intersecting = []
    for idx in candidates:
        polygon = flood_polys[idx]
        if route_line.intersects(polygon):
            # Calculate polygon area in km² (approximate)
            area_deg2 = polygon.area
            # Convert deg² to km² at ~27°N latitude (Assam)
            # 1° lat ≈ 111 km, 1° lon ≈ 111 * cos(27°) ≈ 98.9 km
            area_km2 = area_deg2 * 111.0 * 98.9

            # Find approximate location: midpoint of the intersection
            intersection = route_line.intersection(polygon)
            if intersection.is_empty:
                continue
            centroid = intersection.centroid
            # centroid is in (lon, lat) since route_line was built from [lon, lat]
            approx_location = [centroid.y, centroid.x]  # return as [lat, lon]

            intersecting.append({
                "polygon_area_km2": round(area_km2, 4),
                "approximate_location": approx_location,
            })

    crosses = len(intersecting) > 0
    warning = None
    if crosses:
        warning = (
            f"Route passes through {len(intersecting)} flood-affected area(s). "
            f"Automatic avoidance is not currently available — "
            f"coordinator should manually consider an alternative route."
        )

    return {
        "crosses_flood_zone": crosses,
        "intersecting_polygons": intersecting,
        "warning": warning,
    }


def check_osrm_health() -> bool:
    """
    Check if OSRM backend is running and healthy.
    
    Returns:
        True if OSRM is responding to health checks, False otherwise.
    """
    try:
        response = requests.get(
            f"{OSRM_BASE_URL}/health",
            timeout=5
        )
        return response.status_code == 200
    except (requests.RequestException, ConnectionError):
        return False


def get_route(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    exclude_flood_polygons: bool = False
) -> dict:
    """
    Query OSRM for a real driving route between two points.
    
    Args:
        start_lat: Starting point latitude
        start_lon: Starting point longitude
        end_lat: Ending point latitude
        end_lon: Ending point longitude
        exclude_flood_polygons: Whether to attempt flood-avoiding routing (Phase 2)
    
    Returns:
        {
            "status": "success" | "unavailable" | "no_route_found",
            "distance_km": float,           # real road distance (or haversine fallback)
            "duration_minutes": float,       # estimated travel time
            "geometry": [[lon, lat], ...],   # route coordinates for map display
            "source": "OSRM routing engine" | "straight-line (haversine) — routing unavailable",
            "message": str,                  # human-readable status message
            "distance_method": str           # explicit labeling of method used
        }
    """
    # First, check if OSRM is available
    if not check_osrm_health():
        return _fallback_to_haversine(
            start_lat, start_lon, end_lat, end_lon,
            reason="OSRM server unavailable"
        )
    
    try:
        # OSRM uses format: lon,lat;lon,lat
        coordinates = f"{start_lon},{start_lat};{end_lon},{end_lat}"
        
        # Query OSRM for route with geometry
        response = requests.get(
            f"{OSRM_BASE_URL}/route/v1/driving/{coordinates}",
            params={
                "overview": "full",      # Return full route geometry
                "geometries": "geojson", # Use GeoJSON format
                "steps": "true"          # Include turn-by-turn steps
            },
            timeout=OSRM_TIMEOUT_SECONDS
        )
        
        data = response.json()
        
        if data.get("code") != "Ok" or not data.get("routes"):
            return _fallback_to_haversine(
                start_lat, start_lon, end_lat, end_lon,
                reason="No route found between points"
            )
        
        route = data["routes"][0]
        
        # Extract route data
        distance_km = route["distance"] / 1000.0  # Convert meters to km
        duration_minutes = route["duration"] / 60.0  # Convert seconds to minutes
        
        # Extract geometry (list of [lon, lat] coordinates)
        geometry = route["geometry"]["coordinates"]
        
        # Phase 2: Check for flood polygon intersections
        flood_check = check_route_flood_intersection(geometry)
        
        result = {
            "status": "success",
            "distance_km": round(distance_km, 2),
            "duration_minutes": round(duration_minutes, 1),
            "geometry": geometry,
            "source": "OSRM routing engine",
            "message": f"Real road route: {distance_km:.1f} km, ~{duration_minutes:.0f} minutes",
            "distance_method": "OSRM road routing",
            "crosses_flood_zone": flood_check["crosses_flood_zone"],
            "intersecting_polygons": flood_check["intersecting_polygons"],
            "flood_warning": flood_check["warning"],
        }
        
        if flood_check["crosses_flood_zone"]:
            result["message"] += f" WARNING: Route crosses {len(flood_check['intersecting_polygons'])} flood zone(s)."
        
        return result
        
    except requests.RequestException as e:
        return _fallback_to_haversine(
            start_lat, start_lon, end_lat, end_lon,
            reason=f"OSRM request failed: {str(e)}"
        )
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return _fallback_to_haversine(
            start_lat, start_lon, end_lat, end_lon,
            reason=f"Failed to parse OSRM response: {str(e)}"
        )


def _fallback_to_haversine(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    reason: str
) -> dict:
    """
    Graceful fallback to haversine when OSRM is unavailable.
    
    CRITICAL: This always explicitly labels the result as an approximation,
    never pretending it's a real route.
    """
    distance_km = haversine_km(start_lon, start_lat, end_lon, end_lat)
    
    # Estimate driving time assuming average speed of 40 km/h in Assam
    # (accounts for road conditions, traffic, etc.)
    estimated_duration = (distance_km / 40.0) * 60.0  # Convert to minutes
    
    # Generate a straight-line geometry for map display
    geometry = [[start_lon, start_lat], [end_lon, end_lat]]
    
    # Phase 2: Check even the fallback geometry for flood crossings
    flood_check = check_route_flood_intersection(geometry)
    
    result = {
        "status": "unavailable",
        "distance_km": round(distance_km, 2),
        "duration_minutes": round(estimated_duration, 1),
        "geometry": geometry,
        "source": f"straight-line (haversine) — {reason}",
        "message": f"Straight-line approximation: {distance_km:.1f} km (routing unavailable)",
        "distance_method": "straight-line (haversine) — routing unavailable",
        "crosses_flood_zone": flood_check["crosses_flood_zone"],
        "intersecting_polygons": flood_check["intersecting_polygons"],
        "flood_warning": flood_check["warning"],
    }
    
    if flood_check["crosses_flood_zone"]:
        result["message"] += f" WARNING: Route crosses {len(flood_check['intersecting_polygons'])} flood zone(s)."
    
    return result


def get_multiple_routes(
    origin_lat: float,
    origin_lon: float,
    destinations: list[dict]
) -> list[dict]:
    """
    Get routes from one origin to multiple destinations.
    
    Args:
        origin_lat: Origin latitude
        origin_lon: Origin longitude
        destinations: List of {"lat": float, "lon": float, "id": str}
    
    Returns:
        List of route results, one per destination, in the same order.
    """
    results = []
    
    for dest in destinations:
        route = get_route(
            start_lat=origin_lat,
            start_lon=origin_lon,
            end_lat=dest["lat"],
            end_lon=dest["lon"]
        )
        route["destination_id"] = dest.get("id", "unknown")
        results.append(route)
    
    return results


# Convenience function for integration with allocation tool
def get_route_for_allocation(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    destination_name: str = "destination"
) -> dict:
    """
    Get a route formatted for the allocation tool's recommend_destination().
    
    This is the primary integration point - returns data in the format
    expected by the allocation tool, with explicit method labeling.
    """
    route = get_route(
        start_lat=origin_lat,
        start_lon=origin_lon,
        end_lat=destination_lat,
        end_lon=destination_lon
    )
    
    # Add metadata for allocation tool
    route["destination_name"] = destination_name
    route["origin"] = {"lat": origin_lat, "lon": origin_lon}
    route["destination"] = {"lat": destination_lat, "lon": destination_lon}
    
    return route
