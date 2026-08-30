"""
ReliefOS Phase 5B.1 — Resumable OSM PBF Ingestion into PostGIS

Ingests real OpenStreetMap geographic data from a regional PBF extract
into the PostGIS database for the four initial ReliefOS districts:
  - Sivasagar
  - Jorhat
  - Charaideo
  - Golaghat

Architecture (RESUMABLE):
  1. Load district polygons from PostGIS (spatial filter source)
  2. Parse PBF *per category* with pyrosm (memory-efficient)
  3. Filter features by district polygon (ST_Contains / spatial predicate)
  4. Batch insert into PostGIS via ON CONFLICT DO UPDATE
  5. Report statistics

Key design:
  - RESUMABLE: --only flag to run specific categories independently
  - MEMORY-EFFICIENT: only parse the needed category from PBF per invocation
  - Idempotent: running twice does not create duplicates (ON CONFLICT DO UPDATE)
  - Provenance-tracked: all records marked as REAL / OpenStreetMap
  - NEVER destructive: no TRUNCATE, no DELETE, no DROP

Usage:
    export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos
    python -m scripts.ingest.osm_pbf                    # all categories
    python -m scripts.ingest.osm_pbf --only roads        # roads only
    python -m scripts.ingest.osm_pbf --only medical      # medical facilities only
    python -m scripts.ingest.osm_pbf --only buildings    # buildings only
    python -m scripts.ingest.osm_pbf --only bridges      # bridges only (subset of roads)
    python -m scripts.ingest.osm_pbf --only infrastructure  # other POIs
    python -m scripts.ingest.osm_pbf --only settlements  # settlement augmentation
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
import logging
from datetime import datetime, timezone
from typing import Optional

import geopandas as gpd
import pyrosm
from shapely.geometry import shape, Point, mapping
from shapely.ops import transform
from sqlalchemy import text

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.data.schema import get_engine, create_all_tables, SRID
from agent.data.postgres_repository import PostgresRepository
from agent.data.models import (
    Building, MedicalFacility, Road, Settlement, Provenance,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("osm_pbf")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PBF_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "raw", "osm", "north-eastern-zone-latest.osm.pbf",
)

TARGET_DISTRICTS = ["sivasagar", "jorhat", "charaideo", "golaghat"]

# OSM amenity categories that map to medical facilities
MEDICAL_AMENITY_TAGS = {"hospital", "clinic", "doctors"}

# OSM amenity categories for other useful infrastructure
INFRASTRUCTURE_AMENITY_TAGS = {
    "school", "college", "university",          # Education
    "police", "fire_station",                   # Emergency
    "fuel",                                     # Fuel stations
    "bus_station", "public_transport",          # Transport
    "shelter",                                  # Emergency shelter
    "pharmacy",                                 # Health support
    "blood_bank",                               # Health support
}

# High-value infrastructure categories to report
REPORT_AMENITY_CATEGORIES = [
    "school", "college", "university",
    "police", "fire_station",
    "fuel", "bus_station",
    "pharmacy", "blood_bank",
]

# Road highway types to import (ordered by importance)
ROAD_HIGHWAY_TYPES = {
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "unclassified", "residential", "service",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
    "living_street", "pedestrian", "track", "path",
}

BATCH_SIZE = 500  # Records per batch insert

# All valid category names
ALL_CATEGORIES = ["buildings", "roads", "medical", "bridges", "infrastructure", "settlements"]

# ---------------------------------------------------------------------------
# Source metadata
# ---------------------------------------------------------------------------

OSM_SOURCE = {
    "source_name": "OpenStreetMap PBF Extract",
    "source_url": "https://download.geofabrik.de/asia/india/north-eastern-zone.html",
    "license": "ODbL 1.0",
    "attribution": "© OpenStreetMap contributors",
    "file": os.path.basename(PBF_PATH),
    "ingestion_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_repo() -> PostgresRepository:
    """Get a PostgresRepository connected to the configured database."""
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise ValueError("DATABASE_URL not set. Export it before running ingestion.")
    engine = get_engine(database_url)
    create_all_tables(engine)
    return PostgresRepository(engine=engine)


def load_district_polygons(repo: PostgresRepository) -> dict[str, object]:
    """
    Load district polygons from PostGIS.

    Returns:
        dict mapping district_id -> shapely Polygon/MultiPolygon
    """
    logger.info("Loading district polygons from PostGIS...")
    districts = {}

    with repo._engine.connect() as conn:
        for did in TARGET_DISTRICTS:
            result = conn.execute(
                text("SELECT ST_AsText(geometry) as wkt FROM districts WHERE id = :did"),
                {"did": did}
            )
            row = result.fetchone()
            if row and row.wkt:
                from shapely import wkt as shapely_wkt
                geom = shapely_wkt.loads(row.wkt)
                districts[did] = geom
                logger.info(f"  [{did}] ✓ Boundary loaded ({geom.geom_type})")
            else:
                logger.warning(f"  [{did}] ⚠ No geometry in database — spatial filtering will use bbox fallback")

    return districts


# ---------------------------------------------------------------------------
# Per-category PBF parsing (MEMORY-EFFICIENT)
# ---------------------------------------------------------------------------

def parse_pbf_category(category: str, bounding_box: list[float] = None) -> gpd.GeoDataFrame:
    """
    Parse the PBF file for a SINGLE category only.

    This is the key memory optimization: instead of loading all three
    GeoDataFrames (buildings ~1.9M rows, roads ~300K rows, POIs ~16K rows)
    simultaneously, we create a fresh pyrosm.OSM instance and extract
    only the needed category. The GDF is released after processing.

    When bounding_box is provided (format: [minx, miny, maxx, maxy]),
    pyrosm restricts PBF parsing to features within that bounding box.
    This dramatically reduces memory usage for single-district extractions
    (e.g. ~61K buildings vs ~1.8M+ regional).

    Args:
        category: one of "buildings", "roads", "medical", "bridges",
                  "infrastructure", "settlements"
        bounding_box: optional [minx, miny, maxx, maxy] to restrict PBF parsing

    Returns:
        GeoDataFrame with the requested features (or empty if invalid category)
    """
    logger.info(f"Loading PBF for category: {category}")
    if bounding_box:
        logger.info(f"  Using bounding box constraint: {bounding_box}")
    t0 = time.time()

    osm = pyrosm.OSM(PBF_PATH, bounding_box=bounding_box)

    gdf = None
    if category in ("buildings",):
        logger.info("  Extracting buildings...")
        gdf = osm.get_buildings()

    elif category in ("roads", "bridges"):
        logger.info("  Extracting road network...")
        gdf = osm.get_network(network_type="all")

    elif category in ("medical", "infrastructure", "settlements"):
        logger.info("  Extracting POIs...")
        gdf = osm.get_pois()

    else:
        logger.error(f"  Unknown category: {category}")
        return gpd.GeoDataFrame()

    # Release pyrosm object to free memory
    del osm

    logger.info(f"  {category}: {len(gdf)} features ({time.time()-t0:.1f}s)")
    return gdf


# ---------------------------------------------------------------------------
# Spatial filtering
# ---------------------------------------------------------------------------

def filter_by_districts(
    gdf: gpd.GeoDataFrame,
    district_polygons: dict[str, object],
    only_districts: list[str] = None,
) -> dict[str, gpd.GeoDataFrame]:
    """
    Filter a GeoDataFrame to features that fall within district polygons.

    For point geometries: uses centroid/point containment.
    For polygon geometries: uses centroid containment.
    For line geometries: uses intersects.

    Args:
        gdf: GeoDataFrame to filter
        district_polygons: dict mapping district_id -> shapely geometry
        only_districts: if provided, only filter for these district IDs

    Returns:
        dict mapping district_id -> filtered GeoDataFrame
    """
    if not district_polygons:
        logger.warning("No district polygons available — cannot spatially filter")
        return {}

    # Filter to only requested districts
    if only_districts:
        district_polygons = {k: v for k, v in district_polygons.items() if k in only_districts}

    results = {}
    for did, poly in district_polygons.items():
        try:
            # Use spatial index for efficiency
            if gdf.geometry.is_empty.all():
                results[did] = gdf.iloc[:0]
                continue

            # Get the bounding box of the district polygon for pre-filtering
            minx, miny, maxx, maxy = poly.bounds

            # Pre-filter by bounding box
            bbox_mask = (
                (gdf.geometry.bounds["minx"] <= maxx) &
                (gdf.geometry.bounds["maxx"] >= minx) &
                (gdf.geometry.bounds["miny"] <= maxy) &
                (gdf.geometry.bounds["maxy"] >= miny)
            )
            candidates = gdf[bbox_mask].copy()

            if len(candidates) == 0:
                results[did] = gdf.iloc[:0]
                continue

            # For each geometry type, apply appropriate spatial predicate
            mask = []
            for geom in candidates.geometry:
                if geom is None or geom.is_empty:
                    mask.append(False)
                    continue

                geom_type = geom.geom_type

                if geom_type in ("Point",):
                    mask.append(poly.contains(geom))
                elif geom_type in ("Polygon", "MultiPolygon"):
                    # Use centroid for containment check
                    centroid = geom.centroid
                    mask.append(poly.contains(centroid))
                elif geom_type in ("LineString", "MultiLineString"):
                    # Check if line intersects or is within the district
                    mask.append(poly.intersects(geom))
                else:
                    # Fallback: use centroid
                    try:
                        centroid = geom.centroid
                        mask.append(poly.contains(centroid))
                    except Exception:
                        mask.append(False)

            filtered = candidates[mask].copy()
            results[did] = filtered
        except Exception as e:
            logger.error(f"  [{did}] Spatial filter error: {e}")
            results[did] = gdf.iloc[:0]

    return results


# ---------------------------------------------------------------------------
# Geometry conversion helpers
# ---------------------------------------------------------------------------

def shapely_to_postgis_wkt(geom) -> Optional[str]:
    """Convert a shapely geometry to PostGIS WKT string with SRID."""
    if geom is None or geom.is_empty:
        return None
    return f"SRID={SRID};{geom.wkt}"


def geojson_tags(row) -> dict:
    """Extract useful OSM tags from a GeoDataFrame row as a dict."""
    tags = {}
    tag_cols = ["name", "amenity", "building", "highway", "surface", "bridge",
                "oneway", "width", "lanes", "maxspeed", "operator", "healthcare",
                "addr:city", "addr:street", "addr:housenumber", "phone", "website",
                "opening_hours", "building:levels", "building:material", "height"]
    for col in tag_cols:
        if col in row.index:
            val = row[col]
            if val is not None and str(val) != "nan" and str(val).strip():
                tags[col] = str(val)
    # Also check the 'tags' column if present (dict of all tags)
    if "tags" in row.index and isinstance(row["tags"], dict):
        for k, v in row["tags"].items():
            if k not in tags and v is not None and str(v) != "nan" and str(v).strip():
                tags[k] = str(v)
    return tags


# ---------------------------------------------------------------------------
# Category ingestion functions
# ---------------------------------------------------------------------------

def ingest_buildings(
    district_polygons: dict[str, object],
    repo: PostgresRepository,
    only_districts: list[str] = None,
) -> dict[str, int]:
    """
    Ingest buildings from PBF. Only parses buildings from PBF (memory-efficient).

    Args:
        district_polygons: dict mapping district_id -> shapely geometry
        repo: PostgresRepository
        only_districts: if provided, only ingest for these district IDs

    Returns:
        dict mapping district_id -> count of buildings ingested
    """
    logger.info("=" * 60)
    logger.info("INGESTING BUILDINGS FROM OSM PBF")
    logger.info("=" * 60)

    counts = {}
    total_start = time.time()

    # MEMORY OPTIMIZATION: When targeting a single district, compute its
    # bounding box and pass to pyrosm so it only parses features in that region
    # instead of loading the full regional GeoDataFrame (~1.8M buildings).
    targeted_bbox = None
    if only_districts and len(only_districts) == 1 and district_polygons:
        did = only_districts[0]
        if did in district_polygons:
            targeted_bbox = list(district_polygons[did].bounds)
            logger.info(f"  Single-district mode: using bbox {targeted_bbox} for {did}")

    # Parse only buildings from PBF (memory-efficient, optionally bbox-constrained)
    buildings_gdf = parse_pbf_category("buildings", bounding_box=targeted_bbox)
    filtered = filter_by_districts(buildings_gdf, district_polygons, only_districts=only_districts)

    # Release the full GDF
    del buildings_gdf
    gc.collect()

    # SAFETY CHECK: Pre-import report — verify we are not about to create
    # a full regional GeoDataFrame. Abort if candidate count is suspiciously large.
    MAX_SINGLE_DISTRICT_CANDIDATES = 150_000
    logger.info("\n" + "=" * 60)
    logger.info("SAFETY CHECK: Pre-import report")
    logger.info("=" * 60)
    for did in (only_districts or TARGET_DISTRICTS):
        existing_count = 0
        with repo._engine.connect() as conn:
            result = conn.execute(
                text("SELECT count(*) FROM buildings WHERE district_id = :did"),
                {"did": did}
            )
            existing_count = result.fetchone()[0]

        gdf = filtered.get(did, None)
        candidate_count = len(gdf) if gdf is not None else 0
        expected_new = max(0, candidate_count - existing_count)

        logger.info(f"  [{did}] Existing: {existing_count}, PBF candidates: {candidate_count}, Expected new: {expected_new}")

        if candidate_count > MAX_SINGLE_DISTRICT_CANDIDATES:
            logger.error(f"  [{did}] ABORT: candidate count {candidate_count} exceeds safety threshold {MAX_SINGLE_DISTRICT_CANDIDATES}")
            logger.error(f"  This likely means the full regional GeoDataFrame was loaded. Stopping.")
            raise RuntimeError(f"Safety check failed for {did}: too many candidates ({candidate_count})")

    logger.info("\nSafety check passed — proceeding with insertion.")

    for did in (only_districts or TARGET_DISTRICTS):
        gdf = filtered.get(did, None)
        if gdf is None or len(gdf) == 0:
            logger.info(f"\n[{did.upper()}] No buildings in district")
            counts[did] = 0
            continue

        logger.info(f"\n[{did.upper()}] Buildings in district: {len(gdf)}")

        t0 = time.time()
        batch = []
        ingested = 0

        for idx, row in gdf.iterrows():
            try:
                # Get centroid for point location
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue

                centroid = geom.centroid
                lon, lat = centroid.x, centroid.y

                # Build tags
                tags = geojson_tags(row)

                # Deterministic ID: osm_{district}_{osm_id}
                osm_id_val = int(row.get("id", 0))
                building_id = f"osm_{did}_{osm_id_val}"

                # Polygon WKT for full geometry
                polygon_wkt = shapely_to_postgis_wkt(geom)

                building = Building(
                    id=building_id,
                    district_id=did,
                    osm_id=osm_id_val,
                    lat=lat,
                    lon=lon,
                    tags=tags,
                    in_flood_zone=False,  # Temporal — not set from existence
                    provenance=Provenance.REAL,
                    geometry_wkt=polygon_wkt,
                )
                batch.append(building)

                if len(batch) >= BATCH_SIZE:
                    repo.upsert_buildings(batch)
                    ingested += len(batch)
                    batch = []
            except Exception as e:
                continue  # Skip bad records silently

        # Flush remaining batch
        if batch:
            repo.upsert_buildings(batch)
            ingested += len(batch)

        elapsed = time.time() - t0
        counts[did] = ingested
        logger.info(f"  [{did}] ✓ {ingested} buildings ingested ({elapsed:.1f}s)")

    total_elapsed = time.time() - total_start
    logger.info(f"\nTotal buildings ingested: {sum(counts.values())} ({total_elapsed:.1f}s)")

    # Release filtered GDFs
    del filtered
    gc.collect()

    return counts


def ingest_roads(
    district_polygons: dict[str, object],
    repo: PostgresRepository,
    only_districts: list[str] = None,
) -> dict[str, int]:
    """
    Ingest roads from PBF. Only parses road network (memory-efficient).

    Returns:
        dict mapping district_id -> count of roads ingested
    """
    logger.info("=" * 60)
    logger.info("INGESTING ROADS FROM OSM PBF")
    logger.info("=" * 60)

    counts = {}
    total_start = time.time()

    # Parse only roads from PBF
    roads_gdf = parse_pbf_category("roads")
    filtered = filter_by_districts(roads_gdf, district_polygons, only_districts=only_districts)

    del roads_gdf
    gc.collect()

    active = only_districts or TARGET_DISTRICTS
    for did in active:
        gdf = filtered.get(did, None)
        if gdf is None or len(gdf) == 0:
            logger.info(f"\n[{did.upper()}] No roads in district")
            counts[did] = 0
            continue

        logger.info(f"\n[{did.upper()}] Roads in district: {len(gdf)}")

        t0 = time.time()
        batch = []
        ingested = 0

        for idx, row in gdf.iterrows():
            try:
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue

                # Get coordinates for the Road model
                if geom.geom_type == "MultiLineString":
                    # Use the longest linestring
                    lines = list(geom.geoms)
                    longest = max(lines, key=lambda l: l.length)
                    coords = list(longest.coords)
                elif geom.geom_type == "LineString":
                    coords = list(geom.coords)
                else:
                    continue

                if len(coords) < 2:
                    continue

                # Convert coords to (lon, lat) pairs for Road.geometry_coords
                geometry_coords = [(c[0], c[1]) for c in coords]

                # Road tags
                tags = geojson_tags(row)

                # Bridge detection
                bridge_val = str(row.get("bridge", "")).lower().strip()
                is_bridge = bridge_val == "yes"

                osm_id_val = int(row.get("id", 0))
                road_id = f"osm_{did}_{osm_id_val}"

                road = Road(
                    id=road_id,
                    district_id=did,
                    name=str(row.get("name", "")) or None,
                    highway_type=str(row.get("highway", "unclassified")),
                    osm_id=osm_id_val,
                    geometry_coords=geometry_coords,
                    flood_affected=False,  # Temporal — not set from existence
                    provenance=Provenance.REAL,
                    tags=tags,
                    is_bridge=is_bridge,
                )
                batch.append(road)

                if len(batch) >= BATCH_SIZE:
                    repo.upsert_roads(batch)
                    ingested += len(batch)
                    batch = []
            except Exception as e:
                continue

        if batch:
            repo.upsert_roads(batch)
            ingested += len(batch)

        elapsed = time.time() - t0
        counts[did] = ingested
        logger.info(f"  [{did}] ✓ {ingested} roads ingested ({elapsed:.1f}s)")

    total_elapsed = time.time() - total_start
    logger.info(f"\nTotal roads ingested: {sum(counts.values())} ({total_elapsed:.1f}s)")

    del filtered
    gc.collect()

    return counts


def ingest_medical(
    district_polygons: dict[str, object],
    repo: PostgresRepository,
    only_districts: list[str] = None,
) -> dict[str, dict[str, int]]:
    """
    Ingest medical facilities (hospitals, clinics) from PBF POIs.

    Returns:
        dict mapping district_id -> {hospitals: N, clinics: N}
    """
    logger.info("=" * 60)
    logger.info("INGESTING MEDICAL FACILITIES FROM OSM PBF")
    logger.info("=" * 60)

    counts = {}
    total_start = time.time()

    # Parse only POIs from PBF
    pois_gdf = parse_pbf_category("medical")

    # Filter POIs to medical amenities only
    if "amenity" in pois_gdf.columns:
        medical_mask = pois_gdf["amenity"].isin(MEDICAL_AMENITY_TAGS)
        medical_pois = pois_gdf[medical_mask].copy()
    else:
        medical_pois = pois_gdf.iloc[:0]

    logger.info(f"Total medical POIs in PBF: {len(medical_pois)}")

    filtered = filter_by_districts(medical_pois, district_polygons, only_districts=only_districts) if len(medical_pois) > 0 else {}

    del pois_gdf, medical_pois
    gc.collect()

    for did in (only_districts or TARGET_DISTRICTS):
        gdf = filtered.get(did, None)
        if gdf is None or len(gdf) == 0:
            logger.info(f"\n[{did.upper()}] No medical facilities in district")
            counts[did] = {"hospitals": 0, "clinics": 0}
            continue

        logger.info(f"\n[{did.upper()}] Medical facilities in district: {len(gdf)}")

        hospitals = 0
        clinics = 0

        t0 = time.time()
        batch = []

        for idx, row in gdf.iterrows():
            try:
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue

                centroid = geom.centroid if geom.geom_type != "Point" else geom
                lon, lat = centroid.x, centroid.y

                amenity = str(row.get("amenity", "")).lower()
                name = str(row.get("name", "")).strip()
                if not name or name == "nan":
                    name = f"OSM {amenity.title()} {int(row.get('id', 0))}"

                # Determine facility type
                if amenity == "hospital":
                    facility_type = "hospital"
                    hospitals += 1
                elif amenity in ("clinic", "doctors"):
                    facility_type = "clinic"
                    clinics += 1
                else:
                    facility_type = amenity

                osm_id_val = int(row.get("id", 0))
                facility_id = f"osm_{did}_{osm_id_val}"

                facility = MedicalFacility(
                    id=facility_id,
                    district_id=did,
                    name=name,
                    lat=lat,
                    lon=lon,
                    facility_type=facility_type,
                    osm_id=osm_id_val,
                    provenance=Provenance.REAL,
                )
                batch.append(facility)
            except Exception as e:
                continue

        if batch:
            repo.upsert_medical_facilities(batch)

        elapsed = time.time() - t0
        counts[did] = {"hospitals": hospitals, "clinics": clinics}
        logger.info(f"  [{did}] ✓ {len(batch)} medical facilities ({hospitals} hospitals, {clinics} clinics) ({elapsed:.1f}s)")

    total_elapsed = time.time() - total_start
    total_hospitals = sum(c["hospitals"] for c in counts.values())
    total_clinics = sum(c["clinics"] for c in counts.values())
    logger.info(f"\nTotal medical: {total_hospitals} hospitals, {total_clinics} clinics ({total_elapsed:.1f}s)")

    del filtered
    gc.collect()

    return counts


def ingest_infrastructure(
    district_polygons: dict[str, object],
    repo: PostgresRepository,
    only_districts: list[str] = None,
) -> dict[str, dict[str, int]]:
    """
    Ingest other useful infrastructure POIs from PBF:
    - Schools / educational institutions
    - Police stations
    - Fuel stations
    - Bus stations
    - Blood banks / pharmacies

    These are stored as MedicalFacility records with appropriate facility_type.

    Returns:
        dict mapping district_id -> {category: count}
    """
    logger.info("=" * 60)
    logger.info("INGESTING OTHER INFRASTRUCTURE FROM OSM PBF")
    logger.info("=" * 60)

    counts = {}
    total_start = time.time()

    # Parse only POIs from PBF
    pois_gdf = parse_pbf_category("infrastructure")

    # Filter POIs to infrastructure amenities
    if "amenity" in pois_gdf.columns:
        infra_mask = pois_gdf["amenity"].isin(INFRASTRUCTURE_AMENITY_TAGS)
        infra_pois = pois_gdf[infra_mask].copy()
    else:
        infra_pois = pois_gdf.iloc[:0]

    logger.info(f"Total infrastructure POIs in PBF: {len(infra_pois)}")

    # Report category distribution
    if len(infra_pois) > 0 and "amenity" in infra_pois.columns:
        cat_counts = infra_pois["amenity"].value_counts()
        for cat in REPORT_AMENITY_CATEGORIES:
            if cat in cat_counts.index:
                logger.info(f"  {cat}: {cat_counts[cat]}")

    filtered = filter_by_districts(infra_pois, district_polygons, only_districts=only_districts) if len(infra_pois) > 0 else {}

    del pois_gdf, infra_pois
    gc.collect()

    for did in (only_districts or TARGET_DISTRICTS):
        gdf = filtered.get(did, None)
        if gdf is None or len(gdf) == 0:
            logger.info(f"\n[{did.upper()}] No infrastructure POIs in district")
            counts[did] = {}
            continue

        logger.info(f"\n[{did.upper()}] Infrastructure POIs in district: {len(gdf)}")

        cat_counts = {}
        t0 = time.time()
        batch = []

        for idx, row in gdf.iterrows():
            try:
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue

                centroid = geom.centroid if geom.geom_type != "Point" else geom
                lon, lat = centroid.x, centroid.y

                amenity = str(row.get("amenity", "")).lower()
                name = str(row.get("name", "")).strip()
                if not name or name == "nan":
                    name = f"OSM {amenity.title()} {int(row.get('id', 0))}"

                # Map amenity to a pseudo-facility_type
                facility_type_map = {
                    "school": "school",
                    "college": "college",
                    "university": "university",
                    "police": "police",
                    "fuel": "fuel_station",
                    "bus_station": "bus_station",
                    "pharmacy": "pharmacy",
                    "blood_bank": "blood_bank",
                    "fire_station": "fire_station",
                    "shelter": "shelter",
                }
                facility_type = facility_type_map.get(amenity, amenity)

                osm_id_val = int(row.get("id", 0))
                facility_id = f"osm_infra_{did}_{osm_id_val}"

                facility = MedicalFacility(
                    id=facility_id,
                    district_id=did,
                    name=name,
                    lat=lat,
                    lon=lon,
                    facility_type=facility_type,
                    osm_id=osm_id_val,
                    provenance=Provenance.REAL,
                )
                batch.append(facility)
                cat_counts[amenity] = cat_counts.get(amenity, 0) + 1
            except Exception as e:
                continue

        if batch:
            repo.upsert_medical_facilities(batch)

        elapsed = time.time() - t0
        counts[did] = cat_counts
        logger.info(f"  [{did}] ✓ {len(batch)} infrastructure POIs ({elapsed:.1f}s)")

    total_elapsed = time.time() - total_start
    total_infra = sum(sum(c.values()) for c in counts.values())
    logger.info(f"\nTotal infrastructure POIs: {total_infra} ({total_elapsed:.1f}s)")

    del filtered
    gc.collect()

    return counts


def ingest_bridges(
    district_polygons: dict[str, object],
    repo: PostgresRepository,
    only_districts: list[str] = None,
) -> dict[str, int]:
    """
    Ingest bridge-tagged roads from PBF.

    Bridges are stored as Road records with is_bridge=True.
    The road network is re-parsed from PBF but only bridge-tagged features
    are inserted. This ensures bridges are properly captured even if the
    roads ingestion skipped them.

    Returns:
        dict mapping district_id -> count of bridges ingested
    """
    logger.info("=" * 60)
    logger.info("INGESTING BRIDGES FROM OSM PBF")
    logger.info("=" * 60)

    counts = {}
    total_start = time.time()

    # Parse road network from PBF
    roads_gdf = parse_pbf_category("bridges")

    # Filter to bridge-tagged roads only
    if "bridge" in roads_gdf.columns:
        bridge_roads = roads_gdf[roads_gdf["bridge"] == "yes"].copy()
    else:
        bridge_roads = roads_gdf.iloc[:0]

    logger.info(f"Total bridge-tagged roads in PBF: {len(bridge_roads)}")

    filtered = filter_by_districts(bridge_roads, district_polygons, only_districts=only_districts) if len(bridge_roads) > 0 else {}

    del roads_gdf, bridge_roads
    gc.collect()

    for did in (only_districts or TARGET_DISTRICTS):
        gdf = filtered.get(did, None)
        if gdf is None or len(gdf) == 0:
            logger.info(f"\n[{did.upper()}] No bridges in district")
            counts[did] = 0
            continue

        logger.info(f"\n[{did.upper()}] Bridges in district: {len(gdf)}")

        t0 = time.time()
        batch = []
        ingested = 0

        for idx, row in gdf.iterrows():
            try:
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue

                if geom.geom_type == "MultiLineString":
                    lines = list(geom.geoms)
                    longest = max(lines, key=lambda l: l.length)
                    coords = list(longest.coords)
                elif geom.geom_type == "LineString":
                    coords = list(geom.coords)
                else:
                    continue

                if len(coords) < 2:
                    continue

                geometry_coords = [(c[0], c[1]) for c in coords]
                tags = geojson_tags(row)

                osm_id_val = int(row.get("id", 0))
                road_id = f"osm_{did}_{osm_id_val}"

                road = Road(
                    id=road_id,
                    district_id=did,
                    name=str(row.get("name", "")) or None,
                    highway_type=str(row.get("highway", "unclassified")),
                    osm_id=osm_id_val,
                    geometry_coords=geometry_coords,
                    flood_affected=False,
                    provenance=Provenance.REAL,
                    tags=tags,
                    is_bridge=True,
                )
                batch.append(road)

                if len(batch) >= BATCH_SIZE:
                    repo.upsert_roads(batch)
                    ingested += len(batch)
                    batch = []
            except Exception as e:
                continue

        if batch:
            repo.upsert_roads(batch)
            ingested += len(batch)

        elapsed = time.time() - t0
        counts[did] = ingested
        logger.info(f"  [{did}] ✓ {ingested} bridges ingested ({elapsed:.1f}s)")

    total_elapsed = time.time() - total_start
    logger.info(f"\nTotal bridges ingested: {sum(counts.values())} ({total_elapsed:.1f}s)")

    del filtered
    gc.collect()

    return counts


def augment_settlements(
    district_polygons: dict[str, object],
    repo: PostgresRepository,
    only_districts: list[str] = None,
) -> dict[str, int]:
    """
    Check if the PBF contains additional settlement/place data
    that could supplement existing curated settlements.

    Does NOT replace existing records — only adds genuinely new ones.
    """
    logger.info("=" * 60)
    logger.info("SETTLEMENT AUGMENTATION CHECK")
    logger.info("=" * 60)

    # Parse only POIs from PBF
    pois_gdf = parse_pbf_category("settlements")

    # Look for place nodes in POIs (towns, villages, hamlets)
    if "place" not in pois_gdf.columns:
        logger.info("  No 'place' column in POIs — skipping settlement augmentation")
        del pois_gdf
        gc.collect()
        return {}

    place_values = {"city", "town", "village", "hamlet", "suburb", "neighbourhood"}
    places_gdf = pois_gdf[pois_gdf["place"].isin(place_values)].copy()
    logger.info(f"  Total place nodes in PBF: {len(places_gdf)}")

    if len(places_gdf) == 0:
        del pois_gdf, places_gdf
        gc.collect()
        return {}

    filtered = filter_by_districts(places_gdf, district_polygons, only_districts=only_districts)

    del pois_gdf, places_gdf
    gc.collect()

    counts = {}
    for did in (only_districts or TARGET_DISTRICTS):
        gdf = filtered.get(did, None)
        if gdf is None or len(gdf) == 0:
            counts[did] = 0
            continue

        added = 0

        for idx, row in gdf.iterrows():
            try:
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue

                centroid = geom.centroid if geom.geom_type != "Point" else geom
                lon, lat = centroid.x, centroid.y
                name = str(row.get("name", "")).strip()
                place_type = str(row.get("place", "")).strip()

                if not name or name == "nan":
                    continue

                # Generate deterministic ID
                slug = name.lower().replace(" ", "_").replace("-", "_")
                settlement_id = f"osm_{did}_{slug}"

                # Check if settlement already exists
                existing = repo.get_settlement(settlement_id)
                if existing:
                    continue

                settlement = Settlement(
                    id=settlement_id,
                    name=name,
                    district_id=did,
                    lat=lat,
                    lon=lon,
                    aliases=[],
                    metadata={
                        "source": "osm_pbf",
                        "place_type": place_type,
                        "osm_id": int(row.get("id", 0)),
                        "provenance": "REAL",
                    },
                )
                repo.upsert_settlement(settlement)
                added += 1
            except Exception as e:
                continue

        counts[did] = added
        logger.info(f"  [{did}] {added} new settlements added from PBF")

    total = sum(counts.values())
    logger.info(f"  Total new settlements: {total}")

    del filtered
    gc.collect()

    return counts


# ---------------------------------------------------------------------------
# Database summary / reporting
# ---------------------------------------------------------------------------

def report_db_counts(repo: PostgresRepository):
    """Print current database row counts for the target districts."""
    with repo._engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                (SELECT count(*) FROM districts WHERE id IN ('sivasagar','jorhat','charaideo','golaghat')) as districts,
                (SELECT count(*) FROM settlements WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as settlements,
                (SELECT count(*) FROM buildings WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as buildings,
                (SELECT count(*) FROM roads WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as roads,
                (SELECT count(*) FROM medical_facilities WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as medical,
                (SELECT count(*) FROM flood_snapshots WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as flood_snapshots,
                (SELECT count(*) FROM roads WHERE is_bridge = true AND district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as bridges,
                (SELECT count(*) FROM buildings WHERE provenance = 'REAL' AND district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as real_buildings,
                (SELECT count(*) FROM roads WHERE provenance = 'REAL' AND district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as real_roads,
                (SELECT count(*) FROM medical_facilities WHERE provenance = 'REAL' AND district_id IN ('sivasagar','jorhat','charaideo','golaghat')) as real_medical
        """))
        row = result.fetchone()

        logger.info("Database Row Counts (4 districts):")
        logger.info(f"  Districts:             {row[0]}")
        logger.info(f"  Settlements:           {row[1]}")
        logger.info(f"  Buildings:             {row[2]}")
        logger.info(f"  Roads:                 {row[3]}")
        logger.info(f"  Medical facilities:    {row[4]}")
        logger.info(f"  Flood snapshots:       {row[5]}")
        logger.info(f"  Bridges (is_bridge):   {row[6]}")
        logger.info(f"  Real buildings:        {row[7]}")
        logger.info(f"  Real roads:            {row[8]}")
        logger.info(f"  Real medical:          {row[9]}")

    # Per-district breakdown
    with repo._engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                d.district_id,
                COALESCE(b.buildings, 0) as buildings,
                COALESCE(r.roads, 0) as roads,
                COALESCE(rb.bridges, 0) as bridges,
                COALESCE(m.medical, 0) as medical
            FROM
                (SELECT 'sivasagar' as district_id UNION ALL SELECT 'jorhat' UNION ALL SELECT 'charaideo' UNION ALL SELECT 'golaghat') d
                LEFT JOIN (SELECT district_id, count(*) as buildings FROM buildings WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat') GROUP BY district_id) b ON b.district_id = d.district_id
                LEFT JOIN (SELECT district_id, count(*) as roads FROM roads WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat') GROUP BY district_id) r ON r.district_id = d.district_id
                LEFT JOIN (SELECT district_id, count(*) as bridges FROM roads WHERE is_bridge = true AND district_id IN ('sivasagar','jorhat','charaideo','golaghat') GROUP BY district_id) rb ON rb.district_id = d.district_id
                LEFT JOIN (SELECT district_id, count(*) as medical FROM medical_facilities WHERE district_id IN ('sivasagar','jorhat','charaideo','golaghat') GROUP BY district_id) m ON m.district_id = d.district_id
            ORDER BY d.district_id
        """))
        rows = result.fetchall()

        logger.info("")
        logger.info("| District    | Buildings | Roads  | Bridges | Medical |")
        logger.info("|-------------|----------:|-------:|--------:|--------:|")
        for r in rows:
            did = r[0] or 'unknown'
            buildings = r[1] or 0
            roads = r[2] or 0
            bridges = r[3] or 0
            medical = r[4] or 0
            logger.info(f"| {did:11s} | {buildings:9d} | {roads:6d} | {bridges:7d} | {medical:7d} |")


# ---------------------------------------------------------------------------
# Main ingestion orchestrator
# ---------------------------------------------------------------------------

def run_osm_pbf_ingestion(categories: list[str] = None, district_ids: list[str] = None):
    """
    Run OSM PBF ingestion pipeline.

    Args:
        categories: list of category names to ingest. If None, runs all.
        district_ids: list of district IDs to process. If None, processes all TARGET_DISTRICTS.
    """
    start_time = time.time()

    if categories is None:
        categories = ALL_CATEGORIES

    # Determine which districts to process
    active_districts = district_ids if district_ids else TARGET_DISTRICTS

    logger.info("=" * 70)
    logger.info("RELIEFOS PHASE 5B.1 — RESUMABLE OSM PBF INGESTION")
    logger.info("=" * 70)
    logger.info(f"Started at: {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"PBF file: {PBF_PATH}")
    logger.info(f"Target districts: {', '.join(active_districts)}")
    logger.info(f"Categories to process: {', '.join(categories)}")
    logger.info("")

    # Verify PBF exists
    if not os.path.exists(PBF_PATH):
        logger.error(f"PBF file not found: {PBF_PATH}")
        sys.exit(1)

    file_size_mb = os.path.getsize(PBF_PATH) / (1024 * 1024)
    logger.info(f"PBF file size: {file_size_mb:.1f} MB")

    # Get repository
    repo = get_repo()

    # Step 0: Verify existing counts (NEVER destructive)
    logger.info("\n" + "=" * 70)
    logger.info("STEP 0: VERIFY EXISTING DATABASE STATE (READ-ONLY)")
    logger.info("=" * 70)
    report_db_counts(repo)

    # Step 1: Load district polygons
    logger.info("\n" + "=" * 70)
    logger.info("STEP 1: LOAD DISTRICT POLYGONS")
    logger.info("=" * 70)
    district_polygons = load_district_polygons(repo)

    if len(district_polygons) < len(active_districts):
        missing = set(active_districts) - set(district_polygons.keys())
        logger.warning(f"Missing district polygons: {missing}")
        logger.warning("Ingestion will proceed but spatial filtering may be incomplete")

    # --- Execute requested categories ---

    if "buildings" in categories:
        logger.info("\n" + "=" * 70)
        logger.info("STEP: INGEST BUILDINGS")
        logger.info("=" * 70)
        ingest_buildings(district_polygons, repo, only_districts=active_districts)
        logger.info("\n--- Post-buildings DB state ---")
        report_db_counts(repo)

    if "roads" in categories:
        logger.info("\n" + "=" * 70)
        logger.info("STEP: INGEST ROADS")
        logger.info("=" * 70)
        ingest_roads(district_polygons, repo, only_districts=active_districts)
        logger.info("\n--- Post-roads DB state ---")
        report_db_counts(repo)

    if "bridges" in categories:
        logger.info("\n" + "=" * 70)
        logger.info("STEP: INGEST BRIDGES")
        logger.info("=" * 70)
        ingest_bridges(district_polygons, repo, only_districts=active_districts)
        logger.info("\n--- Post-bridges DB state ---")
        report_db_counts(repo)

    if "medical" in categories:
        logger.info("\n" + "=" * 70)
        logger.info("STEP: INGEST MEDICAL FACILITIES")
        logger.info("=" * 70)
        ingest_medical(district_polygons, repo, only_districts=active_districts)
        logger.info("\n--- Post-medical DB state ---")
        report_db_counts(repo)

    if "infrastructure" in categories:
        logger.info("\n" + "=" * 70)
        logger.info("STEP: INGEST OTHER INFRASTRUCTURE")
        logger.info("=" * 70)
        ingest_infrastructure(district_polygons, repo, only_districts=active_districts)
        logger.info("\n--- Post-infrastructure DB state ---")
        report_db_counts(repo)

    if "settlements" in categories:
        logger.info("\n" + "=" * 70)
        logger.info("STEP: SETTLEMENT AUGMENTATION")
        logger.info("=" * 70)
        augment_settlements(district_polygons, repo, only_districts=active_districts)
        logger.info("\n--- Post-settlements DB state ---")
        report_db_counts(repo)

    # Final summary
    total_time = time.time() - start_time

    logger.info("\n" + "=" * 70)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Total time: {total_time:.1f}s ({total_time/60:.1f}min)")
    logger.info(f"Categories processed: {', '.join(categories)}")

    logger.info("")
    report_db_counts(repo)

    logger.info("")
    logger.info("Provenance: All imported records marked as REAL / OpenStreetMap")
    logger.info("OSM Attribution: © OpenStreetMap contributors (ODbL 1.0)")

    return {
        "total_time": total_time,
        "categories": categories,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ReliefOS Phase 5B.1 — Resumable OSM PBF Ingestion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.ingest.osm_pbf                       # all categories, all districts
  python -m scripts.ingest.osm_pbf --only roads           # roads only
  python -m scripts.ingest.osm_pbf --only medical         # medical only
  python -m scripts.ingest.osm_pbf --only buildings       # buildings only
  python -m scripts.ingest.osm_pbf --only bridges         # bridges only
  python -m scripts.ingest.osm_pbf --only infrastructure  # other POIs
  python -m scripts.ingest.osm_pbf --only settlements     # settlement augmentation
  python -m scripts.ingest.osm_pbf --only roads --only medical  # multiple categories
  python -m scripts.ingest.osm_pbf --only buildings --district golaghat  # buildings for golaghat only
  python -m scripts.ingest.osm_pbf --only buildings --district golaghat --district charaideo
        """,
    )
    parser.add_argument(
        "--only",
        dest="categories",
        action="append",
        choices=ALL_CATEGORIES,
        help="Ingest only the specified category (can be repeated). "
             "If not specified, all categories are processed.",
    )
    parser.add_argument(
        "--district",
        dest="districts",
        action="append",
        choices=TARGET_DISTRICTS,
        help="Ingest only for the specified district (can be repeated). "
             "If not specified, all districts are processed.",
    )
    args = parser.parse_args()

    categories = args.categories if args.categories else None
    districts = args.districts if args.districts else None
    run_osm_pbf_ingestion(categories=categories, district_ids=districts)


if __name__ == "__main__":
    main()
