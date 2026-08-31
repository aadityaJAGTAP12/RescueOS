"""
Phase 3: Generalized Data Models

Defines normalized schemas for all ReliefOS entities. These are the
single source of truth for data shapes — tools, API, and storage
all use these definitions.

Key design decisions:
- Dataclasses for clean, typed, serializable models
- Provenance enum to track data origin (REAL/DERIVED/SYNTHETIC/MANUAL_OVERRIDE)
- Temporal flood model (district + date + geometry)
- District-independent location resolution
- No ORM dependency — plain Python dataclasses
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

class Provenance(str, Enum):
    """Every observation carries a provenance tag."""
    REAL = "REAL"                    # imported from external source (e.g. Sentinel-1)
    DERIVED = "DERIVED"              # computed from other data (e.g. PDC score)
    SYNTHETIC = "SYNTHETIC"          # created for testing/demo
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"  # coordinator manual override


class VerificationState(str, Enum):
    """Verification status for field reports."""
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"


# ---------------------------------------------------------------------------
# Administrative Geography
# ---------------------------------------------------------------------------

class District:
    """A geographic district (e.g. Sivasagar, Jorhat)."""
    def __init__(
        self,
        id: str,
        name: str,
        state: str = "",
        country: str = "India",
        geometry_wkt: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        self.id = id
        self.name = name
        self.state = state
        self.country = country
        self.geometry_wkt = geometry_wkt  # WKT polygon for PostGIS (optional)
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "country": self.country,
            "geometry_wkt": self.geometry_wkt,
            "metadata": self.metadata,
        }


class Settlement:
    """A known settlement or location within a district."""
    def __init__(
        self,
        id: str,
        name: str,
        district_id: str,
        lat: float,
        lon: float,
        aliases: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ):
        self.id = id
        self.name = name
        self.district_id = district_id
        self.lat = lat
        self.lon = lon
        self.aliases = aliases or []
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "district_id": self.district_id,
            "lat": self.lat,
            "lon": self.lon,
            "aliases": self.aliases,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Flood Intelligence
# ---------------------------------------------------------------------------

class FloodSnapshot:
    """
    A temporal flood observation: district + date + geometry.

    This is the core of the temporal flood model. A flood is NOT one
    permanent polygon — it's a series of snapshots over time.
    """
    def __init__(
        self,
        id: str,
        district_id: str,
        observed_at: datetime,
        source: str,
        confidence: float = 1.0,
        geometry_geojson: Optional[dict] = None,
        geometry_wkt: Optional[str] = None,
        polygon_count: int = 0,
        provenance: Provenance = Provenance.REAL,
        source_timestamp: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ):
        self.id = id
        self.district_id = district_id
        self.observed_at = observed_at
        self.source = source
        self.confidence = confidence
        self.geometry_geojson = geometry_geojson  # full GeoJSON FeatureCollection
        self.geometry_wkt = geometry_wkt  # for PostGIS storage
        self.polygon_count = polygon_count
        self.provenance = provenance
        self.source_timestamp = source_timestamp
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "district_id": self.district_id,
            "observed_at": self.observed_at.isoformat(),
            "source": self.source,
            "confidence": self.confidence,
            "geometry_geojson": self.geometry_geojson,
            "polygon_count": self.polygon_count,
            "provenance": self.provenance.value,
            "source_timestamp": self.source_timestamp.isoformat() if self.source_timestamp else None,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

class Building:
    """A building from OSM/Overpass data."""
    def __init__(
        self,
        id: str,
        district_id: str,
        osm_id: Optional[int] = None,
        lat: float = 0.0,
        lon: float = 0.0,
        tags: Optional[dict] = None,
        in_flood_zone: bool = False,
        provenance: Provenance = Provenance.REAL,
        geometry_wkt: Optional[str] = None,
    ):
        self.id = id
        self.district_id = district_id
        self.osm_id = osm_id
        self.lat = lat
        self.lon = lon
        self.tags = tags or {}
        self.in_flood_zone = in_flood_zone
        self.provenance = provenance
        self.geometry_wkt = geometry_wkt


class MedicalFacility:
    """A medical facility (hospital/clinic) from OSM/Overpass data."""
    def __init__(
        self,
        id: str,
        district_id: str,
        name: str,
        lat: float,
        lon: float,
        facility_type: str = "hospital",
        osm_id: Optional[int] = None,
        provenance: Provenance = Provenance.REAL,
    ):
        self.id = id
        self.district_id = district_id
        self.name = name
        self.lat = lat
        self.lon = lon
        self.facility_type = facility_type
        self.osm_id = osm_id
        self.provenance = provenance

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "district_id": self.district_id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "facility_type": self.facility_type,
            "provenance": self.provenance.value,
        }


class Road:
    """A road from OSM/Overpass data."""
    def __init__(
        self,
        id: str,
        district_id: str,
        name: Optional[str] = None,
        highway_type: str = "unclassified",
        osm_id: Optional[int] = None,
        geometry_coords: Optional[list] = None,
        flood_affected: bool = False,
        provenance: Provenance = Provenance.REAL,
        tags: Optional[dict] = None,
        is_bridge: bool = False,
    ):
        self.id = id
        self.district_id = district_id
        self.name = name
        self.highway_type = highway_type
        self.osm_id = osm_id
        self.geometry_coords = geometry_coords or []
        self.flood_affected = flood_affected
        self.provenance = provenance
        self.tags = tags or {}
        self.is_bridge = is_bridge


# ---------------------------------------------------------------------------
# Field Intelligence
# ---------------------------------------------------------------------------

class FieldReport:
    """A community or field report — self-reported observation."""
    def __init__(
        self,
        id: str,
        district_id: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        source_type: str = "community_report",
        raw_text: str = "",
        people_count: int = 0,
        adults: int = 0,
        children: int = 0,
        elderly: int = 0,
        needs: Optional[list[str]] = None,
        location_description: Optional[str] = None,
        verification_state: VerificationState = VerificationState.UNVERIFIED,
        extraction_confidence: str = "low",
        observed_at: Optional[datetime] = None,
        ingested_at: Optional[datetime] = None,
        provenance: Provenance = Provenance.REAL,
        metadata: Optional[dict] = None,
    ):
        self.id = id
        self.district_id = district_id
        self.lat = lat
        self.lon = lon
        self.source_type = source_type
        self.raw_text = raw_text
        self.people_count = people_count
        self.adults = adults
        self.children = children
        self.elderly = elderly
        self.needs = needs or []
        self.location_description = location_description
        self.verification_state = verification_state
        self.extraction_confidence = extraction_confidence
        self.observed_at = observed_at or datetime.now(timezone.utc)
        self.ingested_at = ingested_at or datetime.now(timezone.utc)
        self.provenance = provenance
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "district_id": self.district_id,
            "lat": self.lat,
            "lon": self.lon,
            "source_type": self.source_type,
            "raw_text": self.raw_text,
            "people_count": self.people_count,
            "adults": self.adults,
            "children": self.children,
            "elderly": self.elderly,
            "needs": self.needs,
            "location_description": self.location_description,
            "verification_state": self.verification_state.value,
            "extraction_confidence": self.extraction_confidence,
            "observed_at": self.observed_at.isoformat(),
            "ingested_at": self.ingested_at.isoformat(),
            "provenance": self.provenance.value,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Operational State
# ---------------------------------------------------------------------------

class Override:
    """A manual status override by a coordinator."""
    def __init__(
        self,
        id: str,
        target_type: str,
        target_id: str,
        override_status: str,
        reason: str = "",
        actor: str = "coordinator",
        system_status: str = "unknown",
        active: bool = True,
        created_at: Optional[datetime] = None,
    ):
        self.id = id
        self.target_type = target_type
        self.target_id = target_id
        self.override_status = override_status
        self.reason = reason
        self.actor = actor
        self.system_status = system_status
        self.active = active
        self.created_at = created_at or datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "override_status": self.override_status,
            "reason": self.reason,
            "actor": self.actor,
            "system_status": self.system_status,
            "active": self.active,
            "timestamp": self.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Query Contracts
# ---------------------------------------------------------------------------

class QueryRequest:
    """A structured query from a coordinator."""
    def __init__(
        self,
        id: Optional[str] = None,
        query_type: str = "assessment",
        locations: Optional[list[dict]] = None,
        timestamp: Optional[datetime] = None,
        constraints: Optional[dict] = None,
        resources: Optional[list[dict]] = None,
        raw_input: str = "",
        source: str = "api",
    ):
        self.id = id or str(uuid.uuid4())[:8]
        self.query_type = query_type
        self.locations = locations or []
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.constraints = constraints or {}
        self.resources = resources or []
        self.raw_input = raw_input
        self.source = source

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "query_type": self.query_type,
            "locations": self.locations,
            "timestamp": self.timestamp.isoformat(),
            "constraints": self.constraints,
            "resources": self.resources,
            "raw_input": self.raw_input,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Shared Operational Objects (Phase 7B)
# ---------------------------------------------------------------------------

class Organization:
    """An organization participating in the relief network."""
    def __init__(
        self,
        id: str,
        name: str,
        organization_type: str = "ngo",
        description: str = "",
        published_capabilities: Optional[list[str]] = None,
        public_contact: Optional[dict] = None,
        active: bool = True,
        created_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ):
        self.id = id
        self.name = name
        self.organization_type = organization_type  # "ngo" | "government" | "military" | "community" | "other"
        self.description = description
        self.published_capabilities = published_capabilities or []
        self.public_contact = public_contact or {}
        self.active = active
        self.created_at = created_at or datetime.now(timezone.utc)
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "organization_type": self.organization_type,
            "description": self.description,
            "published_capabilities": self.published_capabilities,
            "public_contact": self.public_contact,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


class Need:
    """A shared need in the relief network."""
    def __init__(
        self,
        id: str,
        need_type: str,
        title: str,
        description: str = "",
        district_id: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        location_name: Optional[str] = None,
        urgency: str = "medium",
        status: str = "OPEN",
        requested_resources: Optional[list[dict]] = None,
        reporter_id: Optional[str] = None,
        reporter_type: str = "coordinator",
        confidence: float = 0.5,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ):
        self.id = id
        self.need_type = need_type  # "food" | "water" | "medical" | "shelter" | "transport" | "rescue" | "other"
        self.title = title
        self.description = description
        self.district_id = district_id
        self.lat = lat
        self.lon = lon
        self.location_name = location_name
        self.urgency = urgency  # "critical" | "high" | "medium" | "low"
        self.status = status  # "OPEN" | "UNDER_REVIEW" | "RESPONDING" | "PARTIALLY_RESOLVED" | "RESOLVED" | "CLOSED"
        self.requested_resources = requested_resources or []
        self.reporter_id = reporter_id
        self.reporter_type = reporter_type  # "coordinator" | "field_team" | "community" | "ai_detector"
        self.confidence = confidence
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "need_type": self.need_type,
            "title": self.title,
            "description": self.description,
            "district_id": self.district_id,
            "lat": self.lat,
            "lon": self.lon,
            "location_name": self.location_name,
            "urgency": self.urgency,
            "status": self.status,
            "requested_resources": self.requested_resources,
            "reporter_id": self.reporter_id,
            "reporter_type": self.reporter_type,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


class ResourceOffer:
    """A published resource offer from an organization."""
    def __init__(
        self,
        id: str,
        organization_id: str,
        resource_type: str,
        quantity: int = 0,
        unit: str = "units",
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        location_name: Optional[str] = None,
        district_id: Optional[str] = None,
        status: str = "OFFERED",
        notes: str = "",
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ):
        self.id = id
        self.organization_id = organization_id
        self.resource_type = resource_type  # "boat" | "medical_team" | "food" | "water" | "shelter" | "vehicle" | "personnel" | "other"
        self.quantity = quantity
        self.unit = unit  # "units" | "people" | "kg" | "liters" | "kits"
        self.lat = lat
        self.lon = lon
        self.location_name = location_name
        self.district_id = district_id
        self.status = status  # "OFFERED" | "ACCEPTED" | "DEPLOYED" | "WITHDRAWN" | "EXPIRED"
        self.notes = notes
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "resource_type": self.resource_type,
            "quantity": self.quantity,
            "unit": self.unit,
            "lat": self.lat,
            "lon": self.lon,
            "location_name": self.location_name,
            "district_id": self.district_id,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


class Operation:
    """A coordinated response action."""
    def __init__(
        self,
        id: str,
        name: str,
        operation_type: str = "other",
        description: str = "",
        need_id: Optional[str] = None,
        lead_organization_id: Optional[str] = None,
        district_id: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        location_name: Optional[str] = None,
        status: str = "PLANNING",
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ):
        self.id = id
        self.name = name
        self.operation_type = operation_type  # "rescue" | "medical" | "supply_delivery" | "evacuation" | "assessment" | "other"
        self.description = description
        self.need_id = need_id
        self.lead_organization_id = lead_organization_id
        self.district_id = district_id
        self.lat = lat
        self.lon = lon
        self.location_name = location_name
        self.status = status  # "PLANNING" | "ACTIVE" | "PAUSED" | "COMPLETED" | "CANCELLED"
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "operation_type": self.operation_type,
            "description": self.description,
            "need_id": self.need_id,
            "lead_organization_id": self.lead_organization_id,
            "district_id": self.district_id,
            "lat": self.lat,
            "lon": self.lon,
            "location_name": self.location_name,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


class ActivityEvent:
    """An append-oriented activity history event."""
    def __init__(
        self,
        id: str,
        entity_type: str,
        entity_id: str,
        event_type: str,
        actor: str = "",
        detail: str = "",
        created_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ):
        self.id = id
        self.entity_type = entity_type  # "need" | "resource_offer" | "operation" | "organization" | "field_report"
        self.entity_id = entity_id
        self.event_type = event_type  # "need_created" | "organization_joined" | "resource_offered" | "operation_created" | "status_changed" | "field_update" | "need_resolved"
        self.actor = actor
        self.detail = detail
        self.created_at = created_at or datetime.now(timezone.utc)
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "detail": self.detail,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


class Notification:
    """A persisted notification for a user."""
    def __init__(
        self,
        id: str,
        recipient_id: str,
        notification_type: str,
        title: str,
        message: str = "",
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        read: bool = False,
        created_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ):
        self.id = id
        self.recipient_id = recipient_id
        self.notification_type = notification_type  # "urgent_need" | "need_update" | "resource_offer" | "operation_update" | "route_change" | "field_report" | "ai_recommendation" | "coordination_gap"
        self.title = title
        self.message = message
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.read = read
        self.created_at = created_at or datetime.now(timezone.utc)
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "recipient_id": self.recipient_id,
            "notification_type": self.notification_type,
            "title": self.title,
            "message": self.message,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "read": self.read,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def make_flood_snapshot_id(district_id: str, observed_at: datetime) -> str:
    """Generate a deterministic ID for a flood snapshot."""
    date_str = observed_at.strftime("%Y%m%d")
    return f"flood_{district_id}_{date_str}"


def make_settlement_id(district_id: str, name: str) -> str:
    """Generate a deterministic ID for a settlement."""
    slug = name.lower().replace(" ", "_").replace("-", "_")
    return f"{district_id}_{slug}"
