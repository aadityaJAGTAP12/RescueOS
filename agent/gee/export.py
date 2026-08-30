"""
Flood Snapshot Export Helpers

Reusable export functions for sending GEE flood processing results
to Google Drive as GeoJSON, or converting to local formats.

The export filename is generated from district + event period.
Do not hardcode district names in the export function.
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


def export_flood_geojson_to_drive(
    flood_polygons,
    config: FloodPipelineConfig,
    folder: str = "ReliefOS_Flood_Snapshots",
    description: Optional[str] = None,
    scale: int = 10,
    max_pixels: float = 1e10,
    crs: str = "EPSG:4326",
):
    """
    Export a flood polygon FeatureCollection to Google Drive as GeoJSON.

    The filename is automatically generated from district + event period.
    Example: sivasagar_flood_2026-08-08_2026-08-13.geojson

    Args:
        flood_polygons: ee.FeatureCollection — vectorized flood polygons
        config: FloodPipelineConfig — with district_id and dates
        folder: Google Drive folder name
        description: export task description (auto-generated if None)
        scale: export resolution in meters
        max_pixels: maximum pixels for export
        crs: coordinate reference system

    Returns:
        ee.batch.Task — the export task (caller must start it)
    """
    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    filename = config.generate_filename()

    if description is None:
        description = f"ReliefOS flood snapshot: {filename}"

    task = ee.batch.Export.table.toDrive(
        collection=flood_polygons,
        description=description,
        folder=folder,
        fileNamePrefix=filename,
        fileFormat="GeoJSON",
        maxFeatures=max_pixels,
    )

    return task


def export_flood_geojson_to_asset(
    flood_polygons,
    config: FloodPipelineConfig,
    asset_id: Optional[str] = None,
    description: Optional[str] = None,
):
    """
    Export a flood polygon FeatureCollection to an Earth Engine asset.

    Useful for sharing flood snapshots between GEE scripts/users.

    Args:
        flood_polygons: ee.FeatureCollection — vectorized flood polygons
        config: FloodPipelineConfig
        asset_id: GEE asset path (auto-generated if None)
        description: export task description

    Returns:
        ee.batch.Task — the export task
    """
    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    if asset_id is None:
        district = config.district_id or "unknown"
        start = config.event_start or "unknown"
        end = config.event_end or "unknown"
        asset_id = f"projects/reliefos/flood_snapshots/{district}_flood_{start}_{end}"

    if description is None:
        description = f"ReliefOS flood asset: {asset_id}"

    task = ee.batch.Export.table.toAsset(
        collection=flood_polygons,
        description=description,
        assetId=asset_id,
    )

    return task


def get_task_status(task) -> dict:
    """
    Get the status of an export task.

    Args:
        task: ee.batch.Task

    Returns:
        dict with task status information
    """
    task_status = task.status()
    return {
        "state": task_status.get("state", "UNKNOWN"),
        "description": task_status.get("description", ""),
        "creation_timestamp_ms": task_status.get("creation_timestamp_ms"),
        "update_timestamp_ms": task_status.get("update_timestamp_ms"),
        "error_message": task_status.get("error_message"),
    }


def monitor_export(tasks: list, poll_interval_seconds: int = 30) -> list:
    """
    Monitor a list of export tasks until all complete.

    Args:
        tasks: list of ee.batch.Task objects
        poll_interval_seconds: seconds between status checks

    Returns:
        list of final task status dicts
    """
    import time

    if not _EE_AVAILABLE:
        raise ImportError("Google Earth Engine (ee) is required.")

    all_tasks = list(tasks)

    while all_tasks:
        still_running = []
        for task in all_tasks:
            status = get_task_status(task)
            if status["state"] in ("READY", "RUNNING"):
                still_running.append(task)
            elif status["state"] in ("COMPLETED", "FAILED", "CANCELLED"):
                if status["state"] == "COMPLETED":
                    print(f"  ✓ Export completed: {status['description']}")
                else:
                    print(f"  ✗ Export {status['state']}: {status['description']}")
                    if status.get("error_message"):
                        print(f"    Error: {status['error_message']}")

        all_tasks = still_running
        if all_tasks:
            time.sleep(poll_interval_seconds)

    return [get_task_status(t) for t in tasks]
