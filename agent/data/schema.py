"""
Phase 5A: SQLAlchemy Schema for PostgreSQL + PostGIS

Defines all database tables using SQLAlchemy Core (not ORM).
Uses GeoAlchemy2 for spatial column types.

Tables:
- districts: Administrative districts with boundary geometry
- settlements: Known locations within districts (Point geometry)
- flood_snapshots: Temporal flood observations (MultiPolygon geometry)
- field_reports: Community/field intelligence reports (Point geometry)
- overrides: Manual status overrides by coordinators
- buildings: OSM/Overpass building data (Point geometry)
- medical_facilities: OSM/Overpass medical facilities (Point geometry)
- roads: OSM/Overpass road data (LineString/MultiLineString geometry)

Design:
- WGS84 / EPSG:4326 for all spatial columns
- JSONB for flexible metadata/aliases/tags fields
- Foreign keys for district_id references
- Provenance stored as VARCHAR with check constraints
- VerificationState stored as VARCHAR with check constraints
- Spatial indexes on all geometry columns
- Indexes on frequently-queried columns (district_id, observed_at, etc.)
"""

import os
from sqlalchemy import (
    create_engine, MetaData, Table, Column, String, Float, Integer, BigInteger,
    Boolean, DateTime, Text, JSON, ForeignKey, Index, CheckConstraint,
    text,
)
from geoalchemy2 import Geometry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SRID = 4326  # WGS84

PROVENANCE_VALUES = ("REAL", "DERIVED", "SYNTHETIC", "MANUAL_OVERRIDE")
VERIFICATION_VALUES = ("UNVERIFIED", "VERIFIED", "DISPUTED")

# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

metadata = MetaData()

# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

districts = Table(
    "districts",
    metadata,
    Column("id", String(128), primary_key=True),
    Column("name", String(256), nullable=False),
    Column("state", String(256), nullable=False, server_default=""),
    Column("country", String(256), nullable=False, server_default="India"),
    Column("geometry", Geometry("Polygon", srid=SRID), nullable=True),
    Column("metadata", JSON, nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
)

settlements = Table(
    "settlements",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("name", String(512), nullable=False),
    Column("district_id", String(128), ForeignKey("districts.id", ondelete="CASCADE"), nullable=False),
    Column("lat", Float, nullable=False),
    Column("lon", Float, nullable=False),
    Column("aliases", JSON, nullable=False, server_default="[]"),
    Column("metadata", JSON, nullable=False, server_default="{}"),
    Column("location", Geometry("Point", srid=SRID), nullable=True),
    Index("ix_settlements_district_id", "district_id"),
    Index("ix_settlements_location", "location", postgresql_using="gist"),
)

flood_snapshots = Table(
    "flood_snapshots",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("district_id", String(128), ForeignKey("districts.id", ondelete="CASCADE"), nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("source", String(512), nullable=False, server_default=""),
    Column("confidence", Float, nullable=False, server_default="1.0"),
    Column("geometry", Geometry("MultiPolygon", srid=SRID), nullable=True),
    Column("geometry_geojson", JSON, nullable=True),
    Column("polygon_count", Integer, nullable=False, server_default="0"),
    Column("provenance", String(64), nullable=False, server_default="REAL"),
    Column("source_timestamp", DateTime(timezone=True), nullable=True),
    Column("metadata", JSON, nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Index("ix_flood_snapshots_district_id", "district_id"),
    Index("ix_flood_snapshots_observed_at", "observed_at"),
    Index("ix_flood_snapshots_geometry", "geometry", postgresql_using="gist"),
    CheckConstraint(f"provenance IN ({', '.join(repr(v) for v in PROVENANCE_VALUES)})",
                    name="ck_flood_snapshots_provenance"),
)

field_reports = Table(
    "field_reports",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("district_id", String(128), ForeignKey("districts.id", ondelete="SET NULL"), nullable=True),
    Column("lat", Float, nullable=True),
    Column("lon", Float, nullable=True),
    Column("location", Geometry("Point", srid=SRID), nullable=True),
    Column("source_type", String(128), nullable=False, server_default="community_report"),
    Column("raw_text", Text, nullable=False, server_default=""),
    Column("people_count", Integer, nullable=False, server_default="0"),
    Column("adults", Integer, nullable=False, server_default="0"),
    Column("children", Integer, nullable=False, server_default="0"),
    Column("elderly", Integer, nullable=False, server_default="0"),
    Column("needs", JSON, nullable=False, server_default="[]"),
    Column("location_description", String(512), nullable=True),
    Column("verification_state", String(64), nullable=False, server_default="UNVERIFIED"),
    Column("extraction_confidence", String(64), nullable=False, server_default="low"),
    Column("observed_at", DateTime(timezone=True), nullable=True),
    Column("ingested_at", DateTime(timezone=True), nullable=True),
    Column("provenance", String(64), nullable=False, server_default="REAL"),
    Column("metadata", JSON, nullable=False, server_default="{}"),
    Index("ix_field_reports_district_id", "district_id"),
    Index("ix_field_reports_location", "location", postgresql_using="gist"),
    CheckConstraint(f"provenance IN ({', '.join(repr(v) for v in PROVENANCE_VALUES)})",
                    name="ck_field_reports_provenance"),
    CheckConstraint(f"verification_state IN ({', '.join(repr(v) for v in VERIFICATION_VALUES)})",
                    name="ck_field_reports_verification_state"),
)

overrides = Table(
    "overrides",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("target_type", String(128), nullable=False),
    Column("target_id", String(512), nullable=False),
    Column("override_status", String(128), nullable=False),
    Column("reason", Text, nullable=False, server_default=""),
    Column("actor", String(128), nullable=False, server_default="coordinator"),
    Column("system_status", String(128), nullable=False, server_default="unknown"),
    Column("active", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Index("ix_overrides_target", "target_type", "target_id"),
    Index("ix_overrides_active", "active"),
)

buildings = Table(
    "buildings",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("district_id", String(128), ForeignKey("districts.id", ondelete="CASCADE"), nullable=False),
    Column("osm_id", BigInteger, nullable=True),
    Column("lat", Float, nullable=False, server_default="0.0"),
    Column("lon", Float, nullable=False, server_default="0.0"),
    Column("location", Geometry("Point", srid=SRID), nullable=True),
    Column("geometry", Geometry("Polygon", srid=SRID), nullable=True),
    Column("tags", JSON, nullable=False, server_default="{}"),
    Column("in_flood_zone", Boolean, nullable=False, server_default="false"),
    Column("provenance", String(64), nullable=False, server_default="REAL"),
    Index("ix_buildings_district_id", "district_id"),
    Index("ix_buildings_location", "location", postgresql_using="gist"),
    Index("ix_buildings_geometry", "geometry", postgresql_using="gist"),
    CheckConstraint(f"provenance IN ({', '.join(repr(v) for v in PROVENANCE_VALUES)})",
                    name="ck_buildings_provenance"),
)

medical_facilities = Table(
    "medical_facilities",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("district_id", String(128), ForeignKey("districts.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(512), nullable=False),
    Column("lat", Float, nullable=False),
    Column("lon", Float, nullable=False),
    Column("location", Geometry("Point", srid=SRID), nullable=True),
    Column("facility_type", String(128), nullable=False, server_default="hospital"),
    Column("osm_id", BigInteger, nullable=True),
    Column("provenance", String(64), nullable=False, server_default="REAL"),
    Index("ix_medical_facilities_district_id", "district_id"),
    Index("ix_medical_facilities_location", "location", postgresql_using="gist"),
    CheckConstraint(f"provenance IN ({', '.join(repr(v) for v in PROVENANCE_VALUES)})",
                    name="ck_medical_facilities_provenance"),
)

roads = Table(
    "roads",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("district_id", String(128), ForeignKey("districts.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(512), nullable=True),
    Column("highway_type", String(128), nullable=False, server_default="unclassified"),
    Column("osm_id", BigInteger, nullable=True),
    Column("geometry", Geometry("MultiLineString", srid=SRID), nullable=True),
    Column("flood_affected", Boolean, nullable=False, server_default="false"),
    Column("provenance", String(64), nullable=False, server_default="REAL"),
    Column("tags", JSON, nullable=False, server_default="{}"),
    Column("is_bridge", Boolean, nullable=False, server_default="false"),
    Index("ix_roads_district_id", "district_id"),
    Index("ix_roads_geometry", "geometry", postgresql_using="gist"),
    CheckConstraint(f"provenance IN ({', '.join(repr(v) for v in PROVENANCE_VALUES)})",
                    name="ck_roads_provenance"),
)


# ---------------------------------------------------------------------------
# Phase 7B: Shared Operational Objects
# ---------------------------------------------------------------------------

organizations = Table(
    "organizations",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("name", String(512), nullable=False),
    Column("organization_type", String(128), nullable=False, server_default="ngo"),
    Column("description", Text, nullable=False, server_default=""),
    Column("published_capabilities", JSON, nullable=False, server_default="[]"),
    Column("public_contact", JSON, nullable=False, server_default="{}"),
    Column("active", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("metadata", JSON, nullable=False, server_default="{}"),
)

needs = Table(
    "needs",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("need_type", String(128), nullable=False),
    Column("title", String(512), nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("district_id", String(128), ForeignKey("districts.id", ondelete="SET NULL"), nullable=True),
    Column("lat", Float, nullable=True),
    Column("lon", Float, nullable=True),
    Column("location_name", String(512), nullable=True),
    Column("urgency", String(64), nullable=False, server_default="medium"),
    Column("status", String(64), nullable=False, server_default="OPEN"),
    Column("requested_resources", JSON, nullable=False, server_default="[]"),
    Column("reporter_id", String(256), nullable=True),
    Column("reporter_type", String(128), nullable=False, server_default="coordinator"),
    Column("confidence", Float, nullable=False, server_default="0.5"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("metadata", JSON, nullable=False, server_default="{}"),
    Index("ix_needs_district_id", "district_id"),
    Index("ix_needs_status", "status"),
    Index("ix_needs_urgency", "urgency"),
    CheckConstraint(
        "status IN ('OPEN', 'UNDER_REVIEW', 'RESPONDING', 'PARTIALLY_RESOLVED', 'RESOLVED', 'CLOSED')",
        name="ck_needs_status"
    ),
    CheckConstraint(
        "urgency IN ('critical', 'high', 'medium', 'low')",
        name="ck_needs_urgency"
    ),
)

resource_offers = Table(
    "resource_offers",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("organization_id", String(256), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
    Column("resource_type", String(128), nullable=False),
    Column("quantity", Integer, nullable=False, server_default="0"),
    Column("unit", String(64), nullable=False, server_default="units"),
    Column("lat", Float, nullable=True),
    Column("lon", Float, nullable=True),
    Column("location_name", String(512), nullable=True),
    Column("district_id", String(128), ForeignKey("districts.id", ondelete="SET NULL"), nullable=True),
    Column("status", String(64), nullable=False, server_default="OFFERED"),
    Column("notes", Text, nullable=False, server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("metadata", JSON, nullable=False, server_default="{}"),
    Index("ix_resource_offers_org_id", "organization_id"),
    Index("ix_resource_offers_status", "status"),
    Index("ix_resource_offers_district_id", "district_id"),
    CheckConstraint(
        "status IN ('OFFERED', 'ACCEPTED', 'DEPLOYED', 'WITHDRAWN', 'EXPIRED')",
        name="ck_resource_offers_status"
    ),
)

operations = Table(
    "operations",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("name", String(512), nullable=False),
    Column("operation_type", String(128), nullable=False, server_default="other"),
    Column("description", Text, nullable=False, server_default=""),
    Column("need_id", String(256), ForeignKey("needs.id", ondelete="SET NULL"), nullable=True),
    Column("lead_organization_id", String(256), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
    Column("district_id", String(128), ForeignKey("districts.id", ondelete="SET NULL"), nullable=True),
    Column("lat", Float, nullable=True),
    Column("lon", Float, nullable=True),
    Column("location_name", String(512), nullable=True),
    Column("status", String(64), nullable=False, server_default="PLANNING"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("metadata", JSON, nullable=False, server_default="{}"),
    Index("ix_operations_district_id", "district_id"),
    Index("ix_operations_status", "status"),
    Index("ix_operations_lead_org_id", "lead_organization_id"),
    CheckConstraint(
        "status IN ('PLANNING', 'ACTIVE', 'PAUSED', 'COMPLETED', 'CANCELLED')",
        name="ck_operations_status"
    ),
)

operation_participants = Table(
    "operation_participants",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("operation_id", String(256), ForeignKey("operations.id", ondelete="CASCADE"), nullable=False),
    Column("organization_id", String(256), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
    Column("role", String(128), nullable=False, server_default="support"),
    Column("joined_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Index("ix_operation_participants_operation_id", "operation_id"),
    Index("ix_operation_participants_org_id", "organization_id"),
)

activity_events = Table(
    "activity_events",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("entity_type", String(128), nullable=False),
    Column("entity_id", String(256), nullable=False),
    Column("event_type", String(128), nullable=False),
    Column("actor", String(256), nullable=False, server_default=""),
    Column("detail", Text, nullable=False, server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("metadata", JSON, nullable=False, server_default="{}"),
    Index("ix_activity_events_entity", "entity_type", "entity_id"),
    Index("ix_activity_events_created_at", "created_at"),
)

notifications = Table(
    "notifications",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("recipient_id", String(256), nullable=False),
    Column("notification_type", String(128), nullable=False),
    Column("title", String(512), nullable=False),
    Column("message", Text, nullable=False, server_default=""),
    Column("entity_type", String(128), nullable=True),
    Column("entity_id", String(256), nullable=True),
    Column("read", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("metadata", JSON, nullable=False, server_default="{}"),
    Index("ix_notifications_recipient_id", "recipient_id"),
    Index("ix_notifications_read", "read"),
    Index("ix_notifications_created_at", "created_at"),
)

# Item #5 Step 2: Coordination proposals (Phase 7H) — migrated from the
# file-backed JSON store (agent/data/coordination_proposals.json) to the
# single authoritative PostgreSQL source.
#
# Privacy note: org_evaluation / private_factors hold NGO-PRIVATE evaluation
# state (mirroring the previous JSON schema). They are stored server-side
# only — every network-facing response must go through the explicit public
# projection in agent/coordination/proposal.py::get_public_view, never
# through a raw row dump.
#
# No FKs on need_id / organization_id / published_offer_id / operation_id:
# proposals may legitimately reference objects that are not (yet) registered
# rows (e.g. targeting an org id string, ephemeral need payloads). Reference
# integrity is the domain layer's concern; indexes match actual queries.
coordination_proposals = Table(
    "coordination_proposals",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("need_id", String(256), nullable=True),
    Column("organization_id", String(256), nullable=False),
    Column("organization_name", String(512), nullable=True),
    Column("proposal_type", String(128), nullable=False),
    Column("summary", Text, nullable=False, server_default=""),
    Column("public_evidence", JSON, nullable=False, server_default="[]"),
    Column("network_findings", JSON, nullable=False, server_default="[]"),
    Column("constraints", JSON, nullable=False, server_default="[]"),
    Column("uncertainty", JSON, nullable=False, server_default="[]"),
    Column("recommended_action", Text, nullable=False, server_default=""),
    Column("status", String(64), nullable=False, server_default="PROPOSED"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("approved_at", DateTime(timezone=True), nullable=True),
    Column("approved_by", String(256), nullable=True),
    Column("published_offer_id", String(256), nullable=True),
    Column("operation_id", String(256), nullable=True),
    Column("org_evaluation", JSON, nullable=True),   # PRIVATE — never in public projections
    Column("private_factors", JSON, nullable=True),  # PRIVATE — never in public projections
    Index("ix_coordination_proposals_org_id", "organization_id"),
    Index("ix_coordination_proposals_need_id", "need_id"),
    Index("ix_coordination_proposals_status", "status"),
    Index("ix_coordination_proposals_created_at", "created_at"),
    CheckConstraint(
        "status IN ('PROPOSED', 'PENDING_ORG_REVIEW', 'ORG_RECOMMENDED', "
        "'PENDING_HUMAN_APPROVAL', 'PUBLISHED', 'CONFIRMED', 'COMPLETED', "
        "'DECLINED', 'EXPIRED')",
        name="ck_coordination_proposals_status"
    ),
)


# ---------------------------------------------------------------------------
# Engine / helpers
# ---------------------------------------------------------------------------

def get_engine(database_url: str = None):
    """Create a SQLAlchemy engine from DATABASE_URL env var or explicit arg."""
    if database_url is None:
        database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise ValueError(
            "DATABASE_URL is not set. "
            "Set the DATABASE_URL environment variable or pass database_url explicitly."
        )
    return create_engine(database_url, echo=False, pool_pre_ping=True)


def create_all_tables(engine):
    """Create all tables (idempotent)."""
    metadata.create_all(engine)


def drop_all_tables(engine):
    """Drop all tables (for testing)."""
    metadata.drop_all(engine)


# ---------------------------------------------------------------------------
# CLI: python -m agent.data.schema
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set.")
        print("Usage: DATABASE_URL=postgresql://... python -m agent.data.schema")
        sys.exit(1)
    engine = get_engine(url)
    create_all_tables(engine)
    print(f"Tables created successfully on {url.split('@')[-1] if '@' in url else url}")
