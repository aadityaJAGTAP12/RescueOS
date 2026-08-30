"""
Sentinel-1 Availability Discovery Script

Find actual Sentinel-1 GRD acquisitions over Jorhat district for
the July 2026 flood period.

Usage (in authenticated GEE Python environment):
    python -m agent.gee.discover_s1

Or paste the equivalent GEE JavaScript into Code Editor.

This script:
1. Defines Jorhat AOI from exported GeoJSON
2. Queries COPERNICUS/S1_GRD for multiple date windows
3. Reports available acquisitions with satellite, date, orbit
4. Helps select optimal pre-event and event date windows
"""

from __future__ import annotations

import os
import sys
import json
from datetime import datetime

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def discover_s1_availability_python():
    """
    Python version of S1 discovery — requires authenticated ee.
    """
    try:
        import ee
    except ImportError:
        print("ERROR: Google Earth Engine (ee) is not installed.")
        print("Install with: pip install earthengine-api")
        print("Then authenticate: earthengine authenticate")
        return

    # Try to initialize
    try:
        ee.Initialize()
    except Exception as e:
        print(f"ERROR: Could not initialize Earth Engine: {e}")
        print("Run: earthengine authenticate")
        return

    print("=" * 60)
    print("SENTINEL-1 AVAILABILITY DISCOVERY — JORHAT")
    print("=" * 60)

    # --- Step 1: Define Jorhat AOI ---
    # Try to load exported GeoJSON, fall back to bounding box
    gee_asset_path = None
    geojson_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "jorhat_gee.geojson"
    )

    if os.path.exists(geojson_path):
        print(f"\nLoading Jorhat geometry from {geojson_path}")
        with open(geojson_path, "r") as f:
            fc = json.load(f)
        # Convert GeoJSON FeatureCollection to ee.FeatureCollection
        features = []
        for feat in fc.get("features", []):
            features.append(ee.Feature(feat))
        jorhat_fc = ee.FeatureCollection(features)
        aoi = jorhat_fc.geometry()
    else:
        print(f"\nGeoJSON not found at {geojson_path}")
        print("Using bounding box approximation for discovery only.")
        print("For production runs, export the actual district geometry first.")
        # Bounding box: [west, south, east, north]
        aoi = ee.Geometry.Rectangle([94.05, 26.55, 94.55, 26.95])

    # --- Step 2: Define search windows ---
    windows = {
        "pre_primary": ("2026-06-25", "2026-07-05"),
        "pre_wider": ("2026-06-10", "2026-07-05"),
        "event_primary": ("2026-07-18", "2026-07-25"),
        "event_wider": ("2026-07-15", "2026-08-05"),
        "event_post": ("2026-08-01", "2026-08-10"),
    }

    # --- Step 3: Query S1 GRD collection ---
    s1 = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(aoi)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
    )

    # --- Step 4: Check each window ---
    results = {}
    for name, (start, end) in windows.items():
        collection = s1.filterDate(start, end)
        count = collection.size().getInfo()
        results[name] = {
            "start": start,
            "end": end,
            "count": count,
            "images": [],
        }

        if count > 0:
            # Get image info
            image_list = collection.toList(count)
            for i in range(count):
                img = ee.Image(image_list.get(i))
                props = img.getInfo().get("properties", {})
                results[name]["images"].append({
                    "date": props.get("system:time_start"),
                    "satellite": props.get("platform_number", "?"),
                    "orbit": props.get("relativeOrbitNumber", "?"),
                    "id": img.id().getInfo(),
                })

    # --- Step 5: Report results ---
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    for name, data in results.items():
        print(f"\n--- {name.upper()} ({data['start']} → {data['end']}) ---")
        print(f"  Available images: {data['count']}")
        for img in data["images"]:
            date_str = "unknown"
            if img["date"]:
                try:
                    dt = datetime.fromtimestamp(img["date"] / 1000)
                    date_str = dt.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    date_str = str(img["date"])
            print(f"  • {date_str} | S1{img['satellite']} | Orbit {img['orbit']} | {img['id']}")

    # --- Step 6: Recommendation ---
    print("\n" + "=" * 60)
    print("RECOMMENDATION")
    print("=" * 60)

    pre_data = results.get("pre_primary", {})
    evt_data = results.get("event_primary", {})

    if pre_data.get("count", 0) >= 1 and evt_data.get("count", 0) >= 1:
        print("\n✓ Primary windows have sufficient S1 coverage.")
        print(f"  Pre-event: {pre_data['start']} → {pre_data['end']} ({pre_data['count']} images)")
        print(f"  Event:     {evt_data['start']} → {evt_data['end']} ({evt_data['count']} images)")
        print("\n  → Proceed with primary date windows.")
    else:
        print("\n⚠ Primary windows may lack S1 coverage.")
        if pre_data.get("count", 0) == 0:
            print(f"  Pre-event: {pre_data['start']} → {pre_data['end']} → 0 images")
            wider = results.get("pre_wider", {})
            if wider.get("count", 0) > 0:
                print(f"  → Wider pre window has {wider['count']} images: {wider['start']} → {wider['end']}")
        if evt_data.get("count", 0) == 0:
            print(f"  Event: {evt_data['start']} → {evt_data['end']} → 0 images")
            wider = results.get("event_wider", {})
            if wider.get("count", 0) > 0:
                print(f"  → Wider event window has {wider['count']} images: {wider['start']} → {wider['end']}")

    print("\n" + "=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print("1. Review the available acquisition dates above")
    print("2. Update JORHAT_CONFIG date windows if needed")
    print("3. Ensure pre-event images have ≥1 DESCENDING pass over Jorhat")
    print("4. Ensure event images cover the flood peak (~19–25 July)")
    print("5. Run the flood pipeline with confirmed dates")
    print("=" * 60)

    return results


# ---------------------------------------------------------------------------
# JavaScript equivalent (paste into GEE Code Editor)
# ---------------------------------------------------------------------------

GEE_CODE_EDITOR_SCRIPT = """
// ============================================================
// SENTINEL-1 AVAILABILITY — JORHAT (Code Editor version)
// ============================================================

// Jorhat bounding box (for discovery)
var aoi = ee.Geometry.Rectangle([94.05, 26.55, 94.55, 26.95]);

// S1 GRD collection — IW, VH, DESCENDING
var s1 = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filterBounds(aoi)
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
  .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'));

// Check multiple windows
var windows = [
  {name: 'PRE_PRIMARY',  start: '2026-06-25', end: '2026-07-05'},
  {name: 'PRE_WIDER',    start: '2026-06-10', end: '2026-07-05'},
  {name: 'EVT_PRIMARY',  start: '2026-07-18', end: '2026-07-25'},
  {name: 'EVT_WIDER',    start: '2026-07-15', end: '2026-08-05'},
  {name: 'EVT_POST',     start: '2026-08-01', end: '2026-08-10'},
];

windows.forEach(function(w) {
  var col = s1.filterDate(w.start, w.end);
  print(w.name + ' (' + w.start + ' → ' + w.end + '):', col.size(), 'images');
  
  col.evaluate(function(result) {
    if (result && result.features) {
      result.features.forEach(function(f) {
        var p = f.properties;
        var date = new Date(p.system:time_start).toISOString().split('T')[0];
        print('  ' + date + ' | S1' + p.platform_number + ' | Orbit ' + p.relativeOrbitNumber);
      });
    }
  });
});

// Visualize first available image
var firstImg = s1.filterDate('2026-06-25', '2026-08-10').first();
if (firstImg) {
  Map.centerObject(aoi, 10);
  Map.addLayer(firstImg, {bands: ['VH'], min: -25, max: 0}, 'First S1 VH');
  Map.addLayer(aoi, {color: 'yellow'}, 'Jorhat AOI');
}
"""


if __name__ == "__main__":
    results = discover_s1_availability_python()
