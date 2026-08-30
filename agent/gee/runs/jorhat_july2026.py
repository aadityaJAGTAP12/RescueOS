"""
Jorhat July 2026 Flood Snapshot — Run Configuration

First validation run of the generalized Sentinel-1 flood-mapping pipeline
on a real district with real imagery.

==================================================
SENTINEL-1 CONSTELLATION STATUS (July 2026)
==================================================

Satellite status during the target period:

| Satellite | Status in July 2026 | Notes |
|-----------|---------------------|-------|
| Sentinel-1A | ENDED 29 June 2026 | 12 years of service. Decommissioned. |
| Sentinel-1C | OPERATIONAL | Launched 5 Dec 2024. Since mid-Jan 2025. |
| Sentinel-1D | OPERATIONAL | Launched 4 Nov 2025. Data from 17 Apr 2026. |

Orbital reconfiguration (May–June 2026):
- Before 9 June: S1A + S1C + S1D all operational (3-sat, ~1-day revisit for some tracks)
- 9–23 June: S1C suspended for orbital maneuver. S1A + S1D ensuring operations.
- 24 June: S1C resumes. S1D adopts S1A's observation scenario.
- 29 June: S1A operations terminated. New constellation: S1C + S1D only.
- New constellation: 6-day revisit with 1-day shift vs. former S1A/S1B pattern.

For Jorhat (Upper Assam, ~26.75°N, 94.2°E):
- S1C and S1D both have DESCENDING passes over this region
- With 2 satellites in the final configuration, ~6-day revisit
- Expected: 2–4 acquisitions over any 10-day window

==================================================
AVAILABILITY IN GEE
==================================================

The COPERNICUS/S1_GRD collection in GEE includes data from all Sentinel-1
satellites (S1A, S1B, S1C, S1D) that match the filtering criteria.
The collection is updated daily within ~2 days of acquisition.

CRITICAL: Do NOT assume specific acquisition dates.
Use the discovery script to find actual available dates.

==================================================
EVENT CONTEXT
==================================================

Upper Assam flooding intensified from ~19 July 2026.
Jorhat was among the worst-affected districts.
CWC-reported river levels elevated at Neamatighat station.
Central damage-assessment team visited the four districts.

These are event-timing/sanity-check context, NOT ground-truth polygon
boundaries.

==================================================
PREFERRED WINDOWS (subject to data availability)
==================================================

Pre-event baseline:  2026-06-25 → 2026-07-05
  (Just before S1A ended; should have S1A + S1C + S1D acquisitions)

Event window:        2026-07-18 → 2026-07-25
  (Core flood period based on reported onset ~19 July)

Alternative event:   2026-07-25 → 2026-08-05
  (If S1 imagery is sparse in the 18–25 window)

These dates MUST be validated against actual S1 acquisitions before use.

==================================================
PROCESSING PARAMETERS
==================================================

Reproduces proven Sivasagar methodology:
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
- Parameters may need re-tuning for Jorhat's specific terrain/noise
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.gee.config import FloodPipelineConfig


# ---------------------------------------------------------------------------
# Jorhat run configuration
# ---------------------------------------------------------------------------

JORHAT_CONFIG = FloodPipelineConfig(
    district_id="jorhat",

    # --- Date windows (PLACEHOLDER — validate against actual S1 acquisitions) ---
    # Pre-event baseline: 2026-06-25 → 2026-07-05
    # Must contain at least one S1 DESCENDING+IW+VH acquisition over Jorhat
    pre_start="2026-06-25",
    pre_end="2026-07-05",

    # Event window: 2026-07-18 → 2026-07-25
    # Core flood period based on reported onset ~19 July
    event_start="2026-07-18",
    event_end="2026-07-25",

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
        "pre_end": "2026-07-05",
        "reason": "Wider pre-event window to increase chance of S1 acquisition",
    },
    "wider_event": {
        "event_start": "2026-07-15",
        "event_end": "2026-08-05",
        "reason": "Extended event window if S1 coverage is sparse in 18–25 July",
    },
    "post_flood": {
        "event_start": "2026-08-01",
        "event_end": "2026-08-10",
        "reason": "Post-flood peak if flooding persisted into August",
    },
}


# ---------------------------------------------------------------------------
# Export filename
# ---------------------------------------------------------------------------

def get_export_filename() -> str:
    """Generate the export filename for this run."""
    return JORHAT_CONFIG.generate_filename()


# ---------------------------------------------------------------------------
# GEE discovery script (to be run in authenticated GEE environment)
# ---------------------------------------------------------------------------

GEE_DISCOVERY_SCRIPT = '''
// ============================================================
// SENTINEL-1 AVAILABILITY DISCOVERY — JORHAT, JULY 2026
// ============================================================
// Run this script in Google Earth Engine Code Editor or
// Python API to find actual Sentinel-1 acquisitions.
//
// Purpose: Determine which S1 images are available before
// selecting final date windows for flood mapping.
// ============================================================

// --- Step 1: Define Jorhat AOI from PostGIS export ---
// Option A: Use the actual district geometry (preferred)
//   Upload data/jorhat_gee.geojson to GEE Assets
//   var jorhat = ee.FeatureCollection('projects/YOUR_PROJECT/assets/jorhat_gee');
//   var aoi = jorhat.geometry();

// Option B: Bounding box approximation (for discovery only)
var aoi = ee.Geometry.Rectangle([94.05, 26.55, 94.55, 26.95]);

// --- Step 2: Define search windows ---
var preStart = '2026-06-25';
var preEnd   = '2026-07-05';
var evtStart = '2026-07-18';
var evtEnd   = '2026-07-25';

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
print('Date range:', preStart, '→', preEnd);
print('Image count:', preImages.size());
print('Images:', preImages);

// Print each image's metadata
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
print('Date range:', evtStart, '→', evtEnd);
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
var widePre = s1.filterDate('2026-06-10', '2026-07-05');
var wideEvt = s1.filterDate('2026-07-15', '2026-08-05');

print('=== WIDER PRE (Jun 10 → Jul 5) ===');
print('Count:', widePre.size());

print('=== WIDER EVENT (Jul 15 → Aug 5) ===');
print('Count:', wideEvt.size());

// --- Step 6: Visualize first available image ---
var firstPre = preImages.first();
var firstEvt = evtImages.first();

if (firstPre) {
  Map.centerObject(aoi, 10);
  Map.addLayer(firstPre, {bands: ['VV'], min: -25, max: 0}, 'Pre-event VV');
  Map.addLayer(firstPre, {bands: ['VH'], min: -25, max: 0}, 'Pre-event VH');
}

if (firstEvt) {
  Map.addLayer(firstEvt, {bands: ['VH'], min: -25, max: 0}, 'Event VH');
}

Map.addLayer(aoi, {color: 'yellow'}, 'Jorhat AOI');
'''


# ---------------------------------------------------------------------------
# GEE execution script (after discovery confirms dates)
# ---------------------------------------------------------------------------

GEE_EXECUTION_SCRIPT = '''
// ============================================================
// JORHAT FLOOD SNAPSHOT — EXECUTION SCRIPT
// ============================================================
// Run AFTER discovery confirms S1 availability.
// Replace DATE Window placeholders with actual dates.
// ============================================================

// --- Import pipeline functions ---
// (In practice, paste the pipeline functions from
//  agent/gee/flood_pipeline.py here, or import as module)

// --- Step 1: District geometry ---
// Upload data/jorhat_gee.geojson as GEE asset
var jorhat_fc = ee.FeatureCollection('projects/YOUR_PROJECT/assets/jorhat_gee');
var aoi = jorhat_fc.geometry();

// --- Step 2: Date windows ---
// REPLACE with actual dates confirmed by discovery script
var preStart = '2026-06-XX';  // ← CONFIRMED DATE
var preEnd   = '2026-07-XX';  // ← CONFIRMED DATE
var evtStart = '2026-07-XX';  // ← CONFIRMED DATE
var evtEnd   = '2026-07-XX';  // ← CONFIRMED DATE

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
var largestArea = floodPolygons.aggregate_max('area_m2');
var avgArea = floodPolygons.aggregate_mean('area_m2');
print('Total flooded area (m²):', totalArea);
print('Largest polygon (m²):', largestArea);
print('Average polygon (m²):', avgArea);

// --- Step 10: Visualization ---
Map.centerObject(aoi, 10);
Map.addLayer(aoi, {color: 'yellow'}, 'Jorhat District');
Map.addLayer(preSmoothed, {bands: ['VH'], min: -25, max: 0}, 'Pre-event VH');
Map.addLayer(evtSmoothed, {bands: ['VH'], min: -25, max: 0}, 'Event VH');
Map.addLayer(diff, {min: -10, max: 10, palette: ['blue', 'white', 'red']}, 'dB Difference');
Map.addLayer(floodClean, {palette: ['red']}, 'Flood Mask (cleaned)');
Map.addLayer(floodPolygons, {color: 'red'}, 'Flood Polygons');

// --- Step 11: Export (uncomment after visual validation) ---
// Export.table.toDrive({
//   collection: floodPolygons,
//   description: 'jorhat_flood_' + evtStart + '_' + evtEnd,
//   folder: 'ReliefOS_Flood_Snapshots',
//   fileNamePrefix: 'jorhat_flood_' + evtStart + '_' + evtEnd,
//   fileFormat: 'GeoJSON',
//   maxFeatures: 1e10
// });
'''


# ---------------------------------------------------------------------------
# Validation procedure
# ---------------------------------------------------------------------------

VALIDATION_PROCEDURE = """
JORHAT FLOOD SNAPSHOT — VALIDATION PROCEDURE
=============================================

Before running the flood pipeline, execute these checks:

A. SENTINEL-1 IMAGERY EXISTS
   → Run the discovery script (GEE_DISCOVERY_SCRIPT)
   → Verify: preImages.size() >= 1 AND evtImages.size() >= 1
   → If zero images: expand date window using ALTERNATIVE_WINDOWS

B. PRE COMPOSITE RENDERS
   → Map.addLayer(preSmoothed, {bands:['VH'], min:-25, max:0})
   → Visual check: should show terrain features, not blank/garbage

C. EVENT COMPOSITE RENDERS
   → Map.addLayer(evtSmoothed, {bands:['VH'], min:-25, max:0})
   → Visual check: similar to pre-event but with visible water

D. DIFFERENCE IMAGE RENDERS
   → Map.addLayer(diff, {min:-10, max:10, palette:['blue','white','red']})
   → Blue = potential flood (backscatter decrease)
   → Red = potential drying/emergence

E. FLOOD MASK RENDERS
   → Map.addLayer(floodClean, {palette:['red']})
   → Should show coherent patches along rivers/floodplains
   → NOT scattered random pixels (would indicate noise)

F. CLEANED FLOOD MASK RENDERS
   → After connected-component cleanup
   → Small isolated pixels should be removed
   → Larger connected regions should remain

G. VECTOR RESULT IS GEOGRAPHICALLY PLAUSIBLE
   → Flood polygons should align with:
     - Brahmaputra river and tributaries
     - Low-lying areas in Jorhat district
     - Known flood-prone zones
   → Should NOT appear in highland/mountainous areas

H. POLYGON COUNT IS FINITE/REASONABLE
   → Expected range: 10–500 polygons (rough estimate)
   → Zero polygons: threshold too aggressive or no flooding
   → >1000 polygons: threshold may be too lenient

I. TOTAL AREA IS PLAUSIBLE
   → Jorhat district area: ~1,321 km²
   → Flooded area should be < district area
   → Reasonable range: 10–300 km² depending on severity
   → If > district area: processing error

J. OUTPUT IS INSIDE JORHAT DISTRICT GEOMETRY
   → All polygon centroids should fall within the district boundary
   → No polygons should extend significantly beyond the boundary

K. CROSS-CHECK WITH CONTEXT
   → Upper Assam flooding intensified ~19 July 2026
   → Jorhat was among worst-affected districts
   → CWC river levels elevated at Neamatighat
   → Central damage-assessment team visited
   → If NO flood detected: possible issues with:
     - Date window selection
     - Threshold too aggressive
     - S1 acquisition timing mismatch

IF VISUAL RESULT CLEARLY FAILS:
   → Document the evidence (screenshot/note)
   → Propose parameter adjustment for human approval
   → Do NOT silently change parameters
"""


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_run_summary():
    """Print a summary of the Jorhat run configuration."""
    print("=" * 60)
    print("JORHAT FLOOD SNAPSHOT — RUN CONFIGURATION")
    print("=" * 60)
    print()
    print("District: Jorhat, Assam, India")
    print(f"Export filename: {get_export_filename()}")
    print()
    print("Date windows (VALIDATE AGAINST ACTUAL S1 DATA):")
    print(f"  Pre-event:  {JORHAT_CONFIG.pre_start} → {JORHAT_CONFIG.pre_end}")
    print(f"  Event:      {JORHAT_CONFIG.event_start} → {JORHAT_CONFIG.event_end}")
    print()
    print("Processing parameters:")
    print(f"  Collection:    {JORHAT_CONFIG.collection}")
    print(f"  Polarization:  {JORHAT_CONFIG.polarization}")
    print(f"  Instrument:    {JORHAT_CONFIG.instrument_mode}")
    print(f"  Orbit:         {JORHAT_CONFIG.orbit_pass}")
    print(f"  Threshold:     {JORHAT_CONFIG.threshold_db} dB")
    print(f"  Speckle:       {JORHAT_CONFIG.speckle_radius_m}m focal_median")
    print(f"  Connected:     {JORHAT_CONFIG.connected_pixel_neighborhood} px neighborhood, gte {JORHAT_CONFIG.min_connected_pixels}")
    print(f"  Vector scale:  {JORHAT_CONFIG.vector_scale}m")
    print(f"  Area filter:   > {JORHAT_CONFIG.area_threshold_m2} m²")
    print()
    print("Sentinel-1 constellation (July 2026):")
    print("  S1A: DECOMMISSIONED (ended 29 June 2026)")
    print("  S1C: OPERATIONAL (launched 5 Dec 2024)")
    print("  S1D: OPERATIONAL (launched 4 Nov 2025)")
    print("  Revisit: ~6 days (S1C + S1D)")
    print()
    print("Next steps:")
    print("  1. Export Jorhat geometry: python -m agent.gee.export_district")
    print("  2. Run discovery script in GEE to find actual S1 dates")
    print("  3. Update date windows if needed")
    print("  4. Execute flood pipeline")
    print("  5. Validate per VALIDATION_PROCEDURE")
    print("=" * 60)


if __name__ == "__main__":
    print_run_summary()
