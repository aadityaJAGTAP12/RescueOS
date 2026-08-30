"""
ReliefOS Ingestion Pipeline — Base Utilities

Common functions for all ingestion scripts:
- Database connection
- Logging
- Source metadata tracking
- Idempotent upsert helpers
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Optional

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from agent.data.schema import get_engine, create_all_tables, metadata
from agent.data.postgres_repository import PostgresRepository
from agent.data.models import (
    District, Settlement, FloodSnapshot, FieldReport, Override,
    Building, MedicalFacility, Road, Provenance, VerificationState,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(name: str) -> logging.Logger:
    """Configure logging for ingestion scripts."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

def get_repo() -> PostgresRepository:
    """Get a PostgresRepository connected to the configured database."""
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise ValueError("DATABASE_URL not set. Export it before running ingestion.")
    engine = get_engine(database_url)
    create_all_tables(engine)
    return PostgresRepository(engine=engine)


# ---------------------------------------------------------------------------
# Source metadata
# ---------------------------------------------------------------------------

class SourceMetadata:
    """Track data source provenance for audit trail."""
    
    def __init__(self, source_name: str, source_url: str, license: str,
                 access_date: str, attribution: str = ""):
        self.source_name = source_name
        self.source_url = source_url
        self.license = license
        self.access_date = access_date
        self.attribution = attribution
    
    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "source_url": self.source_url,
            "license": self.license,
            "access_date": self.access_date,
            "attribution": self.attribution,
        }


# Pre-defined sources
SOURCES = {
    "osm_nominatim": SourceMetadata(
        source_name="OpenStreetMap Nominatim",
        source_url="https://nominatim.openstreetmap.org",
        license="ODbL 1.0",
        access_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        attribution="© OpenStreetMap contributors",
    ),
    "osm_overpass": SourceMetadata(
        source_name="OpenStreetMap Overpass API",
        source_url="https://overpass-api.de",
        license="ODbL 1.0",
        access_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        attribution="© OpenStreetMap contributors",
    ),
    "sentinel1_sar": SourceMetadata(
        source_name="Sentinel-1 SAR (Earth Engine export)",
        source_url="https://earthengine.google.com",
        license="Copernicus Open Access License",
        access_date="2026-07-01",
        attribution="Contains Copernicus Sentinel data",
    ),
    "manual_research": SourceMetadata(
        source_name="Manual research / public reports",
        source_url="N/A",
        license="Public domain / fair use",
        access_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        attribution="Compiled from public sources",
    ),
}


# ---------------------------------------------------------------------------
# Ingestion stats
# ---------------------------------------------------------------------------

class IngestStats:
    """Track ingestion statistics per source/district."""
    
    def __init__(self):
        self.stats = {}
    
    def record(self, district_id: str, source: str, entity_type: str,
               count: int, errors: int = 0):
        key = f"{district_id}:{source}:{entity_type}"
        self.stats[key] = {
            "district_id": district_id,
            "source": source,
            "entity_type": entity_type,
            "count": count,
            "errors": errors,
        }
    
    def summary(self) -> str:
        lines = ["=== Ingestion Summary ==="]
        for key, s in sorted(self.stats.items()):
            status = "✓" if s["errors"] == 0 else f"✗ {s['errors']} errors"
            lines.append(f"  {s['district_id']:15s} {s['entity_type']:20s} {s['count']:6d} {status}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def geojson_to_wkt(geojson_geom: dict) -> Optional[str]:
    """Convert a GeoJSON geometry dict to WKT string with SRID."""
    geom_type = geojson_geom.get("type", "")
    coords = geojson_geom.get("coordinates", [])
    
    if geom_type == "Point":
        return f"SRID=4326;POINT({coords[0]} {coords[1]})"
    elif geom_type == "Polygon":
        rings = []
        for ring in coords:
            points = ", ".join(f"{c[0]} {c[1]}" for c in ring)
            rings.append(f"({points})")
        return f"SRID=4326;POLYGON({', '.join(rings)})"
    elif geom_type == "MultiPolygon":
        polygons = []
        for poly in coords:
            rings = []
            for ring in poly:
                points = ", ".join(f"{c[0]} {c[1]}" for c in ring)
                rings.append(f"({points})")
            polygons.append(f"({', '.join(rings)})")
        return f"SRID=4326;MULTIPOLYGON({', '.join(polygons)})"
    elif geom_type == "LineString":
        points = ", ".join(f"{c[0]} {c[1]}" for c in coords)
        return f"SRID=4326;LINESTRING({points})"
    elif geom_type == "MultiLineString":
        lines = []
        for line in coords:
            points = ", ".join(f"{c[0]} {c[1]}" for c in line)
            lines.append(f"({points})")
        return f"SRID=4326;MULTILINESTRING({', '.join(lines)})"
    return None


def wkt_to_geojson(wkt_str: str) -> Optional[dict]:
    """Convert a WKT geometry string (with optional SRID prefix) to a GeoJSON geometry dict.

    Handles: Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon.
    Strips SRID=XXXX; prefix if present.

    Returns None if the WKT string cannot be parsed.
    """
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
        return mapping(geom)
    except Exception:
        return None


def extract_centroid(geojson_geom: dict) -> tuple[float, float]:
    """Extract centroid coordinates from a GeoJSON geometry."""
    geom_type = geojson_geom.get("type", "")
    coords = geojson_geom.get("coordinates", [])
    
    if geom_type == "Point":
        return coords[1], coords[0]  # lat, lon
    elif geom_type == "Polygon":
        # Use first ring's centroid approximation
        ring = coords[0]
        lats = [c[1] for c in ring]
        lons = [c[0] for c in ring]
        return sum(lats) / len(lats), sum(lons) / len(lons)
    elif geom_type == "MultiPolygon":
        # Use first polygon's centroid
        return extract_centroid({"type": "Polygon", "coordinates": coords[0]})
    return 0.0, 0.0


# ---------------------------------------------------------------------------
# Rate limiting for API calls
# ---------------------------------------------------------------------------

import time

def rate_limit(seconds: float = 1.0):
    """Simple rate limiter for API calls."""
    time.sleep(seconds)
