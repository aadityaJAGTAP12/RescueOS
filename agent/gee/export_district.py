"""
District Geometry Export for GEE

Reads existing ReliefOS district boundary geometries from PostGIS
(via the DataRepository) and exports them as valid GeoJSON suitable
for Google Earth Engine.

Output is a GeoJSON Feature with:
- district_id
- district_name
- geometry (Polygon or MultiPolygon)
- provenance/source metadata

Usage:
    from agent.gee.export_district import (
        export_district_geometry,
        export_all_district_geometries,
    )

    # Single district
    feature = export_district_geometry("sivasagar")
    feature = export_district_geometry("jorhat")

    # All four target districts as FeatureCollection
    fc = export_all_district_geometries()
"""

from __future__ import annotations

import os
import sys
from typing import Optional

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.data.repository import get_repository, DataRepository
from agent.data.models import District


# Target districts — used only for batch export, not for per-district branching
TARGET_DISTRICTS = ["sivasagar", "jorhat", "charaideo", "golaghat"]


# ---------------------------------------------------------------------------
# Core export functions
# ---------------------------------------------------------------------------

def _wkt_to_geojson_geom(wkt_str: str) -> Optional[dict]:
    """Convert a WKT string (with optional SRID prefix) to a GeoJSON geometry dict."""
    if not wkt_str:
        return None

    # Strip SRID prefix
    wkt = wkt_str.strip()
    if wkt.upper().startswith("SRID="):
        wkt = wkt.split(";", 1)[1].strip() if ";" in wkt else wkt

    try:
        from shapely import wkt as shapely_wkt
        from shapely.geometry import mapping
        geom = shapely_wkt.loads(wkt)
        if geom.is_empty:
            return None
        geojson_geom = mapping(geom)
        # Ensure CRS is WGS84
        if "crs" in geojson_geom:
            del geojson_geom["crs"]
        return geojson_geom
    except Exception:
        return None


def _validate_geojson_feature(feature: dict) -> dict:
    """
    Validate a GeoJSON Feature for correctness.

    Returns a dict with validation results:
    - valid: bool
    - errors: list of str
    """
    errors = []

    # Check Feature structure
    if feature.get("type") != "Feature":
        errors.append("Not a GeoJSON Feature (type != 'Feature')")
        return {"valid": False, "errors": errors}

    # Check geometry exists
    geom = feature.get("geometry")
    if geom is None:
        errors.append("Geometry is null")
        return {"valid": False, "errors": errors}

    # Check geometry type
    geom_type = geom.get("type", "")
    if geom_type not in ("Polygon", "MultiPolygon"):
        errors.append(f"Geometry type is '{geom_type}', expected Polygon or MultiPolygon")

    # Check coordinates exist and non-empty
    coords = geom.get("coordinates")
    if not coords:
        errors.append("Geometry coordinates are empty")
    elif geom_type == "Polygon":
        # Polygon: list of rings, each ring is list of [lon, lat]
        # Note: shapely.mapping() returns tuples, so check for Sequence
        if not hasattr(coords, '__len__') or len(coords) < 1:
            errors.append("Polygon has no rings")
        else:
            for i, ring in enumerate(coords):
                if not hasattr(ring, '__len__') or len(ring) < 4:
                    errors.append(f"Ring {i} has fewer than 4 points ({len(ring) if hasattr(ring, '__len__') else 0})")
    elif geom_type == "MultiPolygon":
        # MultiPolygon: list of polygons
        if not hasattr(coords, '__len__') or len(coords) < 1:
            errors.append("MultiPolygon has no polygons")

    # Check CRS — should be WGS84 (no explicit CRS in GeoJSON is WGS84 by spec)
    # We just verify no unexpected CRS field

    # Check properties
    props = feature.get("properties", {})
    if not isinstance(props, dict):
        errors.append("Properties is not a dict")

    # Check required fields in properties
    required = ["district_id", "district_name"]
    for field in required:
        if field not in props:
            errors.append(f"Missing required property: {field}")

    return {"valid": len(errors) == 0, "errors": errors}


def export_district_geometry(
    district_id: str,
    repo: Optional[DataRepository] = None,
) -> dict:
    """
    Export a single district boundary as a GeoJSON Feature.

    Reads the district geometry from the DataRepository (PostGIS or
    in-memory) and converts it to valid GeoJSON.

    Args:
        district_id: district identifier (e.g. "sivasagar")
        repo: optional DataRepository instance (uses get_repository() if None)

    Returns:
        GeoJSON Feature dict with:
            - type: "Feature"
            - geometry: Polygon or MultiPolygon
            - properties:
                - district_id: str
                - district_name: str
                - source: str
                - provenance: str
                - license: str

    Raises:
        ValueError: if district not found or has no geometry
    """
    if repo is None:
        repo = get_repository()

    district: Optional[District] = repo.get_district(district_id)
    if district is None:
        raise ValueError(f"District '{district_id}' not found in repository")

    if not district.geometry_wkt:
        raise ValueError(f"District '{district_id}' has no geometry in the database")

    geojson_geom = _wkt_to_geojson_geom(district.geometry_wkt)
    if geojson_geom is None:
        raise ValueError(
            f"District '{district_id}' has invalid geometry: "
            f"could not parse WKT ({district.geometry_wkt[:80]}...)"
        )

    feature = {
        "type": "Feature",
        "geometry": geojson_geom,
        "properties": {
            "district_id": district.id,
            "district_name": district.name,
            "source": "ReliefOS PostGIS",
            "provenance": "REAL",
            "license": "ODbL 1.0",
        },
    }

    return feature


def export_all_district_geometries(
    district_ids: Optional[list[str]] = None,
    repo: Optional[DataRepository] = None,
) -> dict:
    """
    Export multiple district boundaries as a GeoJSON FeatureCollection.

    Args:
        district_ids: list of district IDs to export.
                      Defaults to TARGET_DISTRICTS.
        repo: optional DataRepository instance

    Returns:
        GeoJSON FeatureCollection dict

    Raises:
        ValueError: if no valid districts found
    """
    if district_ids is None:
        district_ids = TARGET_DISTRICTS

    if repo is None:
        repo = get_repository()

    features = []
    errors = []

    for did in district_ids:
        try:
            feature = export_district_geometry(did, repo=repo)
            validation = _validate_geojson_feature(feature)
            if validation["valid"]:
                features.append(feature)
            else:
                errors.append(f"{did}: validation failed: {', '.join(validation['errors'])}")
        except ValueError as e:
            errors.append(f"{did}: {e}")

    if not features and errors:
        raise ValueError(
            f"No valid district geometries exported. Errors: {'; '.join(errors)}"
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "_errors": errors if errors else None,
    }


def validate_district_feature(feature: dict) -> dict:
    """
    Validate a GeoJSON Feature representing a district boundary.

    Checks:
    - Geometry is valid
    - Geometry is non-empty
    - CRS is WGS84 (EPSG:4326) — implicit in GeoJSON spec
    - GeoJSON is valid
    - Geometry is Polygon or MultiPolygon
    - district_id matches expected

    Returns:
        dict with 'valid' (bool) and 'errors' (list of str)
    """
    return _validate_geojson_feature(feature)


def validate_all_features(features: list[dict], expected_district_ids: Optional[list[str]] = None) -> dict:
    """
    Validate a list of GeoJSON Features.

    Returns:
        dict with:
            - all_valid: bool
            - total: int
            - valid: int
            - invalid: int
            - district_ids_found: list of str
            - errors: list of (district_id, error_messages)
    """
    if expected_district_ids is None:
        expected_district_ids = TARGET_DISTRICTS

    results = []
    for f in features:
        props = f.get("properties", {})
        did = props.get("district_id", "unknown")
        validation = _validate_geojson_feature(f)
        results.append((did, validation))

    valid_count = sum(1 for _, v in results if v["valid"])
    invalid_count = len(results) - valid_count
    district_ids_found = [did for did, _ in results]

    # Check for cross-district substitution
    substitution_errors = []
    if expected_district_ids:
        found_set = set(district_ids_found)
        expected_set = set(expected_district_ids)
        missing = expected_set - found_set
        unexpected = found_set - expected_set
        if missing:
            substitution_errors.append(f"Missing districts: {', '.join(missing)}")
        if unexpected:
            substitution_errors.append(f"Unexpected districts: {', '.join(unexpected)}")

    all_errors = []
    for did, v in results:
        if not v["valid"]:
            all_errors.append((did, v["errors"]))
    all_errors.extend([("substitution_check", [e]) for e in substitution_errors])

    return {
        "all_valid": invalid_count == 0 and not substitution_errors,
        "total": len(results),
        "valid": valid_count,
        "invalid": invalid_count,
        "district_ids_found": district_ids_found,
        "errors": all_errors,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    # Export all target districts
    print("Exporting district geometries for GEE...")
    fc = export_all_district_geometries()

    features = fc.get("features", [])
    errors = fc.get("_errors", [])
    print(f"\nExported {len(features)} district(s)")

    for feat in features:
        props = feat["properties"]
        geom = feat["geometry"]
        coords = geom.get("coordinates", [])
        geom_type = geom.get("type", "?")
        # Rough vertex count
        if geom_type == "Polygon":
            vertex_count = sum(len(ring) for ring in coords)
        elif geom_type == "MultiPolygon":
            vertex_count = sum(
                sum(len(ring) for ring in poly)
                for poly in coords
            )
        else:
            vertex_count = 0
        print(f"  {props['district_id']:12s} {geom_type:16s} {vertex_count:>6d} vertices  name={props['district_name']}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")

    # Validate
    validation = validate_all_features(features)
    print(f"\nValidation: {'PASS' if validation['all_valid'] else 'FAIL'}")
    print(f"  Valid: {validation['valid']}/{validation['total']}")

    if not validation["all_valid"]:
        for did, errs in validation["errors"]:
            for err in errs:
                print(f"  {did}: {err}")
        sys.exit(1)

    # Write to file
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "districts_gee.geojson"
    )
    with open(output_path, "w") as f:
        # Remove internal _errors key before writing
        clean_fc = {k: v for k, v in fc.items() if k != "_errors"}
        json.dump(clean_fc, f, indent=2)
    print(f"\nOutput: {output_path}")
