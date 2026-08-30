"""
Flood Snapshot Validation Helpers

Helper functions for validating flood polygon output from the
Sentinel-1 processing pipeline. These operate on either
ee.FeatureCollection (server-side) or local GeoJSON data.

Validation output is designed to make it easy to compare districts.
"""

from __future__ import annotations

from typing import Optional

try:
    import ee
    _EE_AVAILABLE = True
except ImportError:
    ee = None
    _EE_AVAILABLE = False

from agent.gee.config import FloodPipelineConfig


# ---------------------------------------------------------------------------
# Server-side validation (ee.FeatureCollection)
# ---------------------------------------------------------------------------

def count_polygons(flood_polygons) -> int:
    """
    Count the number of flood polygons in a FeatureCollection.

    Args:
        flood_polygons: ee.FeatureCollection

    Returns:
        ee.Number — polygon count
    """
    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    return flood_polygons.size()


def total_flooded_area_m2(flood_polygons) -> float:
    """
    Compute total flooded area in square meters.

    Args:
        flood_polygons: ee.FeatureCollection

    Returns:
        ee.Number — total area in m²
    """
    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    def add_area(feature):
        return feature.set("area_m2", feature.geometry().area(maxError=1))

    with_area = flood_polygons.map(add_area)
    return with_area.aggregate_sum("area_m2")


def largest_polygon_area_m2(flood_polygons) -> float:
    """
    Find the area of the largest flood polygon.

    Args:
        flood_polygons: ee.FeatureCollection

    Returns:
        ee.Number — largest polygon area in m²
    """
    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    def add_area(feature):
        return feature.set("area_m2", feature.geometry().area(maxError=1))

    with_area = flood_polygons.map(add_area)
    return with_area.aggregate_max("area_m2")


def smallest_polygon_area_m2(flood_polygons) -> float:
    """
    Find the area of the smallest flood polygon.

    Args:
        flood_polygons: ee.FeatureCollection

    Returns:
        ee.Number — smallest polygon area in m²
    """
    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    def add_area(feature):
        return feature.set("area_m2", feature.geometry().area(maxError=1))

    with_area = flood_polygons.map(add_area)
    return with_area.aggregate_min("area_m2")


def average_polygon_area_m2(flood_polygons) -> float:
    """
    Compute average flood polygon area in square meters.

    Args:
        flood_polygons: ee.FeatureCollection

    Returns:
        ee.Number — average area in m²
    """
    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    def add_area(feature):
        return feature.set("area_m2", feature.geometry().area(maxError=1))

    with_area = flood_polygons.map(add_area)
    return with_area.aggregate_mean("area_m2")


def compute_all_stats(flood_polygons) -> dict:
    """
    Compute all validation statistics in a single pass.

    Args:
        flood_polygons: ee.FeatureCollection

    Returns:
        dict with:
            - polygon_count: ee.Number
            - total_area_m2: ee.Number
            - largest_area_m2: ee.Number
            - smallest_area_m2: ee.Number
            - average_area_m2: ee.Number
    """
    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    def add_area(feature):
        return feature.set("area_m2", feature.geometry().area(maxError=1))

    with_area = flood_polygons.map(add_area)

    return {
        "polygon_count": with_area.size(),
        "total_area_m2": with_area.aggregate_sum("area_m2"),
        "largest_area_m2": with_area.aggregate_max("area_m2"),
        "smallest_area_m2": with_area.aggregate_min("area_m2"),
        "average_area_m2": with_area.aggregate_mean("area_m2"),
    }


# ---------------------------------------------------------------------------
# Local validation (GeoJSON dict)
# ---------------------------------------------------------------------------

def validate_geojson_flood_data(geojson: dict) -> dict:
    """
    Validate a local GeoJSON flood dataset.

    Computes polygon count, total area, largest/smallest polygon,
    and average polygon area.

    Args:
        geojson: dict — GeoJSON FeatureCollection

    Returns:
        dict with validation results
    """
    from shapely.geometry import shape, mapping

    features = geojson.get("features", [])
    polygon_count = len(features)

    if polygon_count == 0:
        return {
            "polygon_count": 0,
            "total_area_m2": 0.0,
            "largest_area_m2": 0.0,
            "smallest_area_m2": 0.0,
            "average_area_m2": 0.0,
            "valid": True,
            "message": "Empty flood dataset (no polygons).",
        }

    areas = []
    valid_count = 0
    invalid_count = 0

    for feature in features:
        try:
            geom = shape(feature.get("geometry", {}))
            if geom.is_valid:
                # Compute area in m² using geodesic approximation
                # For WGS84 polygons, approximate conversion:
                # 1 degree ≈ 111,320 m at equator
                area_deg2 = geom.area
                # More accurate: use equirectangular approximation
                centroid = geom.centroid
                lat_rad = centroid.y * 3.14159 / 180.0
                cos_lat = max(0.1, __import__("math").cos(lat_rad))
                m_per_deg_lat = 111_320.0
                m_per_deg_lon = 111_320.0 * cos_lat
                area_m2 = area_deg2 * m_per_deg_lat * m_per_deg_lon
                areas.append(area_m2)
                valid_count += 1
            else:
                invalid_count += 1
        except Exception:
            invalid_count += 1

    if areas:
        total_area = sum(areas)
        return {
            "polygon_count": polygon_count,
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "total_area_m2": round(total_area, 1),
            "largest_area_m2": round(max(areas), 1),
            "smallest_area_m2": round(min(areas), 1),
            "average_area_m2": round(total_area / len(areas), 1),
            "valid": invalid_count == 0,
            "message": (
                f"Validated {valid_count}/{polygon_count} polygons."
                + (f" {invalid_count} invalid geometries." if invalid_count else "")
            ),
        }
    else:
        return {
            "polygon_count": polygon_count,
            "valid_count": 0,
            "invalid_count": invalid_count,
            "total_area_m2": 0.0,
            "largest_area_m2": 0.0,
            "smallest_area_m2": 0.0,
            "average_area_m2": 0.0,
            "valid": False,
            "message": "No valid polygon geometries found.",
        }


def compare_district_stats(stats_list: list[dict]) -> str:
    """
    Generate a formatted comparison table of flood statistics.

    Args:
        stats_list: list of dicts, each with keys:
            - district_id: str
            - polygon_count: int
            - total_area_m2: float
            - largest_area_m2: float
            - average_area_m2: float

    Returns:
        str — formatted table
    """
    header = f"| {'District':12s} | {'Polygons':>10s} | {'Total km²':>10s} | {'Largest km²':>11s} | {'Avg km²':>10s} |"
    sep = f"|{'-' * 14}|{'-' * 12}|{'-' * 12}|{'-' * 13}|{'-' * 12}|"

    lines = [header, sep]

    for s in stats_list:
        total_km2 = s.get("total_area_m2", 0) / 1e6
        largest_km2 = s.get("largest_area_m2", 0) / 1e6
        avg_km2 = s.get("average_area_m2", 0) / 1e6
        count = s.get("polygon_count", 0)
        district = s.get("district_id", "?")

        lines.append(
            f"| {district:12s} | {count:>10,d} | {total_km2:>10.2f} | {largest_km2:>11.2f} | {avg_km2:>10.2f} |"
        )

    return "\n".join(lines)
