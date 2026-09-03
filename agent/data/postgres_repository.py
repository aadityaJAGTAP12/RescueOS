"""
Phase 5A: PostgreSQL + PostGIS Repository Implementation

Implements the full DataRepository interface against PostgreSQL/PostGIS.
Uses SQLAlchemy Core (not ORM) with GeoAlchemy2 for spatial operations.

Key features:
- Database-side spatial filtering (point-in-polygon, intersects, within radius)
- Temporal flood snapshot queries
- Provenance preservation
- Bulk import support
- Idempotent upserts via ON CONFLICT DO UPDATE
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text, select, insert, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from geoalchemy2.functions import (
    ST_Contains, ST_Distance, ST_DWithin, ST_GeomFromText,
    ST_Point, ST_MakePoint, ST_SetSRID, ST_MakeLine, ST_Multi, ST_Collect,
    ST_Buffer, ST_Transform,
)

from agent.data.models import (
    District,
    Settlement,
    FloodSnapshot,
    FieldReport,
    Override,
    MedicalFacility,
    Building,
    Road,
    Provenance,
    VerificationState,
    make_flood_snapshot_id,
    Organization,
    Need,
    ResourceOffer,
    Operation,
    ActivityEvent,
    Notification,
)
from agent.data.repository import DataRepository
from agent.data.schema import (
    districts, settlements, flood_snapshots, field_reports,
    overrides, buildings, medical_facilities, roads,
    get_engine, SRID,
)


class PostgresRepository(DataRepository):
    """
    PostgreSQL + PostGIS backed repository.

    All data operations go through this implementation in production.
    Uses SQLAlchemy Core for queries, GeoAlchemy2 for spatial operations.
    """

    def __init__(self, engine=None, database_url: str = None):
        """
        Initialize with either an existing engine or a database URL.

        Args:
            engine: SQLAlchemy engine (optional)
            database_url: PostgreSQL connection string (optional, falls back to DATABASE_URL env var)
        """
        if engine is not None:
            self._engine = engine
        else:
            self._engine = get_engine(database_url)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _execute(self, stmt, params=None):
        """Execute a statement and return the result."""
        with self._engine.connect() as conn:
            result = conn.execute(stmt, params or {})
            conn.commit()
            return result

    def _execute_fetchone(self, stmt, params=None):
        """Execute and return first row or None."""
        with self._engine.connect() as conn:
            result = conn.execute(stmt, params or {})
            return result.fetchone()

    def _execute_fetchall(self, stmt, params=None):
        """Execute and return all rows."""
        with self._engine.connect() as conn:
            result = conn.execute(stmt, params or {})
            return result.fetchall()

    @staticmethod
    def _wkt_point(lon: float, lat: float) -> str:
        """Create a WKT POINT for PostGIS."""
        return f"SRID={SRID};POINT({lon} {lat})"

    @staticmethod
    def _wkb_to_wkt(wkb) -> Optional[str]:
        """Convert a WKBElement to WKT string."""
        if wkb is None:
            return None
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(f"SELECT ST_AsText(:geom)"), {"geom": wkb})
                row = result.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Districts
    # ------------------------------------------------------------------

    def get_district(self, district_id: str) -> Optional[District]:
        # Use raw query to get WKT directly (avoids WKBElement conversion issues)
        with self._engine.connect() as conn:
            result = conn.execute(
                text("SELECT id, name, state, country, ST_AsText(geometry) as geometry_wkt, metadata "
                     "FROM districts WHERE id = :did"),
                {"did": district_id}
            )
            row = result.fetchone()
        if row is None:
            return None
        return District(
            id=row.id,
            name=row.name,
            state=row.state,
            country=row.country,
            geometry_wkt=row.geometry_wkt,
            metadata=row.metadata or {},
        )

    def list_districts(self) -> list[District]:
        rows = self._execute_fetchall(select(districts))
        return [
            District(
                id=r.id,
                name=r.name,
                state=r.state,
                country=r.country,
                geometry_wkt=self._row_geometry_to_wkt(r, "geometry"),
                metadata=r.metadata or {},
            )
            for r in rows
        ]

    def upsert_district(self, district: District) -> None:
        stmt = pg_insert(districts).values(
            id=district.id,
            name=district.name,
            state=district.state,
            country=district.country,
            geometry=district.geometry_wkt,
            metadata=district.metadata,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": district.name,
                "state": district.state,
                "country": district.country,
                "geometry": district.geometry_wkt,
                "metadata": district.metadata,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        self._execute(stmt)

    # ------------------------------------------------------------------
    # Settlements
    # ------------------------------------------------------------------

    def get_settlement(self, settlement_id: str) -> Optional[Settlement]:
        row = self._execute_fetchone(
            select(settlements).where(settlements.c.id == settlement_id)
        )
        if row is None:
            return None
        return self._row_to_settlement(row)

    def list_settlements(self, district_id: Optional[str] = None) -> list[Settlement]:
        stmt = select(settlements)
        if district_id:
            stmt = stmt.where(settlements.c.district_id == district_id)
        rows = self._execute_fetchall(stmt)
        return [self._row_to_settlement(r) for r in rows]

    def upsert_settlement(self, settlement: Settlement) -> None:
        location_wkt = self._wkt_point(settlement.lon, settlement.lat)
        stmt = pg_insert(settlements).values(
            id=settlement.id,
            name=settlement.name,
            district_id=settlement.district_id,
            lat=settlement.lat,
            lon=settlement.lon,
            aliases=settlement.aliases,
            metadata=settlement.metadata,
            location=location_wkt,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": settlement.name,
                "district_id": settlement.district_id,
                "lat": settlement.lat,
                "lon": settlement.lon,
                "aliases": settlement.aliases,
                "metadata": settlement.metadata,
                "location": location_wkt,
            },
        )
        self._execute(stmt)

    def resolve_location(self, name: str = None, lat: float = None, lon: float = None, district_id: str = None) -> Optional[Settlement]:
        """
        Generalized location resolution against PostgreSQL.

        Resolution order:
        1. Coordinate-based: nearest settlement within 5km via PostGIS ST_DWithin
        2. Name-based: exact match, then case-insensitive, then alias
        3. Direct coordinates: return synthetic settlement if no match
        """
        # 1. Coordinate-based resolution using PostGIS
        if lat is not None and lon is not None:
            point_wkt = f"SRID={SRID};POINT({lon} {lat})"
            # 5km in degrees (approximate, good enough for this use case)
            approx_5km_deg = 5.0 / 111.0

            stmt = (
                select(settlements,
                       ST_Distance(
                           settlements.c.location,
                           ST_SetSRID(ST_MakePoint(lon, lat), SRID)
                       ).label("dist"))
            )
            if district_id:
                stmt = stmt.where(settlements.c.district_id == district_id)
            stmt = stmt.order_by(text("dist")).limit(5)
            rows = self._execute_fetchall(stmt)

            if rows:
                best = rows[0]
                if best.dist <= approx_5km_deg:
                    return self._row_to_settlement(best)

            # Return a synthetic settlement for direct coordinates
            return Settlement(
                id=f"coord_{lat:.4f}_{lon:.4f}",
                name=f"({lat:.4f}, {lon:.4f})",
                district_id=district_id or "unknown",
                lat=lat,
                lon=lon,
            )

        # 2. Name-based resolution
        if name is None:
            return None

        name_lower = name.strip().lower()

        # Exact match by id or name
        row = self._execute_fetchone(
            select(settlements).where(
                (settlements.c.id.ilike(name_lower)) |
                (settlements.c.name.ilike(name_lower))
            )
        )
        if row:
            return self._row_to_settlement(row)

        # Partial match
        row = self._execute_fetchone(
            select(settlements).where(
                settlements.c.name.ilike(f"%{name_lower}%")
            ).limit(1)
        )
        if row:
            return self._row_to_settlement(row)

        # Alias match — search JSONB aliases array
        row = self._execute_fetchone(
            select(settlements).where(
                text("aliases::jsonb @> :alias_json")
            ).params(alias_json=json.dumps([name_lower]))
        )
        if row:
            return self._row_to_settlement(row)

        return None

    # ------------------------------------------------------------------
    # Flood Snapshots
    # ------------------------------------------------------------------

    def get_flood_snapshot(self, snapshot_id: str) -> Optional[FloodSnapshot]:
        row = self._execute_fetchone(
            select(flood_snapshots).where(flood_snapshots.c.id == snapshot_id)
        )
        if row is None:
            return None
        return self._row_to_flood_snapshot(row)

    def list_flood_snapshots(self, district_id: str = None, observed_after: str = None) -> list[FloodSnapshot]:
        stmt = select(flood_snapshots)
        if district_id:
            stmt = stmt.where(flood_snapshots.c.district_id == district_id)
        if observed_after:
            cutoff = datetime.fromisoformat(observed_after)
            stmt = stmt.where(flood_snapshots.c.observed_at >= cutoff)
        stmt = stmt.order_by(flood_snapshots.c.observed_at.desc())
        rows = self._execute_fetchall(stmt)
        return [self._row_to_flood_snapshot(r) for r in rows]

    def upsert_flood_snapshot(self, snapshot: FloodSnapshot) -> None:
        # Convert GeoJSON to PostGIS MultiPolygon geometry
        geometry_sql = None
        if snapshot.geometry_geojson:
            geometry_sql = self._geojson_to_multipolygon_sql(snapshot.geometry_geojson)

        stmt = pg_insert(flood_snapshots).values(
            id=snapshot.id,
            district_id=snapshot.district_id,
            observed_at=snapshot.observed_at,
            source=snapshot.source,
            confidence=snapshot.confidence,
            geometry=geometry_sql,
            geometry_geojson=snapshot.geometry_geojson,
            polygon_count=snapshot.polygon_count,
            provenance=snapshot.provenance.value,
            source_timestamp=snapshot.source_timestamp,
            metadata=snapshot.metadata,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "district_id": snapshot.district_id,
                "observed_at": snapshot.observed_at,
                "source": snapshot.source,
                "confidence": snapshot.confidence,
                "geometry": geometry_sql,
                "geometry_geojson": snapshot.geometry_geojson,
                "polygon_count": snapshot.polygon_count,
                "provenance": snapshot.provenance.value,
                "source_timestamp": snapshot.source_timestamp,
                "metadata": snapshot.metadata,
            },
        )
        self._execute(stmt)

    def get_latest_flood_snapshot(self, district_id: str, observed_at: str = None) -> Optional[FloodSnapshot]:
        stmt = select(flood_snapshots).where(
            flood_snapshots.c.district_id == district_id
        )
        if observed_at:
            cutoff = datetime.fromisoformat(observed_at)
            stmt = stmt.where(flood_snapshots.c.observed_at <= cutoff)
        stmt = stmt.order_by(flood_snapshots.c.observed_at.desc()).limit(1)
        row = self._execute_fetchone(stmt)
        if row is None:
            return None
        return self._row_to_flood_snapshot(row)

    def query_flood_containment(self, lat: float, lon: float, district_id: str = None) -> list[FloodSnapshot]:
        """
        PostGIS-accelerated: find flood snapshots whose geometry contains the given point.
        """
        point_wkt = f"SRID={SRID};POINT({lon} {lat})"
        stmt = (
            select(flood_snapshots)
            .where(
                ST_Contains(flood_snapshots.c.geometry, ST_SetSRID(ST_MakePoint(lon, lat), SRID))
            )
        )
        if district_id:
            stmt = stmt.where(flood_snapshots.c.district_id == district_id)
        rows = self._execute_fetchall(stmt)
        return [self._row_to_flood_snapshot(r) for r in rows]

    # ------------------------------------------------------------------
    # Field Reports
    # ------------------------------------------------------------------

    def get_field_report(self, report_id: str) -> Optional[FieldReport]:
        row = self._execute_fetchone(
            select(field_reports).where(field_reports.c.id == report_id)
        )
        if row is None:
            return None
        return self._row_to_field_report(row)

    def list_field_reports(self, district_id: str = None, lat: float = None, lon: float = None, radius_km: float = 5.0) -> list[FieldReport]:
        stmt = select(field_reports)
        if district_id:
            stmt = stmt.where(field_reports.c.district_id == district_id)

        if lat is not None and lon is not None:
            # PostGIS spatial radius filter
            approx_radius_deg = radius_km / 111.0
            stmt = stmt.where(
                ST_DWithin(
                    field_reports.c.location,
                    ST_SetSRID(ST_MakePoint(lon, lat), SRID),
                    approx_radius_deg
                )
            )

        rows = self._execute_fetchall(stmt)
        return [self._row_to_field_report(r) for r in rows]

    def upsert_field_report(self, report: FieldReport) -> None:
        location_wkt = None
        if report.lat is not None and report.lon is not None:
            location_wkt = self._wkt_point(report.lon, report.lat)

        stmt = pg_insert(field_reports).values(
            id=report.id,
            district_id=report.district_id,
            lat=report.lat,
            lon=report.lon,
            location=location_wkt,
            source_type=report.source_type,
            raw_text=report.raw_text,
            people_count=report.people_count,
            adults=report.adults,
            children=report.children,
            elderly=report.elderly,
            needs=report.needs,
            location_description=report.location_description,
            verification_state=report.verification_state.value,
            extraction_confidence=report.extraction_confidence,
            observed_at=report.observed_at,
            ingested_at=report.ingested_at,
            provenance=report.provenance.value,
            metadata=report.metadata,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "district_id": report.district_id,
                "lat": report.lat,
                "lon": report.lon,
                "location": location_wkt,
                "source_type": report.source_type,
                "raw_text": report.raw_text,
                "people_count": report.people_count,
                "adults": report.adults,
                "children": report.children,
                "elderly": report.elderly,
                "needs": report.needs,
                "location_description": report.location_description,
                "verification_state": report.verification_state.value,
                "extraction_confidence": report.extraction_confidence,
                "observed_at": report.observed_at,
                "ingested_at": report.ingested_at,
                "provenance": report.provenance.value,
                "metadata": report.metadata,
            },
        )
        self._execute(stmt)

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def get_active_override(self, target_type: str, target_id: str) -> Optional[Override]:
        # Use fuzzy matching like InMemoryRepository
        rows = self._execute_fetchall(
            select(overrides).where(
                (overrides.c.target_type == target_type) &
                (overrides.c.active == True)
            ).order_by(overrides.c.created_at.desc())
        )
        for row in rows:
            if _names_match(row.target_id, target_id):
                return self._row_to_override(row)
        return None

    def list_overrides(self, district_id: str = None) -> list[Override]:
        rows = self._execute_fetchall(select(overrides))
        return [self._row_to_override(r) for r in rows]

    def upsert_override(self, override: Override) -> None:
        stmt = pg_insert(overrides).values(
            id=override.id,
            target_type=override.target_type,
            target_id=override.target_id,
            override_status=override.override_status,
            reason=override.reason,
            actor=override.actor,
            system_status=override.system_status,
            active=override.active,
            created_at=override.created_at,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "target_type": override.target_type,
                "target_id": override.target_id,
                "override_status": override.override_status,
                "reason": override.reason,
                "actor": override.actor,
                "system_status": override.system_status,
                "active": override.active,
                "created_at": override.created_at,
            },
        )
        self._execute(stmt)

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------

    def get_buildings(self, district_id: str, lat: float = None, lon: float = None, radius_km: float = 1.5) -> list[Building]:
        stmt = select(buildings).where(buildings.c.district_id == district_id)

        if lat is not None and lon is not None:
            approx_radius_deg = radius_km / 111.0
            stmt = stmt.where(
                ST_DWithin(
                    buildings.c.location,
                    ST_SetSRID(ST_MakePoint(lon, lat), SRID),
                    approx_radius_deg
                )
            )

        rows = self._execute_fetchall(stmt)
        return [self._row_to_building(r) for r in rows]

    def get_medical_facilities(self, district_id: str, lat: float = None, lon: float = None, radius_km: float = 20.0) -> list[MedicalFacility]:
        stmt = select(medical_facilities).where(medical_facilities.c.district_id == district_id)

        if lat is not None and lon is not None:
            approx_radius_deg = radius_km / 111.0
            stmt = stmt.where(
                ST_DWithin(
                    medical_facilities.c.location,
                    ST_SetSRID(ST_MakePoint(lon, lat), SRID),
                    approx_radius_deg
                )
            )

        rows = self._execute_fetchall(stmt)
        return [self._row_to_medical_facility(r) for r in rows]

    def get_roads(self, district_id: str, lat: float = None, lon: float = None, radius_km: float = 2.0) -> list[Road]:
        stmt = select(roads, text("ST_AsText(roads.geometry) AS geometry_wkt")).where(roads.c.district_id == district_id)
        rows = self._execute_fetchall(stmt)
        return [self._row_to_road(r) for r in rows]

    def upsert_buildings(self, buildings_list: list[Building]) -> None:
        """Upsert buildings using psycopg2 execute_batch for bulk performance."""
        if not buildings_list:
            return
        from psycopg2.extras import execute_batch
        sql = (
            "INSERT INTO buildings (id, district_id, osm_id, lat, lon, location, geometry, tags, in_flood_zone, provenance) "
            "VALUES (%s, %s, %s, %s, %s, "
            "CASE WHEN %s IS NULL THEN NULL ELSE ST_GeomFromEWKT(%s) END, "
            "CASE WHEN %s IS NULL THEN NULL ELSE ST_GeomFromEWKT(%s) END, "
            "%s::jsonb, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET "
            "district_id = EXCLUDED.district_id, osm_id = EXCLUDED.osm_id, "
            "lat = EXCLUDED.lat, lon = EXCLUDED.lon, "
            "location = EXCLUDED.location, geometry = EXCLUDED.geometry, "
            "tags = EXCLUDED.tags, in_flood_zone = EXCLUDED.in_flood_zone, "
            "provenance = EXCLUDED.provenance"
        )
        rows = []
        for b in buildings_list:
            location_wkt = self._wkt_point(b.lon, b.lat) if b.lat and b.lon else None
            geometry_wkt = getattr(b, 'geometry_wkt', None)
            rows.append((
                b.id, b.district_id, b.osm_id, b.lat, b.lon,
                location_wkt, location_wkt,
                geometry_wkt, geometry_wkt,
                json.dumps(b.tags or {}), b.in_flood_zone, b.provenance.value,
            ))
        with self._engine.raw_connection() as raw_conn:
            with raw_conn.cursor() as cur:
                execute_batch(cur, sql, rows, page_size=500)
            raw_conn.commit()

    def upsert_medical_facilities(self, facilities_list: list[MedicalFacility]) -> None:
        """Upsert medical facilities using psycopg2 execute_batch for bulk performance."""
        if not facilities_list:
            return
        from psycopg2.extras import execute_batch
        sql = (
            "INSERT INTO medical_facilities (id, district_id, name, lat, lon, location, facility_type, osm_id, provenance) "
            "VALUES (%s, %s, %s, %s, %s, ST_GeomFromEWKT(%s), %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET "
            "district_id = EXCLUDED.district_id, name = EXCLUDED.name, "
            "lat = EXCLUDED.lat, lon = EXCLUDED.lon, location = EXCLUDED.location, "
            "facility_type = EXCLUDED.facility_type, osm_id = EXCLUDED.osm_id, "
            "provenance = EXCLUDED.provenance"
        )
        rows = []
        for f in facilities_list:
            location_wkt = self._wkt_point(f.lon, f.lat)
            rows.append([
                f.id, f.district_id, f.name, f.lat, f.lon,
                location_wkt, f.facility_type, f.osm_id, f.provenance.value,
            ])
        with self._engine.raw_connection() as raw_conn:
            with raw_conn.cursor() as cur:
                execute_batch(cur, sql, rows, page_size=500)
            raw_conn.commit()

    def upsert_roads(self, roads_list: list[Road]) -> None:
        """Upsert roads using psycopg2 execute_batch for bulk performance."""
        if not roads_list:
            return
        from psycopg2.extras import execute_batch
        sql = (
            "INSERT INTO roads (id, district_id, name, highway_type, osm_id, geometry, flood_affected, provenance, tags, is_bridge) "
            "VALUES (%s, %s, %s, %s, %s, "
            "CASE WHEN %s IS NULL THEN NULL ELSE ST_GeomFromEWKT(%s) END, "
            "%s, %s, %s::jsonb, %s) "
            "ON CONFLICT (id) DO UPDATE SET "
            "district_id = EXCLUDED.district_id, name = EXCLUDED.name, "
            "highway_type = EXCLUDED.highway_type, osm_id = EXCLUDED.osm_id, "
            "geometry = EXCLUDED.geometry, flood_affected = EXCLUDED.flood_affected, "
            "provenance = EXCLUDED.provenance, tags = EXCLUDED.tags, is_bridge = EXCLUDED.is_bridge"
        )
        rows = []
        for r in roads_list:
            geometry_wkt = None
            if r.geometry_coords and len(r.geometry_coords) >= 2:
                coords_str = ", ".join(f"{c[0]} {c[1]}" for c in r.geometry_coords)
                if len(r.geometry_coords) > 2:
                    geometry_wkt = f"SRID={SRID};MULTILINESTRING(({coords_str}))"
                else:
                    geometry_wkt = f"SRID={SRID};LINESTRING({coords_str})"
            tags = getattr(r, 'tags', {}) or {}
            is_bridge = getattr(r, 'is_bridge', False)
            rows.append((
                r.id, r.district_id, r.name, r.highway_type, r.osm_id,
                geometry_wkt, geometry_wkt,
                r.flood_affected, r.provenance.value, json.dumps(tags), is_bridge,
            ))
        with self._engine.raw_connection() as raw_conn:
            with raw_conn.cursor() as cur:
                execute_batch(cur, sql, rows, page_size=500)
            raw_conn.commit()

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------

    def get_provenance_summary(self, district_id: str = None) -> dict:
        summary = {}

        # Flood snapshots
        stmt = select(flood_snapshots.c.provenance)
        if district_id:
            stmt = stmt.where(flood_snapshots.c.district_id == district_id)
        for row in self._execute_fetchall(stmt):
            key = row.provenance
            summary[key] = summary.get(key, 0) + 1

        # Field reports
        stmt = select(field_reports.c.provenance)
        if district_id:
            stmt = stmt.where(field_reports.c.district_id == district_id)
        for row in self._execute_fetchall(stmt):
            key = row.provenance
            summary[key] = summary.get(key, 0) + 1

        # Overrides always count as MANUAL_OVERRIDE
        rows = self._execute_fetchall(select(overrides))
        if rows:
            summary["MANUAL_OVERRIDE"] = summary.get("MANUAL_OVERRIDE", 0) + len(rows)

        return summary

    # ------------------------------------------------------------------
    # Bulk / migration
    # ------------------------------------------------------------------

    def import_flood_geojson(self, geojson: dict, district_id: str, source: str = "import", observed_at: str = None) -> FloodSnapshot:
        """Import a GeoJSON FeatureCollection as a flood snapshot."""
        from datetime import datetime as dt, timezone

        if observed_at:
            obs_dt = dt.fromisoformat(observed_at)
        else:
            obs_dt = dt.now(timezone.utc)

        features = geojson.get("features", [])
        snapshot = FloodSnapshot(
            id=make_flood_snapshot_id(district_id, obs_dt),
            district_id=district_id,
            observed_at=obs_dt,
            source=source,
            confidence=1.0,
            geometry_geojson=geojson,
            polygon_count=len(features),
            provenance=Provenance.REAL,
        )
        self.upsert_flood_snapshot(snapshot)
        return snapshot

    # ------------------------------------------------------------------
    # Organizations (Phase 7B)
    # ------------------------------------------------------------------

    def create_organization(self, org: Organization) -> Organization:
        from agent.data.schema import organizations as orgs_table
        stmt = pg_insert(orgs_table).values(
            id=org.id,
            name=org.name,
            organization_type=org.organization_type,
            description=org.description,
            published_capabilities=org.published_capabilities,
            public_contact=org.public_contact,
            active=org.active,
            metadata=org.metadata,
        )
        self._execute(stmt)
        return org

    def get_organization(self, org_id: str) -> Optional[Organization]:
        from agent.data.schema import organizations as orgs_table
        row = self._execute_fetchone(
            select(orgs_table).where(orgs_table.c.id == org_id)
        )
        if row is None:
            return None
        return self._row_to_organization(row)

    def list_organizations(self, active_only: bool = True) -> list[Organization]:
        from agent.data.schema import organizations as orgs_table
        stmt = select(orgs_table)
        if active_only:
            stmt = stmt.where(orgs_table.c.active == True)
        rows = self._execute_fetchall(stmt)
        return [self._row_to_organization(r) for r in rows]

    def update_organization(self, org: Organization) -> None:
        from agent.data.schema import organizations as orgs_table
        stmt = update(orgs_table).where(orgs_table.c.id == org.id).values(
            name=org.name,
            organization_type=org.organization_type,
            description=org.description,
            published_capabilities=org.published_capabilities,
            public_contact=org.public_contact,
            active=org.active,
            updated_at=datetime.now(timezone.utc),
            metadata=org.metadata,
        )
        self._execute(stmt)

    # ------------------------------------------------------------------
    # Needs (Phase 7B)
    # ------------------------------------------------------------------

    def create_need(self, need: Need) -> Need:
        from agent.data.schema import needs as needs_table
        stmt = pg_insert(needs_table).values(
            id=need.id,
            need_type=need.need_type,
            title=need.title,
            description=need.description,
            district_id=need.district_id,
            lat=need.lat,
            lon=need.lon,
            location_name=need.location_name,
            urgency=need.urgency,
            status=need.status,
            requested_resources=need.requested_resources,
            reporter_id=need.reporter_id,
            reporter_type=need.reporter_type,
            confidence=need.confidence,
            metadata=need.metadata,
        )
        self._execute(stmt)
        return need

    def get_need(self, need_id: str) -> Optional[Need]:
        from agent.data.schema import needs as needs_table
        row = self._execute_fetchone(
            select(needs_table).where(needs_table.c.id == need_id)
        )
        if row is None:
            return None
        return self._row_to_need(row)

    def list_needs(self, district_id: str = None, status: str = None, urgency: str = None) -> list[Need]:
        from agent.data.schema import needs as needs_table
        stmt = select(needs_table)
        if district_id:
            stmt = stmt.where(needs_table.c.district_id == district_id)
        if status:
            stmt = stmt.where(needs_table.c.status == status)
        if urgency:
            stmt = stmt.where(needs_table.c.urgency == urgency)
        stmt = stmt.order_by(needs_table.c.created_at.desc())
        rows = self._execute_fetchall(stmt)
        return [self._row_to_need(r) for r in rows]

    def update_need(self, need: Need) -> None:
        from agent.data.schema import needs as needs_table
        stmt = update(needs_table).where(needs_table.c.id == need.id).values(
            need_type=need.need_type,
            title=need.title,
            description=need.description,
            district_id=need.district_id,
            lat=need.lat,
            lon=need.lon,
            location_name=need.location_name,
            urgency=need.urgency,
            status=need.status,
            requested_resources=need.requested_resources,
            reporter_id=need.reporter_id,
            reporter_type=need.reporter_type,
            confidence=need.confidence,
            updated_at=datetime.now(timezone.utc),
            metadata=need.metadata,
        )
        self._execute(stmt)

    def update_need_status(self, need_id: str, status: str) -> Optional[Need]:
        from agent.data.schema import needs as needs_table
        stmt = update(needs_table).where(needs_table.c.id == need_id).values(
            status=status,
            updated_at=datetime.now(timezone.utc),
        )
        self._execute(stmt)
        return self.get_need(need_id)

    # ------------------------------------------------------------------
    # Resource Offers (Phase 7B)
    # ------------------------------------------------------------------

    def create_resource_offer(self, offer: ResourceOffer) -> ResourceOffer:
        from agent.data.schema import resource_offers as offers_table
        stmt = pg_insert(offers_table).values(
            id=offer.id,
            organization_id=offer.organization_id,
            resource_type=offer.resource_type,
            quantity=offer.quantity,
            unit=offer.unit,
            lat=offer.lat,
            lon=offer.lon,
            location_name=offer.location_name,
            district_id=offer.district_id,
            status=offer.status,
            notes=offer.notes,
            metadata=offer.metadata,
        )
        self._execute(stmt)
        return offer

    def get_resource_offer(self, offer_id: str) -> Optional[ResourceOffer]:
        from agent.data.schema import resource_offers as offers_table
        row = self._execute_fetchone(
            select(offers_table).where(offers_table.c.id == offer_id)
        )
        if row is None:
            return None
        return self._row_to_resource_offer(row)

    def list_resource_offers(self, organization_id: str = None, district_id: str = None, status: str = None, resource_type: str = None) -> list[ResourceOffer]:
        from agent.data.schema import resource_offers as offers_table
        stmt = select(offers_table)
        if organization_id:
            stmt = stmt.where(offers_table.c.organization_id == organization_id)
        if district_id:
            stmt = stmt.where(offers_table.c.district_id == district_id)
        if status:
            stmt = stmt.where(offers_table.c.status == status)
        if resource_type:
            stmt = stmt.where(offers_table.c.resource_type == resource_type)
        stmt = stmt.order_by(offers_table.c.created_at.desc())
        rows = self._execute_fetchall(stmt)
        return [self._row_to_resource_offer(r) for r in rows]

    def update_resource_offer(self, offer: ResourceOffer) -> None:
        from agent.data.schema import resource_offers as offers_table
        stmt = update(offers_table).where(offers_table.c.id == offer.id).values(
            organization_id=offer.organization_id,
            resource_type=offer.resource_type,
            quantity=offer.quantity,
            unit=offer.unit,
            lat=offer.lat,
            lon=offer.lon,
            location_name=offer.location_name,
            district_id=offer.district_id,
            status=offer.status,
            notes=offer.notes,
            updated_at=datetime.now(timezone.utc),
            metadata=offer.metadata,
        )
        self._execute(stmt)

    # ------------------------------------------------------------------
    # Operations (Phase 7B)
    # ------------------------------------------------------------------

    def create_operation(self, operation: Operation) -> Operation:
        from agent.data.schema import operations as ops_table
        stmt = pg_insert(ops_table).values(
            id=operation.id,
            name=operation.name,
            operation_type=operation.operation_type,
            description=operation.description,
            need_id=operation.need_id,
            lead_organization_id=operation.lead_organization_id,
            district_id=operation.district_id,
            lat=operation.lat,
            lon=operation.lon,
            location_name=operation.location_name,
            status=operation.status,
            metadata=operation.metadata,
        )
        self._execute(stmt)
        return operation

    def get_operation(self, operation_id: str) -> Optional[Operation]:
        from agent.data.schema import operations as ops_table
        row = self._execute_fetchone(
            select(ops_table).where(ops_table.c.id == operation_id)
        )
        if row is None:
            return None
        return self._row_to_operation(row)

    def list_operations(self, district_id: str = None, status: str = None, lead_organization_id: str = None) -> list[Operation]:
        from agent.data.schema import operations as ops_table
        stmt = select(ops_table)
        if district_id:
            stmt = stmt.where(ops_table.c.district_id == district_id)
        if status:
            stmt = stmt.where(ops_table.c.status == status)
        if lead_organization_id:
            stmt = stmt.where(ops_table.c.lead_organization_id == lead_organization_id)
        stmt = stmt.order_by(ops_table.c.created_at.desc())
        rows = self._execute_fetchall(stmt)
        return [self._row_to_operation(r) for r in rows]

    def update_operation(self, operation: Operation) -> None:
        from agent.data.schema import operations as ops_table
        stmt = update(ops_table).where(ops_table.c.id == operation.id).values(
            name=operation.name,
            operation_type=operation.operation_type,
            description=operation.description,
            need_id=operation.need_id,
            lead_organization_id=operation.lead_organization_id,
            district_id=operation.district_id,
            lat=operation.lat,
            lon=operation.lon,
            location_name=operation.location_name,
            status=operation.status,
            updated_at=datetime.now(timezone.utc),
            metadata=operation.metadata,
        )
        self._execute(stmt)

    def add_operation_participant(self, operation_id: str, organization_id: str, role: str = "support") -> None:
        from agent.data.schema import operation_participants as op_table
        participant_id = f"{operation_id}_{organization_id}"
        stmt = pg_insert(op_table).values(
            id=participant_id,
            operation_id=operation_id,
            organization_id=organization_id,
            role=role,
        )
        self._execute(stmt)

    def list_operation_participants(self, operation_id: str) -> list[dict]:
        from agent.data.schema import operation_participants as op_table
        stmt = select(op_table).where(op_table.c.operation_id == operation_id)
        rows = self._execute_fetchall(stmt)
        return [{
            "operation_id": r.operation_id,
            "organization_id": r.organization_id,
            "role": r.role,
            "joined_at": r.joined_at.isoformat() if r.joined_at else None,
        } for r in rows]

    # ------------------------------------------------------------------
    # Activity Events (Phase 7B)
    # ------------------------------------------------------------------

    def append_activity_event(self, event: ActivityEvent) -> None:
        from agent.data.schema import activity_events as events_table
        stmt = pg_insert(events_table).values(
            id=event.id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            event_type=event.event_type,
            actor=event.actor,
            detail=event.detail,
            metadata=event.metadata,
        )
        self._execute(stmt)

    def list_activity_events(self, entity_type: str = None, entity_id: str = None, limit: int = 50) -> list[ActivityEvent]:
        from agent.data.schema import activity_events as events_table
        stmt = select(events_table)
        if entity_type:
            stmt = stmt.where(events_table.c.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(events_table.c.entity_id == entity_id)
        stmt = stmt.order_by(events_table.c.created_at.desc()).limit(limit)
        rows = self._execute_fetchall(stmt)
        return [self._row_to_activity_event(r) for r in rows]

    # ------------------------------------------------------------------
    # Notifications (Phase 7B)
    # ------------------------------------------------------------------

    def create_notification(self, notification: Notification) -> Notification:
        from agent.data.schema import notifications as notif_table
        stmt = pg_insert(notif_table).values(
            id=notification.id,
            recipient_id=notification.recipient_id,
            notification_type=notification.notification_type,
            title=notification.title,
            message=notification.message,
            entity_type=notification.entity_type,
            entity_id=notification.entity_id,
            read=notification.read,
            metadata=notification.metadata,
        )
        self._execute(stmt)
        return notification

    def list_notifications(self, recipient_id: str, unread_only: bool = False, limit: int = 50) -> list[Notification]:
        from agent.data.schema import notifications as notif_table
        stmt = select(notif_table).where(notif_table.c.recipient_id == recipient_id)
        if unread_only:
            stmt = stmt.where(notif_table.c.read == False)
        stmt = stmt.order_by(notif_table.c.created_at.desc()).limit(limit)
        rows = self._execute_fetchall(stmt)
        return [self._row_to_notification(r) for r in rows]

    def mark_notification_read(self, notification_id: str) -> None:
        from agent.data.schema import notifications as notif_table
        stmt = update(notif_table).where(notif_table.c.id == notification_id).values(read=True)
        self._execute(stmt)

    # ------------------------------------------------------------------
    # Row -> Model conversion helpers
    # ------------------------------------------------------------------

    def _row_to_settlement(self, row) -> Settlement:
        return Settlement(
            id=row.id,
            name=row.name,
            district_id=row.district_id,
            lat=row.lat,
            lon=row.lon,
            aliases=row.aliases or [],
            metadata=row.metadata or {},
        )

    def _row_to_flood_snapshot(self, row) -> FloodSnapshot:
        return FloodSnapshot(
            id=row.id,
            district_id=row.district_id,
            observed_at=row.observed_at,
            source=row.source,
            confidence=row.confidence,
            geometry_geojson=row.geometry_geojson,
            geometry_wkt=self._row_geometry_to_wkt(row, "geometry"),
            polygon_count=row.polygon_count,
            provenance=Provenance(row.provenance),
            source_timestamp=row.source_timestamp,
            metadata=row.metadata or {},
        )

    def _row_to_field_report(self, row) -> FieldReport:
        return FieldReport(
            id=row.id,
            district_id=row.district_id,
            lat=row.lat,
            lon=row.lon,
            source_type=row.source_type,
            raw_text=row.raw_text,
            people_count=row.people_count,
            adults=row.adults,
            children=row.children,
            elderly=row.elderly,
            needs=row.needs or [],
            location_description=row.location_description,
            verification_state=VerificationState(row.verification_state),
            extraction_confidence=row.extraction_confidence,
            observed_at=row.observed_at,
            ingested_at=row.ingested_at,
            provenance=Provenance(row.provenance),
            metadata=row.metadata or {},
        )

    def _row_to_override(self, row) -> Override:
        return Override(
            id=row.id,
            target_type=row.target_type,
            target_id=row.target_id,
            override_status=row.override_status,
            reason=row.reason,
            actor=row.actor,
            system_status=row.system_status,
            active=row.active,
            created_at=row.created_at,
        )

    def _row_to_building(self, row) -> Building:
        return Building(
            id=row.id,
            district_id=row.district_id,
            osm_id=row.osm_id,
            lat=row.lat,
            lon=row.lon,
            tags=row.tags or {},
            in_flood_zone=row.in_flood_zone,
            provenance=Provenance(row.provenance),
        )

    def _row_to_medical_facility(self, row) -> MedicalFacility:
        return MedicalFacility(
            id=row.id,
            district_id=row.district_id,
            name=row.name,
            lat=row.lat,
            lon=row.lon,
            facility_type=row.facility_type,
            osm_id=row.osm_id,
            provenance=Provenance(row.provenance),
        )

    def _row_to_road(self, row) -> Road:
        # Extract geometry coordinates from PostGIS if available
        geometry_coords = []
        geometry_wkt = getattr(row, 'geometry_wkt', None)
        if geometry_wkt:
            geometry_coords = _parse_linestring_coords(geometry_wkt)
        else:
            geom = getattr(row, 'geometry', None)
        if not geometry_coords and geom is not None:
            try:
                from geoalchemy2 import WKBElement
                if isinstance(geom, WKBElement):
                    with self._engine.connect() as conn:
                        result = conn.execute(
                            text("SELECT ST_AsText(:geom)"), {"geom": geom}
                        )
                        wkt_row = result.fetchone()
                        if wkt_row and wkt_row[0]:
                            geometry_coords = _parse_linestring_coords(wkt_row[0])
            except Exception:
                pass

        r = Road(
            id=row.id,
            district_id=row.district_id,
            name=row.name,
            highway_type=row.highway_type,
            osm_id=row.osm_id,
            geometry_coords=geometry_coords,
            flood_affected=row.flood_affected,
            provenance=Provenance(row.provenance),
        )
        r.tags = getattr(row, 'tags', {}) or {}
        r.is_bridge = getattr(row, 'is_bridge', False)
        return r

    # --- Phase 7B row converters ---

    def _row_to_organization(self, row) -> Organization:
        return Organization(
            id=row.id,
            name=row.name,
            organization_type=row.organization_type,
            description=row.description,
            published_capabilities=row.published_capabilities or [],
            public_contact=row.public_contact or {},
            active=row.active,
            created_at=row.created_at,
            metadata=row.metadata or {},
        )

    def _row_to_need(self, row) -> Need:
        return Need(
            id=row.id,
            need_type=row.need_type,
            title=row.title,
            description=row.description,
            district_id=row.district_id,
            lat=row.lat,
            lon=row.lon,
            location_name=row.location_name,
            urgency=row.urgency,
            status=row.status,
            requested_resources=row.requested_resources or [],
            reporter_id=row.reporter_id,
            reporter_type=row.reporter_type,
            confidence=row.confidence,
            created_at=row.created_at,
            updated_at=row.updated_at,
            metadata=row.metadata or {},
        )

    def _row_to_resource_offer(self, row) -> ResourceOffer:
        return ResourceOffer(
            id=row.id,
            organization_id=row.organization_id,
            resource_type=row.resource_type,
            quantity=row.quantity,
            unit=row.unit,
            lat=row.lat,
            lon=row.lon,
            location_name=row.location_name,
            district_id=row.district_id,
            status=row.status,
            notes=row.notes,
            created_at=row.created_at,
            updated_at=row.updated_at,
            metadata=row.metadata or {},
        )

    def _row_to_operation(self, row) -> Operation:
        return Operation(
            id=row.id,
            name=row.name,
            operation_type=row.operation_type,
            description=row.description,
            need_id=row.need_id,
            lead_organization_id=row.lead_organization_id,
            district_id=row.district_id,
            lat=row.lat,
            lon=row.lon,
            location_name=row.location_name,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
            metadata=row.metadata or {},
        )

    def _row_to_activity_event(self, row) -> ActivityEvent:
        return ActivityEvent(
            id=row.id,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            event_type=row.event_type,
            actor=row.actor,
            detail=row.detail,
            created_at=row.created_at,
            metadata=row.metadata or {},
        )

    def _row_to_notification(self, row) -> Notification:
        return Notification(
            id=row.id,
            recipient_id=row.recipient_id,
            notification_type=row.notification_type,
            title=row.title,
            message=row.message,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            read=row.read,
            created_at=row.created_at,
            metadata=row.metadata or {},
        )

    def _row_geometry_to_wkt(self, row, col_name: str) -> Optional[str]:
        """Extract WKT from a PostGIS geometry column."""
        geom = getattr(row, col_name, None)
        if geom is None:
            return None
        try:
            # The geom is a WKBElement from GeoAlchemy2
            # Use ST_AsText to convert to WKT via a direct query
            with self._engine.connect() as conn:
                # Use the WKB element directly with ST_AsText
                from geoalchemy2 import WKBElement
                if isinstance(geom, WKBElement):
                    result = conn.execute(
                        text("SELECT ST_AsText(:geom)"),
                        {"geom": geom}
                    )
                else:
                    # Fallback for string geometry
                    result = conn.execute(
                        text("SELECT ST_AsText(:geom::geometry)"),
                        {"geom": str(geom)}
                    )
                r = result.fetchone()
                return r[0] if r else None
        except Exception:
            return None

    def _geojson_to_multipolygon_sql(self, geojson: dict):
        """
        Convert a GeoJSON FeatureCollection to a PostGIS MultiPolygon WKT string
        that can be used in an INSERT statement.
        """
        features = geojson.get("features", [])
        if not features:
            return None

        # Collect all polygon coordinates
        all_polygon_coords = []
        for feature in features:
            geom = feature.get("geometry", {})
            geom_type = geom.get("type", "")
            coords = geom.get("coordinates", [])

            if geom_type == "Polygon":
                all_polygon_coords.append(coords)
            elif geom_type == "MultiPolygon":
                all_polygon_coords.extend(coords)

        if not all_polygon_coords:
            return None

        # Build WKT for MultiPolygon
        polygon_wkts = []
        for poly_coords in all_polygon_coords:
            rings = []
            for ring in poly_coords:
                points = ", ".join(f"{c[0]} {c[1]}" for c in ring)
                rings.append(f"({points})")
            polygon_wkts.append(f"({', '.join(rings)})")

        if len(polygon_wkts) == 1:
            wkt = f"SRID={SRID};POLYGON{polygon_wkts[0]}"
        else:
            wkt = f"SRID={SRID};MULTIPOLYGON({', '.join(polygon_wkts)})"

        return wkt


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _names_match(a: str, b: str) -> bool:
    """Case-insensitive substring matching (same as InMemoryRepository)."""
    a_low = a.strip().lower()
    b_low = b.strip().lower()
    if a_low == b_low:
        return True
    if a_low in b_low or b_low in a_low:
        shorter, longer = (a_low, b_low) if len(a_low) <= len(b_low) else (b_low, a_low)
        if longer.startswith(shorter) and (len(shorter) == len(longer) or longer[len(shorter)] == ' '):
            return True
        if len(shorter) > len(longer) / 2:
            return True
    return False


def _parse_linestring_coords(wkt: str) -> list[list[float]]:
    """Parse a WKT LINESTRING or MULTILINESTRING into a flat list of [lon, lat] coords.

    For MULTILINESTRING, returns the coordinates of the first linestring.
    """
    if not wkt:
        return []

    wkt = wkt.strip()

    # Handle MULTILINESTRING(((lon lat, ...)))
    if wkt.startswith("MULTILINESTRING"):
        # Extract first linestring from MULTILINESTRING(((...), (...)))
        inner = wkt[len("MULTILINESTRING"):].strip()
        # Remove leading/trailing parens to get inner linestrings
        if inner.startswith("(("):
            inner = inner[1:]  # Remove one leading (
        # Find first closing paren of first linestring
        end = inner.find(")")
        if end > 0:
            inner = inner[1:end]  # Skip opening (
        else:
            inner = inner[1:]
        wkt = inner
    elif wkt.startswith("LINESTRING"):
        wkt = wkt[len("LINESTRING"):].strip()
        if wkt.startswith("("):
            wkt = wkt[1:]
        if wkt.endswith(")"):
            wkt = wkt[:-1]

    # Parse "lon1 lat1, lon2 lat2, ..."
    coords = []
    for pair in wkt.split(","):
        pair = pair.strip()
        parts = pair.split()
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                coords.append([lon, lat])
            except ValueError:
                continue

    return coords
