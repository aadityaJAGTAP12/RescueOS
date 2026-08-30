"""
Generalized Sentinel-1 SAR Flood-Mapping Pipeline

A reusable Google Earth Engine processing pipeline that generates
flood snapshots for ANY ReliefOS-supported district and date window.

Methodology:
- Sentinel-1 GRD, VH polarization, IW mode, descending orbit
- Pre-flood and post-event median composites
- Speckle reduction via focal_median
- Change detection (dB difference)
- Connected-component cleanup
- Vectorization and area filtering

SCIENTIFIC CAVEATS:
- Original Sivasagar parameters were not exhaustively optimized
  against ground truth and may need re-tuning for other terrain
  or noise conditions.
- -3 dB threshold is approximate; actual flood boundaries depend
  on local terrain, vegetation, and radar shadow effects.
- Binary flood mask (flooded / not-flooded), not flood depth.
- Connected-component and area filtering can remove genuine small
  inundation areas.
- Result is approximate/reconstructed, not ground-truth exact.

Usage:
    import ee
    ee.Initialize()

    from agent.gee.flood_pipeline import generate_flood_snapshot
    from agent.gee.config import SIVASAGAR_REGRESSION_CONFIG

    # Sivasagar regression
    config = SIVASAGAR_REGRESSION_CONFIG
    aoi = ee.Geometry.Rectangle([94.55, 26.85, 95.05, 27.15])
    result = generate_flood_snapshot(aoi, config)

    # Different district
    from agent.gee.config import FloodPipelineConfig
    custom_config = FloodPipelineConfig(
        district_id="jorhat",
        pre_start="2026-06-25",
        pre_end="2026-07-05",
        event_start="2026-08-08",
        event_end="2026-08-13",
    )
    result = generate_flood_snapshot(jorhat_geometry, custom_config)
"""

from __future__ import annotations

from typing import Optional

try:
    import ee
    _EE_AVAILABLE = True
except ImportError:
    ee = None
    _EE_AVAILABLE = False

from agent.gee.config import FloodPipelineConfig, DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# Sentinel-1 collection helpers
# ---------------------------------------------------------------------------

def build_s1_collection(
    aoi,
    start_date: str,
    end_date: str,
    config: FloodPipelineConfig = DEFAULT_CONFIG,
):
    """
    Build a filtered Sentinel-1 GRD collection.

    Filters: IW mode, VH polarization, descending orbit,
    date range, clipped to AOI.

    Args:
        aoi: ee.Geometry — area of interest
        start_date: start date string (YYYY-MM-DD)
        end_date: end date string (YYYY-MM-DD)
        config: FloodPipelineConfig with collection parameters

    Returns:
        ee.ImageCollection filtered and clipped to AOI
    """
    if not _EE_AVAILABLE:
        raise ImportError(
            "Google Earth Engine (ee) is required. "
            "Install with: pip install earthengine-api"
        )

    collection = (
        ee.ImageCollection(config.collection)
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.eq("instrumentMode", config.instrument_mode))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", config.polarization))
        .filter(ee.Filter.eq("orbitProperties_pass", config.orbit_pass))
    )

    return collection


# ---------------------------------------------------------------------------
# Compositing and speckle reduction
# ---------------------------------------------------------------------------

def create_composite(
    collection,
    aoi,
    config: FloodPipelineConfig = DEFAULT_CONFIG,
):
    """
    Create a median composite and apply speckle reduction.

    Steps:
        1. Median compositing
        2. Clip to AOI
        3. Focal median speckle reduction

    Args:
        collection: ee.ImageCollection
        aoi: ee.Geometry
        config: FloodPipelineConfig

    Returns:
        ee.Image — speckle-reduced, clipped composite
    """
    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    composite = collection.median().clip(aoi)

    # Speckle reduction: focal median
    smoothed = composite.focal_median(
        radius=config.speckle_radius_m,
        units="meters",
    )

    return smoothed


# ---------------------------------------------------------------------------
# Change detection and flood masking
# ---------------------------------------------------------------------------

def detect_flood(
    pre_smoothed,
    post_smoothed,
    config: FloodPipelineConfig = DEFAULT_CONFIG,
):
    """
    Compute change detection and apply flood threshold + connected-component cleanup.

    Steps:
        1. diff = post_smooth - pre_smooth (in dB)
        2. Flood mask: diff < threshold_db
        3. Self-mask
        4. Connected pixel count filter
        5. Self-mask again

    Args:
        pre_smoothed: ee.Image — pre-flood smoothed composite
        post_smoothed: ee.Image — post-event smoothed composite
        config: FloodPipelineConfig

    Returns:
        ee.Image — binary flood mask (1 where flooded)
    """
    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    # Change detection
    diff = post_smoothed.subtract(pre_smoothed)

    # Flood threshold
    flood_mask_raw = diff.lt(config.threshold_db)

    # Self-mask (only keep pixels below threshold)
    flood_mask = flood_mask_raw.selfMask()

    # Connected-component cleanup
    neighborhood = config.connected_pixel_neighborhood
    min_count = config.min_connected_pixels
    flood_mask_clean = (
        flood_mask
        .connectedPixelCount(neighborhood)
        .gte(min_count)
        .selfMask()
    )

    return flood_mask_clean


# ---------------------------------------------------------------------------
# Vectorization and area filter
# ---------------------------------------------------------------------------

def vectorize_flood(
    flood_mask,
    aoi,
    config: FloodPipelineConfig = DEFAULT_CONFIG,
):
    """
    Vectorize the raster flood mask and apply area filtering.

    Steps:
        1. reduceToVectors (polygon)
        2. Compute area in m²
        3. Filter by area_threshold_m2

    Args:
        flood_mask: ee.Image — binary flood mask
        aoi: ee.Geometry — area of interest
        config: FloodPipelineConfig

    Returns:
        ee.FeatureCollection of flood polygons (area-filtered)
    """
    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    # Vectorize
    vectors = flood_mask.reduceToVectors(
        scale=config.vector_scale,
        geometryType=config.vector_geometry_type,
        labelProperty="flooded",
        maxPixels=config.vector_max_pixels,
        geometry=aoi,
    )

    # Area filter: compute area in m²
    vectors_filtered = vectors.map(lambda feature: feature.set(
        "area_m2",
        feature.geometry().area(maxError=1),
    ))

    # Apply area threshold
    vectors_filtered = vectors_filtered.filter(
        ee.Filter.gt("area_m2", config.area_threshold_m2)
    )

    return vectors_filtered


# ---------------------------------------------------------------------------
# Main pipeline: generate_flood_snapshot
# ---------------------------------------------------------------------------

def generate_flood_snapshot(
    aoi,
    config: FloodPipelineConfig = None,
    pre_start: Optional[str] = None,
    pre_end: Optional[str] = None,
    event_start: Optional[str] = None,
    event_end: Optional[str] = None,
    threshold_db: Optional[float] = None,
    speckle_radius_m: Optional[float] = None,
    min_connected_pixels: Optional[int] = None,
    area_threshold_m2: Optional[float] = None,
) -> dict:
    """
    Generate a flood snapshot for a given district geometry and date window.

    This is the main entry point. It orchestrates the full pipeline:
    1. Build Sentinel-1 collection (pre and post)
    2. Create composites with speckle reduction
    3. Detect flood via change detection
    4. Vectorize and filter by area
    5. Return the feature collection + metadata

    Args:
        aoi: ee.Geometry — district or AOI geometry
        config: FloodPipelineConfig (optional, overrides defaults)
        pre_start: pre-flood start date (overrides config)
        pre_end: pre-flood end date (overrides config)
        event_start: event start date (overrides config)
        event_end: event end date (overrides config)
        threshold_db: flood threshold (overrides config)
        speckle_radius_m: speckle reduction radius (overrides config)
        min_connected_pixels: minimum connected pixels (overrides config)
        area_threshold_m2: minimum polygon area in m² (overrides config)

    Returns:
        dict with keys:
            - flood_polygons: ee.FeatureCollection
            - polygon_count: int (computed server-side)
            - metadata: dict with full processing metadata
            - config_used: FloodPipelineConfig snapshot
    """
    if config is None:
        config = FloodPipelineConfig()
    else:
        # Clone config to avoid mutating the original
        config = FloodPipelineConfig(
            collection=config.collection,
            polarization=config.polarization,
            instrument_mode=config.instrument_mode,
            orbit_pass=config.orbit_pass,
            pre_start=config.pre_start,
            pre_end=config.pre_end,
            event_start=config.event_start,
            event_end=config.event_end,
            speckle_radius_m=config.speckle_radius_m,
            threshold_db=config.threshold_db,
            connected_pixel_neighborhood=config.connected_pixel_neighborhood,
            min_connected_pixels=config.min_connected_pixels,
            vector_scale=config.vector_scale,
            vector_geometry_type=config.vector_geometry_type,
            vector_max_pixels=config.vector_max_pixels,
            area_threshold_m2=config.area_threshold_m2,
            district_id=config.district_id,
            methodology_version=config.methodology_version,
            provenance=config.provenance,
            confidence=config.confidence,
            export_prefix=config.export_prefix,
        )

    # Apply parameter overrides
    if pre_start is not None:
        config.pre_start = pre_start
    if pre_end is not None:
        config.pre_end = pre_end
    if event_start is not None:
        config.event_start = event_start
    if event_end is not None:
        config.event_end = event_end
    if threshold_db is not None:
        config.threshold_db = threshold_db
    if speckle_radius_m is not None:
        config.speckle_radius_m = speckle_radius_m
    if min_connected_pixels is not None:
        config.min_connected_pixels = min_connected_pixels
    if area_threshold_m2 is not None:
        config.area_threshold_m2 = area_threshold_m2

    if not _EE_AVAILABLE:
        raise ImportError(
            "Google Earth Engine (ee) is required. "
            "Install with: pip install earthengine-api"
        )

    # --- Step 1: Build collections ---
    pre_collection = build_s1_collection(aoi, config.pre_start, config.pre_end, config)
    post_collection = build_s1_collection(aoi, config.event_start, config.event_end, config)

    # --- Step 2: Create composites with speckle reduction ---
    pre_smoothed = create_composite(pre_collection, aoi, config)
    post_smoothed = create_composite(post_collection, aoi, config)

    # --- Step 3: Detect flood ---
    flood_mask = detect_flood(pre_smoothed, post_smoothed, config)

    # --- Step 4: Vectorize and filter ---
    flood_polygons = vectorize_flood(flood_mask, aoi, config)

    # --- Step 5: Count polygons (server-side) ---
    polygon_count = flood_polygons.size()

    # --- Step 6: Build metadata ---
    metadata = config.get_metadata()
    metadata["status"] = "computed"
    metadata["note"] = (
        "Approximate reconstructed flood extent from Sentinel-1 SAR. "
        "Not ground-truth exact. May include false positives from "
        "radar shadow, terrain effects, or vegetation moisture changes."
    )

    return {
        "flood_polygons": flood_polygons,
        "polygon_count": polygon_count,
        "metadata": metadata,
        "config_used": config,
    }


# ---------------------------------------------------------------------------
# Raster visualization helpers
# ---------------------------------------------------------------------------

def get_flood_vis_params(config: FloodPipelineConfig = DEFAULT_CONFIG) -> dict:
    """
    Get visualization parameters for flood mask overlay.

    Returns dict suitable for ee.Image.visualize().
    """
    return {
        "bands": [config.polarization],
        "min": -25,
        "max": 0,
        "palette": ["0000ff", "00ff00", "ffff00", "ff0000"],
    }


def get_change_vis_params() -> dict:
    """
    Get visualization parameters for the dB difference raster.

    Returns dict suitable for ee.Image.visualize().
    """
    return {
        "min": -10,
        "max": 10,
        "palette": ["0000ff", "ffffff", "ff0000"],
    }


def inspect_point(
    flood_mask,
    flood_polygons,
    point,
):
    """
    Inspect flood status at a specific point.

    Args:
        flood_mask: ee.Image — binary flood mask
        flood_polygons: ee.FeatureCollection — vectorized flood polygons
        point: ee.Geometry.Point — location to inspect

    Returns:
        dict with flood status at the point
    """
    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    # Sample raster value
    raster_value = flood_mask.sample(point, scale=10).first()

    # Count nearby polygons
    nearby_polygons = flood_polygons.filterBounds(point.buffer(100))

    return {
        "raster_value": raster_value,
        "nearby_polygon_count": nearby_polygons.size(),
    }
