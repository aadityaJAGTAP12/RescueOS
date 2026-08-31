"""
Phase 3: Data Repository Interface + In-Memory Implementation

Provides an abstract repository interface that can be backed by:
- InMemoryRepository (for tests, backward compatibility, no external deps)
- PostgresRepository (for production, requires PostgreSQL + PostGIS)

The in-memory implementation stores everything in Python dicts/lists.
This allows all existing tests to keep working without any database.

Key principle: Tools never touch storage directly. They go through
the repository interface, which makes the data source swappable.
"""

from __future__ import annotations

import math
from typing import Optional

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


# ---------------------------------------------------------------------------
# Abstract Repository Interface
# ---------------------------------------------------------------------------

class DataRepository:
    """
    Abstract data access layer. All data operations go through here.

    Implementations:
    - InMemoryRepository: dict-backed, for tests (no external deps)
    - PostgresRepository: PostgreSQL + PostGIS (for production)
    """

    # --- Districts ---

    def get_district(self, district_id: str) -> Optional[District]:
        raise NotImplementedError

    def list_districts(self) -> list[District]:
        raise NotImplementedError

    def upsert_district(self, district: District) -> None:
        raise NotImplementedError

    # --- Settlements / Locations ---

    def get_settlement(self, settlement_id: str) -> Optional[Settlement]:
        raise NotImplementedError

    def list_settlements(self, district_id: Optional[str] = None) -> list[Settlement]:
        raise NotImplementedError

    def upsert_settlement(self, settlement: Settlement) -> None:
        raise NotImplementedError

    def resolve_location(self, name: str = None, lat: float = None, lon: float = None, district_id: str = None) -> Optional[Settlement]:
        """
        Generalized location resolution.

        Resolves a location from:
        - Exact settlement ID or name
        - Alias matching
        - Coordinate proximity (nearest settlement within threshold)
        - Direct lat/lon (returns a synthetic Settlement if needed)

        Returns None only if truly unresolvable.
        """
        raise NotImplementedError

    # --- Flood Snapshots ---

    def get_flood_snapshot(self, snapshot_id: str) -> Optional[FloodSnapshot]:
        raise NotImplementedError

    def list_flood_snapshots(self, district_id: str = None, observed_after: str = None) -> list[FloodSnapshot]:
        raise NotImplementedError

    def upsert_flood_snapshot(self, snapshot: FloodSnapshot) -> None:
        raise NotImplementedError

    def get_latest_flood_snapshot(self, district_id: str, observed_at: str = None) -> Optional[FloodSnapshot]:
        """Get the most recent flood snapshot for a district, optionally filtered by date."""
        raise NotImplementedError

    # --- Field Reports ---

    def get_field_report(self, report_id: str) -> Optional[FieldReport]:
        raise NotImplementedError

    def list_field_reports(self, district_id: str = None, lat: float = None, lon: float = None, radius_km: float = 5.0) -> list[FieldReport]:
        raise NotImplementedError

    def upsert_field_report(self, report: FieldReport) -> None:
        raise NotImplementedError

    # --- Overrides ---

    def get_active_override(self, target_type: str, target_id: str) -> Optional[Override]:
        raise NotImplementedError

    def list_overrides(self, district_id: str = None) -> list[Override]:
        raise NotImplementedError

    def upsert_override(self, override: Override) -> None:
        raise NotImplementedError

    # --- Infrastructure (generic geographic queries) ---

    def get_buildings(self, district_id: str, lat: float = None, lon: float = None, radius_km: float = 1.5) -> list[Building]:
        raise NotImplementedError

    def get_medical_facilities(self, district_id: str, lat: float = None, lon: float = None, radius_km: float = 20.0) -> list[MedicalFacility]:
        raise NotImplementedError

    def get_roads(self, district_id: str, lat: float = None, lon: float = None, radius_km: float = 2.0) -> list[Road]:
        raise NotImplementedError

    def upsert_buildings(self, buildings: list[Building]) -> None:
        raise NotImplementedError

    def upsert_medical_facilities(self, facilities: list[MedicalFacility]) -> None:
        raise NotImplementedError

    def upsert_roads(self, roads: list[Road]) -> None:
        raise NotImplementedError

    # --- Provenance ---

    def get_provenance_summary(self, district_id: str = None) -> dict:
        """Return counts by provenance type for auditing."""
        raise NotImplementedError

    # --- Bulk / migration ---

    def import_flood_geojson(self, geojson: dict, district_id: str, source: str = "import", observed_at: str = None) -> FloodSnapshot:
        """
        Import a GeoJSON file as a flood snapshot.

        This is the migration path for data/sivasagar_flood.geojson.
        """
        raise NotImplementedError

    # --- Organizations (Phase 7B) ---

    def create_organization(self, org: Organization) -> Organization:
        raise NotImplementedError

    def get_organization(self, org_id: str) -> Optional[Organization]:
        raise NotImplementedError

    def list_organizations(self, active_only: bool = True) -> list[Organization]:
        raise NotImplementedError

    def update_organization(self, org: Organization) -> None:
        raise NotImplementedError

    # --- Needs (Phase 7B) ---

    def create_need(self, need: Need) -> Need:
        raise NotImplementedError

    def get_need(self, need_id: str) -> Optional[Need]:
        raise NotImplementedError

    def list_needs(self, district_id: str = None, status: str = None, urgency: str = None) -> list[Need]:
        raise NotImplementedError

    def update_need(self, need: Need) -> None:
        raise NotImplementedError

    def update_need_status(self, need_id: str, status: str) -> Optional[Need]:
        raise NotImplementedError

    # --- Resource Offers (Phase 7B) ---

    def create_resource_offer(self, offer: ResourceOffer) -> ResourceOffer:
        raise NotImplementedError

    def get_resource_offer(self, offer_id: str) -> Optional[ResourceOffer]:
        raise NotImplementedError

    def list_resource_offers(self, organization_id: str = None, district_id: str = None, status: str = None, resource_type: str = None) -> list[ResourceOffer]:
        raise NotImplementedError

    def update_resource_offer(self, offer: ResourceOffer) -> None:
        raise NotImplementedError

    # --- Operations (Phase 7B) ---

    def create_operation(self, operation: Operation) -> Operation:
        raise NotImplementedError

    def get_operation(self, operation_id: str) -> Optional[Operation]:
        raise NotImplementedError

    def list_operations(self, district_id: str = None, status: str = None, lead_organization_id: str = None) -> list[Operation]:
        raise NotImplementedError

    def update_operation(self, operation: Operation) -> None:
        raise NotImplementedError

    def add_operation_participant(self, operation_id: str, organization_id: str, role: str = "support") -> None:
        raise NotImplementedError

    def list_operation_participants(self, operation_id: str) -> list[dict]:
        raise NotImplementedError

    # --- Activity Events (Phase 7B) ---

    def append_activity_event(self, event: ActivityEvent) -> None:
        raise NotImplementedError

    def list_activity_events(self, entity_type: str = None, entity_id: str = None, limit: int = 50) -> list[ActivityEvent]:
        raise NotImplementedError

    # --- Notifications (Phase 7B) ---

    def create_notification(self, notification: Notification) -> Notification:
        raise NotImplementedError

    def list_notifications(self, recipient_id: str, unread_only: bool = False, limit: int = 50) -> list[Notification]:
        raise NotImplementedError

    def mark_notification_read(self, notification_id: str) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# In-Memory Implementation
# ---------------------------------------------------------------------------

class InMemoryRepository(DataRepository):
    """
    Dict-backed repository for tests and backward compatibility.

    All data lives in Python dicts keyed by ID. No external dependencies.
    Thread-unsafe (fine for single-threaded tests and dev server).
    """

    def __init__(self):
        self._districts: dict[str, District] = {}
        self._settlements: dict[str, Settlement] = {}
        self._flood_snapshots: dict[str, FloodSnapshot] = {}
        self._field_reports: dict[str, FieldReport] = {}
        self._overrides: dict[str, Override] = {}
        self._buildings: dict[str, Building] = {}
        self._medical_facilities: dict[str, MedicalFacility] = {}
        self._roads: dict[str, Road] = {}
        # Phase 7B: Shared operational objects
        self._organizations: dict[str, Organization] = {}
        self._needs: dict[str, Need] = {}
        self._resource_offers: dict[str, ResourceOffer] = {}
        self._operations: dict[str, Operation] = {}
        self._operation_participants: dict[str, list[dict]] = {}  # operation_id -> [{org_id, role, joined_at}]
        self._activity_events: list[ActivityEvent] = []
        self._notifications: dict[str, Notification] = {}

    def clear(self):
        """Reset all data (for testing)."""
        self._districts.clear()
        self._settlements.clear()
        self._flood_snapshots.clear()
        self._field_reports.clear()
        self._overrides.clear()
        self._buildings.clear()
        self._medical_facilities.clear()
        self._roads.clear()
        self._organizations.clear()
        self._needs.clear()
        self._resource_offers.clear()
        self._operations.clear()
        self._operation_participants.clear()
        self._activity_events.clear()
        self._notifications.clear()

    # --- Districts ---

    def get_district(self, district_id: str) -> Optional[District]:
        return self._districts.get(district_id)

    def list_districts(self) -> list[District]:
        return list(self._districts.values())

    def upsert_district(self, district: District) -> None:
        self._districts[district.id] = district

    # --- Settlements ---

    def get_settlement(self, settlement_id: str) -> Optional[Settlement]:
        return self._settlements.get(settlement_id)

    def list_settlements(self, district_id: Optional[str] = None) -> list[Settlement]:
        if district_id:
            return [s for s in self._settlements.values() if s.district_id == district_id]
        return list(self._settlements.values())

    def upsert_settlement(self, settlement: Settlement) -> None:
        self._settlements[settlement.id] = settlement

    def resolve_location(self, name: str = None, lat: float = None, lon: float = None, district_id: str = None) -> Optional[Settlement]:
        """
        Generalized location resolution — no hardcoded place names.

        Resolution order:
        1. Direct lat/lon → nearest settlement within 5km
        2. Name → exact match, then case-insensitive, then alias
        3. Name + district → scoped search
        """
        settlements = self.list_settlements(district_id=district_id)

        # 1. Coordinate-based resolution
        if lat is not None and lon is not None:
            best = None
            best_dist = float("inf")
            for s in settlements:
                d = _haversine_km(lon, lat, s.lon, s.lat)
                if d < best_dist:
                    best_dist = d
                    best = s
            if best and best_dist <= 5.0:
                return best
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
        name_with_underscores = name_lower.replace(" ", "_").replace("-", "_")

        # Exact match
        for s in settlements:
            if s.id.lower() == name_lower or s.id.lower() == name_with_underscores:
                return s
            if s.name.lower() == name_lower:
                return s

        # Case-insensitive partial match
        for s in settlements:
            if name_lower in s.name.lower() or s.name.lower() in name_lower:
                return s
            for alias in s.aliases:
                if name_lower == alias.lower():
                    return s

        # Name with underscores match (backward compatibility)
        for s in settlements:
            if s.id.lower() == name_with_underscores:
                return s

        return None

    # --- Flood Snapshots ---

    def get_flood_snapshot(self, snapshot_id: str) -> Optional[FloodSnapshot]:
        return self._flood_snapshots.get(snapshot_id)

    def list_flood_snapshots(self, district_id: str = None, observed_after: str = None) -> list[FloodSnapshot]:
        results = list(self._flood_snapshots.values())
        if district_id:
            results = [s for s in results if s.district_id == district_id]
        if observed_after:
            from datetime import datetime as dt
            cutoff = dt.fromisoformat(observed_after)
            results = [s for s in results if s.observed_at >= cutoff]
        return results

    def upsert_flood_snapshot(self, snapshot: FloodSnapshot) -> None:
        self._flood_snapshots[snapshot.id] = snapshot

    def get_latest_flood_snapshot(self, district_id: str, observed_at: str = None) -> Optional[FloodSnapshot]:
        snapshots = self.list_flood_snapshots(district_id=district_id)
        if not snapshots:
            return None
        # Sort by observed_at descending
        snapshots.sort(key=lambda s: s.observed_at, reverse=True)
        if observed_at:
            from datetime import datetime as dt
            cutoff = dt.fromisoformat(observed_at)
            snapshots = [s for s in snapshots if s.observed_at <= cutoff]
        return snapshots[0] if snapshots else None

    # --- Field Reports ---

    def get_field_report(self, report_id: str) -> Optional[FieldReport]:
        return self._field_reports.get(report_id)

    def list_field_reports(self, district_id: str = None, lat: float = None, lon: float = None, radius_km: float = 5.0) -> list[FieldReport]:
        results = list(self._field_reports.values())
        if district_id:
            results = [r for r in results if r.district_id == district_id]
        if lat is not None and lon is not None:
            nearby = []
            for r in results:
                if r.lat is None or r.lon is None:
                    continue
                dist = _haversine_km(lon, lat, r.lon, r.lat)
                if dist <= radius_km:
                    nearby.append(r)
            results = nearby
        return results

    def upsert_field_report(self, report: FieldReport) -> None:
        self._field_reports[report.id] = report

    # --- Overrides ---

    def get_active_override(self, target_type: str, target_id: str) -> Optional[Override]:
        matching = [
            o for o in self._overrides.values()
            if o.target_type == target_type
            and o.active
            and _names_match(o.target_id, target_id)
        ]
        if not matching:
            return None
        matching.sort(key=lambda o: o.created_at, reverse=True)
        return matching[0]

    def list_overrides(self, district_id: str = None) -> list[Override]:
        return list(self._overrides.values())

    def upsert_override(self, override: Override) -> None:
        self._overrides[override.id] = override

    # --- Infrastructure ---

    def get_buildings(self, district_id: str, lat: float = None, lon: float = None, radius_km: float = 1.5) -> list[Building]:
        results = [b for b in self._buildings.values() if b.district_id == district_id]
        if lat is not None and lon is not None:
            nearby = []
            for b in results:
                dist = _haversine_km(lon, lat, b.lon, b.lat)
                if dist <= radius_km:
                    nearby.append(b)
            results = nearby
        return results

    def get_medical_facilities(self, district_id: str, lat: float = None, lon: float = None, radius_km: float = 20.0) -> list[MedicalFacility]:
        results = [f for f in self._medical_facilities.values() if f.district_id == district_id]
        if lat is not None and lon is not None:
            nearby = []
            for f in results:
                dist = _haversine_km(lon, lat, f.lon, f.lat)
                if dist <= radius_km:
                    nearby.append(f)
            results = nearby
        return results

    def get_roads(self, district_id: str, lat: float = None, lon: float = None, radius_km: float = 2.0) -> list[Road]:
        results = [r for r in self._roads.values() if r.district_id == district_id]
        # Road radius filtering would require road geometry — skip for now
        return results

    def upsert_buildings(self, buildings: list[Building]) -> None:
        for b in buildings:
            self._buildings[b.id] = b

    def upsert_medical_facilities(self, facilities: list[MedicalFacility]) -> None:
        for f in facilities:
            self._medical_facilities[f.id] = f

    def upsert_roads(self, roads: list[Road]) -> None:
        for r in roads:
            self._roads[r.id] = r

    # --- Provenance ---

    def get_provenance_summary(self, district_id: str = None) -> dict:
        summary = {}
        for snap in self._flood_snapshots.values():
            if district_id and snap.district_id != district_id:
                continue
            key = snap.provenance.value
            summary[key] = summary.get(key, 0) + 1
        for report in self._field_reports.values():
            if district_id and report.district_id != district_id:
                continue
            key = report.provenance.value
            summary[key] = summary.get(key, 0) + 1
        for override in self._overrides.values():
            key = "MANUAL_OVERRIDE"
            summary[key] = summary.get(key, 0) + 1
        return summary

    # --- Bulk / migration ---

    def import_flood_geojson(self, geojson: dict, district_id: str, source: str = "import", observed_at: str = None) -> FloodSnapshot:
        """
        Import a GeoJSON FeatureCollection as a flood snapshot.

        Preserves the full GeoJSON for backward compatibility.
        """
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

    # --- Organizations (Phase 7B) ---

    def create_organization(self, org: Organization) -> Organization:
        self._organizations[org.id] = org
        return org

    def get_organization(self, org_id: str) -> Optional[Organization]:
        return self._organizations.get(org_id)

    def list_organizations(self, active_only: bool = True) -> list[Organization]:
        results = list(self._organizations.values())
        if active_only:
            results = [o for o in results if o.active]
        return results

    def update_organization(self, org: Organization) -> None:
        self._organizations[org.id] = org

    # --- Needs (Phase 7B) ---

    def create_need(self, need: Need) -> Need:
        self._needs[need.id] = need
        return need

    def get_need(self, need_id: str) -> Optional[Need]:
        return self._needs.get(need_id)

    def list_needs(self, district_id: str = None, status: str = None, urgency: str = None) -> list[Need]:
        results = list(self._needs.values())
        if district_id:
            results = [n for n in results if n.district_id == district_id]
        if status:
            results = [n for n in results if n.status == status]
        if urgency:
            results = [n for n in results if n.urgency == urgency]
        return results

    def update_need(self, need: Need) -> None:
        self._needs[need.id] = need

    def update_need_status(self, need_id: str, status: str) -> Optional[Need]:
        need = self._needs.get(need_id)
        if need is None:
            return None
        need.status = status
        from datetime import datetime as dt, timezone
        need.updated_at = dt.now(timezone.utc)
        return need

    # --- Resource Offers (Phase 7B) ---

    def create_resource_offer(self, offer: ResourceOffer) -> ResourceOffer:
        self._resource_offers[offer.id] = offer
        return offer

    def get_resource_offer(self, offer_id: str) -> Optional[ResourceOffer]:
        return self._resource_offers.get(offer_id)

    def list_resource_offers(self, organization_id: str = None, district_id: str = None, status: str = None, resource_type: str = None) -> list[ResourceOffer]:
        results = list(self._resource_offers.values())
        if organization_id:
            results = [o for o in results if o.organization_id == organization_id]
        if district_id:
            results = [o for o in results if o.district_id == district_id]
        if status:
            results = [o for o in results if o.status == status]
        if resource_type:
            results = [o for o in results if o.resource_type == resource_type]
        return results

    def update_resource_offer(self, offer: ResourceOffer) -> None:
        self._resource_offers[offer.id] = offer

    # --- Operations (Phase 7B) ---

    def create_operation(self, operation: Operation) -> Operation:
        self._operations[operation.id] = operation
        return operation

    def get_operation(self, operation_id: str) -> Optional[Operation]:
        return self._operations.get(operation_id)

    def list_operations(self, district_id: str = None, status: str = None, lead_organization_id: str = None) -> list[Operation]:
        results = list(self._operations.values())
        if district_id:
            results = [o for o in results if o.district_id == district_id]
        if status:
            results = [o for o in results if o.status == status]
        if lead_organization_id:
            results = [o for o in results if o.lead_organization_id == lead_organization_id]
        return results

    def update_operation(self, operation: Operation) -> None:
        self._operations[operation.id] = operation

    def add_operation_participant(self, operation_id: str, organization_id: str, role: str = "support") -> None:
        if operation_id not in self._operation_participants:
            self._operation_participants[operation_id] = []
        from datetime import datetime as dt, timezone
        self._operation_participants[operation_id].append({
            "operation_id": operation_id,
            "organization_id": organization_id,
            "role": role,
            "joined_at": dt.now(timezone.utc),
        })

    def list_operation_participants(self, operation_id: str) -> list[dict]:
        return self._operation_participants.get(operation_id, [])

    # --- Activity Events (Phase 7B) ---

    def append_activity_event(self, event: ActivityEvent) -> None:
        self._activity_events.append(event)

    def list_activity_events(self, entity_type: str = None, entity_id: str = None, limit: int = 50) -> list[ActivityEvent]:
        results = self._activity_events
        if entity_type:
            results = [e for e in results if e.entity_type == entity_type]
        if entity_id:
            results = [e for e in results if e.entity_id == entity_id]
        # Sort by created_at descending (most recent first)
        results.sort(key=lambda e: e.created_at, reverse=True)
        return results[:limit]

    # --- Notifications (Phase 7B) ---

    def create_notification(self, notification: Notification) -> Notification:
        self._notifications[notification.id] = notification
        return notification

    def list_notifications(self, recipient_id: str, unread_only: bool = False, limit: int = 50) -> list[Notification]:
        results = [n for n in self._notifications.values() if n.recipient_id == recipient_id]
        if unread_only:
            results = [n for n in results if not n.read]
        results.sort(key=lambda n: n.created_at, reverse=True)
        return results[:limit]

    def mark_notification_read(self, notification_id: str) -> None:
        notif = self._notifications.get(notification_id)
        if notif:
            notif.read = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Straight-line distance in km between two lon/lat points."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _names_match(a: str, b: str) -> bool:
    """Case-insensitive substring matching (same as overrides.py)."""
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


# ---------------------------------------------------------------------------
# Repository factory — selects backend based on environment
# ---------------------------------------------------------------------------

import os

_default_repository: Optional[DataRepository] = None
_repository_explicitly_set: bool = False


def get_repository() -> DataRepository:
    """
    Get the active data repository.

    Selection logic:
    1. If set_repository() was called explicitly → use that
    2. If DATABASE_URL env var is set and not empty → PostgresRepository
    3. If RELIEFOS_MEMORY=1 or TEST mode → InMemoryRepository
    4. Default → InMemoryRepository (safe fallback for dev/tests)

    Production config:
        export DATABASE_URL=postgresql://user:pass@localhost:5432/reliefos
        python agent/main.py

    Test config:
        export RELIEFOS_MEMORY=1
        python -m pytest tests/
    """
    global _default_repository, _repository_explicitly_set

    # If explicitly set via set_repository(), use that
    if _repository_explicitly_set and _default_repository is not None:
        return _default_repository

    # Check if DATABASE_URL is configured
    db_url = os.environ.get("DATABASE_URL", "").strip()
    memory_mode = os.environ.get("RELIEFOS_MEMORY", "").strip()

    if _default_repository is not None:
        return _default_repository

    # If explicitly memory mode, use InMemoryRepository
    if memory_mode in ("1", "true", "yes"):
        _default_repository = InMemoryRepository()
        return _default_repository

    # If DATABASE_URL is set, try PostgresRepository
    if db_url:
        try:
            from agent.data.postgres_repository import PostgresRepository
            repo = PostgresRepository(database_url=db_url)
            _default_repository = repo
            print(f"  [REPOSITORY] Using PostgreSQL backend")
            return _default_repository
        except Exception as e:
            print(f"  [REPOSITORY WARNING] Failed to connect to PostgreSQL: {e}")
            print(f"  [REPOSITORY WARNING] Falling back to InMemoryRepository")
            print(f"  [REPOSITORY WARNING] Set RELIEFOS_MEMORY=1 to suppress this warning")
            _default_repository = InMemoryRepository()
            return _default_repository

    # Default: InMemoryRepository (safe for tests and development)
    _default_repository = InMemoryRepository()
    return _default_repository


def set_repository(repo: DataRepository) -> None:
    """Replace the default repository (for testing or production wiring)."""
    global _default_repository, _repository_explicitly_set
    _default_repository = repo
    _repository_explicitly_set = True


def reset_repository() -> None:
    """Reset to a fresh InMemoryRepository (for testing)."""
    global _default_repository, _repository_explicitly_set
    _default_repository = InMemoryRepository()
    _repository_explicitly_set = False
