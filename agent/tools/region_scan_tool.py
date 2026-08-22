"""
Region scan tool: scans a grid of points across a bounding box
and reports which are flood-affected, with exact vs near-flood distinction.

Uses get_flood_status with lat/lon coordinates for each grid point.
Cache-first pattern for flood status (no Overpass calls needed — flood
data is loaded from GeoJSON at startup).
"""

import time
from strands import tool
from agent.tools.flood_tool import get_flood_status


@tool
def scan_region(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    grid_size_km: float = 2.0
) -> dict:
    """
    Scan a rectangular region for flood-affected points.

    Divides the bounding box into a grid of points spaced grid_size_km
    apart, checks flood status at each point using get_flood_status, and
    reports both exactly_contained and near_flood_zone points separately.

    Args:
        min_lat: southern boundary latitude
        min_lon: western boundary longitude
        max_lat: northern boundary latitude
        max_lon: eastern boundary longitude
        grid_size_km: spacing between grid points in km (default 2.0)

    Returns:
        {
            "total_points_scanned": int,
            "exactly_contained_count": int,
            "near_flood_zone_count": int,
            "unaffected_count": int,
            "flooded_points": list of {lat, lon, nearest_flood_polygon_km2, detail, containment_status},
            "region_bounds": str
        }
    """
    print(f"  [Tool: scan_region] bounds=({min_lat},{min_lon})-({max_lat},{max_lon}), grid={grid_size_km}km")

    # Convert grid_size_km to approximate degree spacing
    # 1 degree latitude ≈ 111km, 1 degree longitude ≈ 111km * cos(lat)
    avg_lat = (min_lat + max_lat) / 2
    lat_step = grid_size_km / 111.0
    lon_step = grid_size_km / (111.0 * __import__('math').cos(__import__('math').radians(avg_lat)))

    exactly_contained_points = []
    near_flood_zone_points = []
    total_scanned = 0

    lat = min_lat
    while lat <= max_lat:
        lon = min_lon
        while lon <= max_lon:
            total_scanned += 1
            result = get_flood_status(lat=round(lat, 4), lon=round(lon, 4))

            if result.get("exactly_contained"):
                exactly_contained_points.append({
                    "lat": round(lat, 4),
                    "lon": round(lon, 4),
                    "nearest_flood_polygon_km2": result["nearest_flood_polygon_km2"],
                    "detail": result["detail"],
                    "containment_status": "exactly_contained"
                })
            elif result.get("near_flood_zone"):
                near_flood_zone_points.append({
                    "lat": round(lat, 4),
                    "lon": round(lon, 4),
                    "nearest_flood_polygon_km2": result["nearest_flood_polygon_km2"],
                    "detail": result["detail"],
                    "containment_status": "near_flood_zone"
                })

            lon += lon_step
        lat += lat_step

    # Sort each list by flood polygon size (largest first)
    exactly_contained_points.sort(key=lambda p: p["nearest_flood_polygon_km2"], reverse=True)
    near_flood_zone_points.sort(key=lambda p: p["nearest_flood_polygon_km2"], reverse=True)

    # Combined flooded list for backward compatibility
    flooded_points = exactly_contained_points + near_flood_zone_points

    unaffected_count = total_scanned - len(flooded_points)

    result = {
        "total_points_scanned": total_scanned,
        "exactly_contained_count": len(exactly_contained_points),
        "near_flood_zone_count": len(near_flood_zone_points),
        "unaffected_count": unaffected_count,
        "flooded_points": flooded_points,
        "flooded_count": len(flooded_points),
        "region_bounds": f"({min_lat},{min_lon}) to ({max_lat},{max_lon})",
        "grid_size_km": grid_size_km
    }

    print(f"  [scan_region] Scanned {total_scanned} points: "
          f"{len(exactly_contained_points)} exactly contained, "
          f"{len(near_flood_zone_points)} near flood zone, "
          f"{unaffected_count} unaffected")
    return result
