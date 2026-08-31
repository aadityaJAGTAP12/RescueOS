"""
Golaghat July 2026 Flood Snapshot — Run Configuration

Prepares the Sentinel-1 flood-mapping pipeline for Golaghat district
using the same generalized methodology validated on Sivasagar, Jorhat,
and Charaideo.

==================================================
SENTINEL-1 CONSTELLATION STATUS (July 2026)
==================================================

Same as all Upper Assam districts:

| Satellite | Status in July 2026 | Notes |
|-----------|---------------------|-------|
| Sentinel-1A | ENDED 29 June 2026 | 12 years of service. Decommissioned. |
| Sentinel-1C | OPERATIONAL | Launched 5 Dec 2024. Since mid-Jan 2025. |
| Sentinel-1D | OPERATIONAL | Launched 4 Nov 2025. Data from 17 Apr 2026. |

New constellation (post-29 June): S1C + S1D only.
~6-day revisit with 1-day shift vs. former S1A/S1B pattern.

For Golaghat (Lower-Middle Assam, ~25.8–26.9°N, 93.3–94.2°E):
- S1C and S1D both have DESCENDING passes over this region
- With 2 satellites, ~6-day revisit
- Expected: 2–4 acquisitions over any 10-day window

==================================================
EVENT CONTEXT
==================================================

Upper Assam flooding intensified from ~19 July 2026.
Golaghat district is in Lower-Middle Assam, downstream of the
Brahmaputra flood wave. Flooding may arrive later than in
Jorhat/Charaideo/Sivasagar.

These are event-timing/sanity-check context, NOT ground-truth polygon
boundaries.

==================================================
PREFERRED WINDOWS (subject to S1 data availability)
==================================================

Pre-event baseline:  2026-06-25 → 2026-07-06
  (Just before S1A ended; should have S1A + S1C + S1D acquisitions)

Event window:        2026-07-22 → 2026-08-10
  (Wider than Jorhat/Charaideo to account for later flood propagation
   into Golaghat's river systems — Brahmaputra flows through Golaghat)

Alternative event:   2026-07-29 → 2026-08-10
  (If S1 imagery is sparse in the 22–29 July window)

These dates MUST be validated against actual S1 acquisitions before use.

==================================================
PROCESSING PARAMETERS
==================================================

Reproduces proven Sivasagar methodology (unchanged):
- polarization = VH
- instrumentMode = IW
- orbit = DESCENDING
- composite = median()
- speckle_radius = 50m focal_median
- threshold_db = -3
- connectedPixelCount = 100 neighborhood, gte 60
- reduceToVectors: scale=10m, polygon, maxPixels=1e9
- area filter: > 5000 m²

==================================================
SCIENTIFIC CAVEATS
==================================================

- -3 dB threshold was not ground-truth optimized
- Binary flood mask, not flood depth
- Connected-component and area filtering can remove genuine small inundation
- Result is approximate/reconstructed, not ground-truth exact
- May include false positives from radar shadow, terrain effects,
  or vegetation moisture changes
- Parameters may need re-tuning for Golaghat's specific terrain/noise
"""

from __future__ import annotations

import os
import sys
from typing import Optional

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.gee.config import FloodPipelineConfig


# ---------------------------------------------------------------------------
# Golaghat run configuration
# ---------------------------------------------------------------------------

GOLAGHAT_CONFIG = FloodPipelineConfig(
    district_id="golaghat",

    # --- Date windows (VALIDATE against actual S1 acquisitions) ---
    # Pre-event baseline: 2026-06-25 → 2026-07-06
    # Must contain at least one S1 DESCENDING+IW+VH acquisition over Golaghat
    pre_start="2026-06-25",
    pre_end="2026-07-06",

    # Event window: 2026-07-22 → 2026-08-10
    # Wider than Jorhat/Charaideo to account for later flood propagation
    # into Golaghat's river systems
    event_start="2026-07-22",
    event_end="2026-08-10",

    # --- Processing parameters (proven Sivasagar methodology) ---
    polarization="VH",
    instrument_mode="IW",
    orbit_pass="DESCENDING",
    speckle_radius_m=50.0,
    threshold_db=-3.0,
    connected_pixel_neighborhood=100,
    min_connected_pixels=60,
    vector_scale=10.0,
    area_threshold_m2=5000.0,

    # --- Metadata ---
    methodology_version="1.0",
    provenance="REAL",
    confidence=0.8,
)


# ---------------------------------------------------------------------------
# Sentinel-1 constellation reference
# ---------------------------------------------------------------------------

SENTINEL1_CONSTELLATION = {
    "S1A": {
        "status": "DECOMMISSIONED",
        "end_date": "2026-06-29",
        "note": "12 years of service. Last acquisitions in late June 2026.",
    },
    "S1B": {
        "status": "DECOMMISSIONED",
        "end_date": "2021-12-23",
        "note": "Failed December 2016. Decommissioned.",
    },
    "S1C": {
        "status": "OPERATIONAL",
        "launch_date": "2024-12-05",
        "operational_from": "2025-01-mid",
        "note": "Launched on Vega-C. Operational since mid-January 2025.",
    },
    "S1D": {
        "status": "OPERATIONAL",
        "launch_date": "2025-11-04",
        "data_from": "2026-04-17",
        "fully_operational": "2026-05",
        "note": "Launched on Ariane 6. Data available from 17 April 2026.",
    },
}


# ---------------------------------------------------------------------------
# Alternative date windows (if primary windows lack sufficient data)
# ---------------------------------------------------------------------------

ALTERNATIVE_WINDOWS = {
    "wider_pre": {
        "pre_start": "2026-06-10",
        "pre_end": "2026-07-06",
        "reason": "Wider pre-event window to increase chance of S1 acquisition",
    },
    "tighter_event": {
        "event_start": "2026-07-29",
        "event_end": "2026-08-10",
        "reason": "Late-July event window if flooding peaked later in Golaghat",
    },
    "extended_event": {
        "event_start": "2026-07-15",
        "event_end": "2026-08-15",
        "reason": "Extended event window if S1 coverage is sparse",
    },
}


# ---------------------------------------------------------------------------
# GEE discovery script (to be run in authenticated GEE environment)
# ---------------------------------------------------------------------------

GEE_DISCOVERY_SCRIPT = '''
// ============================================================
// SENTINEL-1 AVAILABILITY DISCOVERY — GOLAGHAT, JULY 2026
// ============================================================
// Run this script in Google Earth Engine Code Editor or
// Python API to find actual Sentinel-1 acquisitions.
//
// Purpose: Determine which S1 images are available before
// selecting final date windows for flood mapping.
// ============================================================

// --- Step 1: Define Golaghat AOI ---
// Option A: Use the actual district geometry (preferred)
//   Upload data/golaghat_gee.geojson to GEE Assets
//   var golaghat = ee.FeatureCollection('projects/YOUR_PROJECT/assets/golaghat_gee');
//   var aoi = golaghat.geometry();

// Option B: Bounding box approximation (for discovery only)
var aoi = ee.Geometry.Rectangle([93.29, 25.81, 94.18, 26.93]);

// --- Step 2: Define search windows ---
var preStart = '2026-06-25';
var preEnd   = '2026-07-06';
var evtStart = '2026-07-22';
var evtEnd   = '2026-08-10';

// --- Step 3: Query Sentinel-1 GRD collection ---
var s1 = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filterBounds(aoi)
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
  .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'));

// --- Step 4: List available images in each window ---
var preImages = s1.filterDate(preStart, preEnd);
var evtImages = s1.filterDate(evtStart, evtEnd);

print('=== PRE-EVENT WINDOW ===');
print('Date range:', preStart, '->', preEnd);
print('Image count:', preImages.size());
print('Images:', preImages);

preImages.evaluate(function(result) {
  if (result && result.features) {
    result.features.forEach(function(f) {
      var p = f.properties;
      print('  Date:', p.system:time_start,
            'Satellite:', p.platform_number,
            'Orbit:', p.relativeOrbitNumber);
    });
  }
});

print('=== EVENT WINDOW ===');
print('Date range:', evtStart, '->', evtEnd);
print('Image count:', evtImages.size());
print('Images:', evtImages);

evtImages.evaluate(function(result) {
  if (result && result.features) {
    result.features.forEach(function(f) {
      var p = f.properties;
      print('  Date:', p.system:time_start,
            'Satellite:', p.platform_number,
            'Orbit:', p.relativeOrbitNumber);
    });
  }
});

// --- Step 5: Also check wider windows ---
var widePre = s1.filterDate('2026-06-10', '2026-07-06');
var wideEvt = s1.filterDate('2026-07-15', '2026-08-15');

print('=== WIDER PRE (Jun 10 -> Jul 6) ===');
print('Count:', widePre.size());

print('=== WIDER EVENT (Jul 15 -> Aug 15) ===');
print('Count:', wideEvt.size());

// --- Step 6: Visualize first available image ---
var firstPre = preImages.first();
var firstEvt = evtImages.first();

if (firstPre) {
  Map.centerObject(aoi, 9);
  Map.addLayer(firstPre, {bands: ['VH'], min: -25, max: 0}, 'Pre-event VH');
}

if (firstEvt) {
  Map.addLayer(firstEvt, {bands: ['VH'], min: -25, max: 0}, 'Event VH');
}

Map.addLayer(aoi, {color: 'yellow'}, 'Golaghat AOI');
'''


# ---------------------------------------------------------------------------
# GEE execution script (after discovery confirms dates)
# ---------------------------------------------------------------------------

GEE_EXECUTION_SCRIPT = '''
// ============================================================
// GOLAGHAT FLOOD SNAPSHOT — EXECUTION SCRIPT
// ============================================================
// Run AFTER discovery confirms S1 availability.
// Replace DATE placeholders with actual dates.
// ============================================================

// --- Step 1: District geometry ---
// Upload data/golaghat_gee.geojson as GEE asset
var golaghat_fc = ee.FeatureCollection('projects/YOUR_PROJECT/assets/golaghat_gee');
var aoi = golaghat_fc.geometry();

// --- Step 2: Date windows ---
// REPLACE with actual dates confirmed by discovery script
var preStart = '2026-06-XX';  // <- CONFIRMED DATE
var preEnd   = '2026-07-XX';  // <- CONFIRMED DATE
var evtStart = '2026-07-XX';  // <- CONFIRMED DATE
var evtEnd   = '2026-08-XX';  // <- CONFIRMED DATE

// --- Step 3: Build Sentinel-1 collections ---
var s1 = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filterBounds(aoi)
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
  .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'));

var preCollection = s1.filterDate(preStart, preEnd);
var evtCollection = s1.filterDate(evtStart, evtEnd);

print('Pre-event images:', preCollection.size());
print('Event images:', evtCollection.size());

// --- Step 4: Create composites with speckle reduction ---
var preSmoothed = preCollection.median().clip(aoi)
  .focal_median(50, 'meters');

var evtSmoothed = evtCollection.median().clip(aoi)
  .focal_median(50, 'meters');

// --- Step 5: Change detection ---
var diff = evtSmoothed.subtract(preSmoothed);
var floodMask = diff.lt(-3).selfMask();

// --- Step 6: Connected-component cleanup ---
var floodClean = floodMask
  .connectedPixelCount(100)
  .gte(60)
  .selfMask();

// --- Step 7: Vectorize ---
var floodPolygons = floodClean.reduceToVectors({
  scale: 10,
  geometryType: 'polygon',
  labelProperty: 'flooded',
  maxPixels: 1e9,
  geometry: aoi
});

// --- Step 8: Area filter ---
floodPolygons = floodPolygons.map(function(f) {
  return f.set('area_m2', f.geometry().area({maxError: 1}));
});
floodPolygons = floodPolygons.filter(ee.Filter.gt('area_m2', 5000));

// --- Step 9: Validation ---
print('=== RESULTS ===');
print('Polygon count:', floodPolygons.size());

var totalArea = floodPolygons.aggregate_sum('area_m2');
print('Total flooded area (m2):', totalArea);

// --- Step 10: Visualization ---
Map.centerObject(aoi, 9);
Map.addLayer(aoi, {color: 'yellow'}, 'Golaghat District');
Map.addLayer(preSmoothed, {bands: ['VH'], min: -25, max: 0}, 'Pre-event VH');
Map.addLayer(evtSmoothed, {bands: ['VH'], min: -25, max: 0}, 'Event VH');
Map.addLayer(diff, {min: -10, max: 10, palette: ['blue', 'white', 'red']}, 'dB Difference');
Map.addLayer(floodClean, {palette: ['red']}, 'Flood Mask (cleaned)');
Map.addLayer(floodPolygons, {color: 'red'}, 'Flood Polygons');

// --- Step 11: Export (uncomment after visual validation) ---
// Export.table.toDrive({
//   collection: floodPolygons,
//   description: 'golaghat_flood_' + evtStart + '_' + evtEnd,
//   folder: 'ReliefOS_Flood_Snapshots',
//   fileNamePrefix: 'golaghat_flood_' + evtStart + '_' + evtEnd,
//   fileFormat: 'GeoJSON',
//   maxFeatures: 1e10
// });
'''


# ---------------------------------------------------------------------------
# Validation procedure
# ---------------------------------------------------------------------------

VALIDATION_PROCEDURE = """
GOLAGHAT FLOOD SNAPSHOT — VALIDATION PROCEDURE
=================================================

Before running the flood pipeline, execute these checks:

A. SENTINEL-1 IMAGERY EXISTS
   -> Run the discovery script (GEE_DISCOVERY_SCRIPT)
   -> Verify: preImages.size() >= 1 AND evtImages.size() >= 1
   -> If zero images: expand date window using ALTERNATIVE_WINDOWS

B. PRE COMPOSITE RENDERS
   -> Map.addLayer(preSmoothed, {bands:['VH'], min:-25, max:0})
   -> Visual check: should show terrain features, not blank/garbage

C. EVENT COMPOSITE RENDERS
   -> Map.addLayer(evtSmoothed, {bands:['VH'], min:-25, max:0})
   -> Visual check: similar to pre-event but with visible water

D. DIFFERENCE IMAGE RENDERS
   -> Map.addLayer(diff, {min:-10, max:10, palette:['blue','white','red']})
   -> Blue = potential flood (backscatter decrease)

E. FLOOD MASK RENDERS
   -> Map.addLayer(floodClean, {palette:['red']})
   -> Should show coherent patches along rivers/floodplains
   -> NOT scattered random pixels (would indicate noise)

F. VECTOR RESULT IS GEOGRAPHICALLY PLAUSIBLE
   -> Flood polygons should align with:
     - Brahmaputra river and tributaries (Doyang, Dorika)
     - Low-lying areas in Golaghat district
     - Known flood-prone zones (Kaziranga area, tea estates)
   -> Should NOT appear in highland/mountainous areas

G. POLYGON COUNT IS FINITE/REASONABLE
   -> Expected range: 10–1000 polygons (rough estimate)
   -> Zero polygons: threshold too aggressive or no flooding
   -> >2000 polygons: threshold may be too lenient

H. TOTAL AREA IS PLAUSIBLE
   -> Golaghat district area: ~3,285 km²
   -> Flooded area should be < district area
   -> Reasonable range: 10–500 km² depending on severity

I. OUTPUT IS INSIDE GOLAGHAT DISTRICT GEOMETRY
   -> All polygon centroids should fall within the district boundary
   -> No polygons should extend significantly beyond the boundary

J. CROSS-CHECK WITH CONTEXT
   -> Upper Assam flooding intensified ~19 July 2026
   -> Golaghat is downstream; flooding may arrive later
   -> If NO flood detected: possible issues with:
     - Date window selection
     - Threshold too aggressive
     - S1 acquisition timing mismatch

IF VISUAL RESULT CLEARLY FAILS:
   -> Document the evidence (screenshot/note)
   -> Propose parameter adjustment for human approval
   -> Do NOT silently change parameters
"""


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_run_summary():
    """Print a summary of the Golaghat run configuration."""
    print("=" * 60)
    print("GOLAGHAT FLOOD SNAPSHOT — RUN CONFIGURATION")
    print("=" * 60)
    print()
    print("District: Golaghat, Assam, India")
    print(f"Export filename: {GOLAGHAT_CONFIG.generate_filename()}")
    print()
    print("Geometry source: PostGIS (export_district_geometry)")
    print(f"  District bounds: lon=[93.2876, 94.1774], lat=[25.8078, 26.9310]")
    print(f"  Vertices: 3,506")
    print()
    print("Date windows (VALIDATE AGAINST ACTUAL S1 DATA):")
    print(f"  Pre-event:  {GOLAGHAT_CONFIG.pre_start} -> {GOLAGHAT_CONFIG.pre_end}")
    print(f"  Event:      {GOLAGHAT_CONFIG.event_start} -> {GOLAGHAT_CONFIG.event_end}")
    print()
    print("Processing parameters:")
    print(f"  Collection:    {GOLAGHAT_CONFIG.collection}")
    print(f"  Polarization:  {GOLAGHAT_CONFIG.polarization}")
    print(f"  Instrument:    {GOLAGHAT_CONFIG.instrument_mode}")
    print(f"  Orbit:         {GOLAGHAT_CONFIG.orbit_pass}")
    print(f"  Threshold:     {GOLAGHAT_CONFIG.threshold_db} dB")
    print(f"  Speckle:       {GOLAGHAT_CONFIG.speckle_radius_m}m focal_median")
    print(f"  Connected:     {GOLAGHAT_CONFIG.connected_pixel_neighborhood} px neighborhood, gte {GOLAGHAT_CONFIG.min_connected_pixels}")
    print(f"  Vector scale:  {GOLAGHAT_CONFIG.vector_scale}m")
    print(f"  Area filter:   > {GOLAGHAT_CONFIG.area_threshold_m2} m²")
    print()
    print("Sentinel-1 constellation (July 2026):")
    print("  S1A: DECOMMISSIONED (ended 29 June 2026)")
    print("  S1C: OPERATIONAL (launched 5 Dec 2024)")
    print("  S1D: OPERATIONAL (launched 4 Nov 2025)")
    print("  Revisit: ~6 days (S1C + S1D)")
    print()
    print("Next steps:")
    print("  1. Upload data/golaghat_gee.geojson to GEE Assets")
    print("  2. Run discovery script in GEE to find actual S1 dates")
    print("  3. Update date windows if needed")
    print("  4. Execute flood pipeline")
    print("  5. Validate per VALIDATION_PROCEDURE")
    print("=" * 60)


if __name__ == "__main__":
    print_run_summary()
