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

import os
import math
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv

# Automatically load environment variables from .env file at repo root
load_dotenv()

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
    AgentEvent,
    AgentEventType,
    EventStatus,
    ProactiveScan,
    ProactiveFinding,
    User,
    OrganizationMembership,
    AuditLog,
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

    def get_notification(self, notification_id: str) -> Optional[Notification]:
        """Fetch a single notification by id, or None."""
        raise NotImplementedError

    def list_notifications(self, recipient_id: str, unread_only: bool = False, limit: int = 50) -> list[Notification]:
        raise NotImplementedError

    def mark_notification_read(self, notification_id: str) -> None:
        raise NotImplementedError

    # --- Coordination Proposals (Item #5 Step 2 — PostgreSQL authoritative) ---

    def create_proposal(self, proposal: dict) -> dict:
        """Store a new coordination proposal (plain dict, Phase 7H schema)."""
        raise NotImplementedError

    def get_proposal(self, proposal_id: str) -> Optional[dict]:
        """Fetch one coordination proposal by id, or None."""
        raise NotImplementedError

    def list_proposals(self, need_id: str = None, organization_id: str = None,
                       status: str = None) -> list[dict]:
        """List coordination proposals with optional filters."""
        raise NotImplementedError

    def update_proposal(self, proposal_id: str, updates: dict,
                        expected_statuses: list = None) -> Optional[dict]:
        """Apply a partial update; if expected_statuses is given, only update
        when the current status matches (atomic single-row guard). Returns the
        updated proposal or None when not found / guard not met."""
        raise NotImplementedError

    # --- Agent Events / Outbox (Phase 2A) ---

    def append_agent_event(self, event: AgentEvent) -> AgentEvent:
        """Persist a machine-facing agent event to the outbox."""
        raise NotImplementedError

    def get_agent_event(self, event_id: str) -> Optional[AgentEvent]:
        """Retrieve an agent event by ID."""
        raise NotImplementedError

    def list_agent_events(
        self,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[AgentEvent]:
        """List agent events with optional filtering."""
        raise NotImplementedError

    def update_agent_event_status(
        self,
        event_id: str,
        status: str,
        processed_at: Optional[datetime] = None,
        error_detail: Optional[str] = None,
        execution_result: Optional[dict] = None,
    ) -> Optional[AgentEvent]:
        """Update an agent event's processing status and execution results."""
        raise NotImplementedError

    def claim_pending_agent_events(self, limit: int = 10) -> list[AgentEvent]:
        """Atomically claim pending agent events for dispatch."""
        raise NotImplementedError

    # --- Proactive Scans & Findings (Phase 2B) ---

    def create_proactive_scan(self, scan: ProactiveScan) -> ProactiveScan:
        """Create a new proactive scan record."""
        raise NotImplementedError

    def get_proactive_scan(self, scan_id: str) -> Optional[ProactiveScan]:
        """Retrieve a proactive scan by ID."""
        raise NotImplementedError

    def list_proactive_scans(
        self,
        status: Optional[str] = None,
        trigger: Optional[str] = None,
        limit: int = 50,
    ) -> list[ProactiveScan]:
        """List proactive scans with optional filtering."""
        raise NotImplementedError

    def update_proactive_scan(
        self,
        scan_id: str,
        status: Optional[str] = None,
        completed_at: Optional[datetime] = None,
        findings_count: Optional[int] = None,
        summary: Optional[str] = None,
        metrics: Optional[dict] = None,
        failures: Optional[list] = None,
        detectors_run: Optional[list] = None,
        specialists_invoked: Optional[list] = None,
    ) -> Optional[ProactiveScan]:
        """Update a proactive scan's status and results."""
        raise NotImplementedError

    def upsert_proactive_finding(self, finding: ProactiveFinding) -> ProactiveFinding:
        """Upsert a proactive finding by fingerprint or ID."""
        raise NotImplementedError

    def get_proactive_finding(self, finding_id: str) -> Optional[ProactiveFinding]:
        """Retrieve a proactive finding by ID."""
        raise NotImplementedError

    def get_proactive_finding_by_fingerprint(self, fingerprint: str) -> Optional[ProactiveFinding]:
        """Retrieve the most recent proactive finding with given fingerprint."""
        raise NotImplementedError

    def list_proactive_findings(
        self,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        severity: Optional[str] = None,
        scan_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[ProactiveFinding]:
        """List proactive findings with optional filtering."""
        raise NotImplementedError

    def recover_stale_agent_events(self, stale_threshold_seconds: int = 300) -> list[AgentEvent]:
        """Recover events stuck in CLAIMED/PROCESSING beyond timeout threshold."""
        raise NotImplementedError

    # --- Authentication & Authorization (Production Hardening) ---

    def create_user(self, user: User) -> User:
        """Create a new user record."""
        raise NotImplementedError

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Retrieve a user by ID."""
        raise NotImplementedError

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Retrieve a user by username."""
        raise NotImplementedError

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Retrieve a user by email."""
        raise NotImplementedError

    def update_user(self, user: User) -> Optional[User]:
        """Update an existing user."""
        raise NotImplementedError

    def list_users(self, limit: int = 100) -> list[User]:
        """List users."""
        raise NotImplementedError

    def create_membership(self, membership: OrganizationMembership) -> OrganizationMembership:
        """Create or update an organization membership."""
        raise NotImplementedError

    def get_membership(self, user_id: str, organization_id: str) -> Optional[OrganizationMembership]:
        """Get membership for a specific user and organization."""
        raise NotImplementedError

    def list_memberships_for_user(self, user_id: str) -> list[OrganizationMembership]:
        """List all organization memberships for a user."""
        raise NotImplementedError

    def list_memberships_for_org(self, organization_id: str) -> list[OrganizationMembership]:
        """List all memberships for an organization."""
        raise NotImplementedError

    def delete_membership(self, user_id: str, organization_id: str) -> bool:
        """Delete an organization membership."""
        raise NotImplementedError

    # --- Consequential Action Audit Logs (Production Hardening) ---

    def create_audit_log(self, log: AuditLog) -> AuditLog:
        """Record an immutable audit log entry."""
        raise NotImplementedError

    def list_audit_logs(
        self,
        actor_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """List audit logs with optional filters."""
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
        # Item #5 Step 2: coordination proposals (plain dicts, Phase 7H schema)
        self._proposals: dict[str, dict] = {}
        # Phase 2A: Agent events outbox
        self._agent_events: dict[str, AgentEvent] = {}
        # Phase 2B: Proactive scans & findings
        self._proactive_scans: dict[str, ProactiveScan] = {}
        self._proactive_findings: dict[str, ProactiveFinding] = {}
        # Production Hardening: Auth & Audit
        self._users: dict[str, User] = {}
        self._memberships: dict[str, OrganizationMembership] = {}
        self._audit_logs: list[AuditLog] = []

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
        self._proposals.clear()
        self._agent_events.clear()
        self._proactive_scans.clear()
        self._proactive_findings.clear()
        self._users.clear()
        self._memberships.clear()
        self._audit_logs.clear()


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
        try:
            from agent.agents.events import make_flood_snapshot_event
            self.append_agent_event(make_flood_snapshot_event(
                snapshot_id=snapshot.id,
                district=district_id,
                priority="urgent",
                metadata={"polygon_count": len(features), "source": source},
            ))
        except Exception:
            pass
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
            results = [n for n in results if n.district_id and n.district_id.lower() == district_id.lower()]
        if status:
            results = [n for n in results if n.status and n.status.lower() == status.lower()]
        if urgency:
            results = [n for n in results if n.urgency and n.urgency.lower() == urgency.lower()]
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
            results = [o for o in results if o.district_id and o.district_id.lower() == district_id.lower()]
        if status:
            results = [o for o in results if o.status and o.status.lower() == status.lower()]
        if resource_type:
            results = [o for o in results if o.resource_type and o.resource_type.lower() == resource_type.lower()]
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
            results = [o for o in results if o.district_id and o.district_id.lower() == district_id.lower()]
        if status:
            results = [o for o in results if o.status and o.status.lower() == status.lower()]
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

    def get_notification(self, notification_id: str) -> Optional[Notification]:
        return self._notifications.get(notification_id)

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

    # --- Coordination Proposals (Item #5 Step 2) ---

    def create_proposal(self, proposal: dict) -> dict:
        stored = dict(proposal)
        # Match the PostgreSQL contract: created_at/updated_at are NOT NULL
        # with a now() server default — never missing or NULL (Item 5B Bug 1).
        now_iso = datetime.now(timezone.utc).isoformat()
        if not stored.get("created_at"):
            stored["created_at"] = now_iso
        if not stored.get("updated_at"):
            stored["updated_at"] = now_iso
        self._proposals[stored["id"]] = stored
        return stored

    def get_proposal(self, proposal_id: str) -> Optional[dict]:
        proposal = self._proposals.get(proposal_id)
        return dict(proposal) if proposal else None

    def list_proposals(self, need_id: str = None, organization_id: str = None,
                       status: str = None) -> list[dict]:
        results = list(self._proposals.values())
        if need_id:
            results = [p for p in results if p.get("need_id") == need_id]
        if organization_id:
            results = [p for p in results if p.get("organization_id") == organization_id]
        if status:
            results = [p for p in results if p.get("status") == status]
        results.sort(key=lambda p: p.get("created_at", ""), reverse=True)
        return [dict(p) for p in results]

    def update_proposal(self, proposal_id: str, updates: dict,
                        expected_statuses: list = None) -> Optional[dict]:
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return None
        if expected_statuses is not None and proposal.get("status") not in expected_statuses:
            return None
        updated = dict(proposal)
        updated.update(updates)
        updated["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._proposals[proposal_id] = updated
        return updated

    # --- Agent Events / Outbox (Phase 2A) ---

    def append_agent_event(self, event: AgentEvent) -> AgentEvent:
        """Persist a machine-facing agent event."""
        if not event.event_id:
            import uuid
            event.event_id = f"evt_{str(uuid.uuid4())[:12]}"
        if not event.created_at:
            event.created_at = datetime.now(timezone.utc).isoformat()
        self._agent_events[event.event_id] = event
        return event

    def get_agent_event(self, event_id: str) -> Optional[AgentEvent]:
        """Retrieve an agent event by ID."""
        return self._agent_events.get(event_id)

    def list_agent_events(
        self,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[AgentEvent]:
        """List agent events with optional filtering."""
        results = list(self._agent_events.values())
        if status:
            results = [e for e in results if (e.status == status or (hasattr(e.status, "value") and e.status.value == status))]
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if entity_type:
            results = [e for e in results if e.entity_type == entity_type]
        results.sort(key=lambda e: e.created_at or "", reverse=True)
        return results[:limit]

    def update_agent_event_status(
        self,
        event_id: str,
        status: str,
        processed_at: Optional[datetime] = None,
        error_detail: Optional[str] = None,
        execution_result: Optional[dict] = None,
    ) -> Optional[AgentEvent]:
        """Update status and outcome of an agent event."""
        evt = self._agent_events.get(event_id)
        if not evt:
            return None
        evt.status = status
        if processed_at:
            evt.processed_at = processed_at.isoformat() if hasattr(processed_at, "isoformat") else str(processed_at)
        elif status in (EventStatus.PROCESSED.value, EventStatus.FAILED.value, EventStatus.SKIPPED_DUPLICATE.value):
            evt.processed_at = datetime.now(timezone.utc).isoformat()
        if error_detail is not None:
            evt.error_detail = error_detail
        if execution_result is not None:
            evt.execution_result = execution_result
        return evt

    def claim_pending_agent_events(self, limit: int = 10) -> list[AgentEvent]:
        """Atomically claim pending agent events for dispatch."""
        pending = [
            e for e in self._agent_events.values()
            if e.status in (EventStatus.PENDING.value, "PENDING")
        ]
        # Sort oldest first for FIFO processing
        pending.sort(key=lambda e: e.created_at or "")
        claimed = pending[:limit]
        for e in claimed:
            e.status = EventStatus.CLAIMED.value
            e.claimed_at = datetime.now(timezone.utc).isoformat()
        return claimed

    # --- Proactive Scans & Findings (Phase 2B) ---

    def create_proactive_scan(self, scan: ProactiveScan) -> ProactiveScan:
        self._proactive_scans[scan.id] = scan
        return scan

    def get_proactive_scan(self, scan_id: str) -> Optional[ProactiveScan]:
        return self._proactive_scans.get(scan_id)

    def list_proactive_scans(
        self,
        status: Optional[str] = None,
        trigger: Optional[str] = None,
        limit: int = 50,
    ) -> list[ProactiveScan]:
        scans = list(self._proactive_scans.values())
        if status:
            scans = [s for s in scans if (s.status if isinstance(s.status, str) else s.status.value) == status]
        if trigger:
            scans = [s for s in scans if s.trigger == trigger]
        scans.sort(key=lambda s: s.started_at or datetime.min, reverse=True)
        return scans[:limit]

    def update_proactive_scan(
        self,
        scan_id: str,
        status: Optional[str] = None,
        completed_at: Optional[datetime] = None,
        findings_count: Optional[int] = None,
        summary: Optional[str] = None,
        metrics: Optional[dict] = None,
        failures: Optional[list] = None,
        detectors_run: Optional[list] = None,
        specialists_invoked: Optional[list] = None,
    ) -> Optional[ProactiveScan]:
        scan = self._proactive_scans.get(scan_id)
        if not scan:
            return None
        if status is not None:
            scan.status = status
        if completed_at is not None:
            scan.completed_at = completed_at
        if findings_count is not None:
            scan.findings_count = findings_count
        if summary is not None:
            scan.summary = summary
        if metrics is not None:
            scan.metrics = metrics
        if failures is not None:
            scan.failures = failures
        if detectors_run is not None:
            scan.detectors_run = detectors_run
        if specialists_invoked is not None:
            scan.specialists_invoked = specialists_invoked
        return scan

    def upsert_proactive_finding(self, finding: ProactiveFinding) -> ProactiveFinding:
        # Check if finding with same fingerprint exists
        existing = self.get_proactive_finding_by_fingerprint(finding.fingerprint)
        if existing:
            # Update mutable fields
            existing.scan_id = finding.scan_id
            existing.status = finding.status
            existing.severity = finding.severity
            existing.title = finding.title
            existing.summary = finding.summary
            existing.evidence = finding.evidence
            existing.provenance = finding.provenance
            existing.uncertainty = finding.uncertainty
            existing.data_gaps = finding.data_gaps
            existing.suggested_action = finding.suggested_action
            existing.last_detected_at = finding.last_detected_at or datetime.now(timezone.utc)
            if finding.resolved_at is not None:
                existing.resolved_at = finding.resolved_at
            if finding.notification_sent_at is not None:
                existing.notification_sent_at = finding.notification_sent_at
            if finding.severity_history:
                existing.severity_history = finding.severity_history
            return existing
        else:
            self._proactive_findings[finding.id] = finding
            return finding

    def get_proactive_finding(self, finding_id: str) -> Optional[ProactiveFinding]:
        return self._proactive_findings.get(finding_id)

    def get_proactive_finding_by_fingerprint(self, fingerprint: str) -> Optional[ProactiveFinding]:
        for f in self._proactive_findings.values():
            if f.fingerprint == fingerprint:
                return f
        return None

    def list_proactive_findings(
        self,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        severity: Optional[str] = None,
        scan_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[ProactiveFinding]:
        findings = list(self._proactive_findings.values())
        if status:
            findings = [f for f in findings if (f.status if isinstance(f.status, str) else f.status.value) == status]
        if domain:
            findings = [f for f in findings if f.domain == domain]
        if severity:
            findings = [f for f in findings if f.severity == severity]
        if scan_id:
            findings = [f for f in findings if f.scan_id == scan_id]
        findings.sort(key=lambda f: f.last_detected_at or datetime.min, reverse=True)
        return findings[:limit]

    # --- Stale Event Recovery (Production Hardening) ---

    def recover_stale_agent_events(self, stale_threshold_seconds: int = 300) -> list[AgentEvent]:
        now = datetime.now(timezone.utc)
        recovered = []
        for e in self._agent_events.values():
            if e.status in (EventStatus.CLAIMED.value, EventStatus.PROCESSING.value):
                # Prefer claimed_at; fall back to created_at for legacy events.
                stamp = e.claimed_at or e.created_at
                try:
                    dt = datetime.fromisoformat(stamp) if stamp else now
                except (TypeError, ValueError):
                    dt = now
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if (now - dt).total_seconds() >= stale_threshold_seconds:
                    if (e.retry_count or 0) < (e.max_retries or 3):
                        e.retry_count = (e.retry_count or 0) + 1
                        e.status = EventStatus.PENDING.value
                        recovered.append(e)
                    else:
                        e.status = EventStatus.FAILED.value
                        e.error_detail = "Max retries exceeded after stale worker timeout"
                        e.processed_at = now.isoformat()
        return recovered

    # --- Authentication & Authorization (Production Hardening) ---

    def create_user(self, user: User) -> User:
        self._users[user.id] = user
        return user

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    def get_user_by_username(self, username: str) -> Optional[User]:
        for u in self._users.values():
            if u.username.lower() == username.lower():
                return u
        return None

    def get_user_by_email(self, email: str) -> Optional[User]:
        for u in self._users.values():
            if u.email.lower() == email.lower():
                return u
        return None

    def update_user(self, user: User) -> Optional[User]:
        if user.id in self._users:
            self._users[user.id] = user
            return user
        return None

    def list_users(self, limit: int = 100) -> list[User]:
        return list(self._users.values())[:limit]

    def create_membership(self, membership: OrganizationMembership) -> OrganizationMembership:
        # Upsert by (user_id, organization_id)
        existing = self.get_membership(membership.user_id, membership.organization_id)
        if existing:
            existing.role = membership.role
            return existing
        self._memberships[membership.id] = membership
        return membership

    def get_membership(self, user_id: str, organization_id: str) -> Optional[OrganizationMembership]:
        for m in self._memberships.values():
            if m.user_id == user_id and m.organization_id == organization_id:
                return m
        return None

    def list_memberships_for_user(self, user_id: str) -> list[OrganizationMembership]:
        return [m for m in self._memberships.values() if m.user_id == user_id]

    def list_memberships_for_org(self, organization_id: str) -> list[OrganizationMembership]:
        return [m for m in self._memberships.values() if m.organization_id == organization_id]

    def delete_membership(self, user_id: str, organization_id: str) -> bool:
        to_del = [k for k, m in self._memberships.items() if m.user_id == user_id and m.organization_id == organization_id]
        if not to_del:
            return False
        for k in to_del:
            del self._memberships[k]
        return True

    # --- Consequential Action Audit Logs (Production Hardening) ---

    def create_audit_log(self, log: AuditLog) -> AuditLog:
        self._audit_logs.append(log)
        return log

    def list_audit_logs(
        self,
        actor_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        logs = list(self._audit_logs)
        if actor_id:
            logs = [l for l in logs if l.actor_id == actor_id]
        if organization_id:
            logs = [l for l in logs if l.organization_id == organization_id]
        if entity_type:
            logs = [l for l in logs if l.entity_type == entity_type]
        if entity_id:
            logs = [l for l in logs if l.entity_id == entity_id]
        if action:
            logs = [l for l in logs if l.action == action]
        logs.sort(key=lambda l: l.timestamp or datetime.min, reverse=True)
        return logs[offset : offset + limit]



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
        export DATABASE_URL=postgresql://user:pass@localhost:5433/reliefos
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
    if memory_mode not in ("1", "true", "yes"):
        print("  [REPOSITORY WARNING] DATABASE_URL not set — running with InMemoryRepository fallback (multi-district data missing)")
    _default_repository = InMemoryRepository()
    return _default_repository


def set_repository(repo: DataRepository) -> None:
    """Replace the default repository (for testing or production wiring)."""
    global _default_repository, _repository_explicitly_set
    _default_repository = repo
    _repository_explicitly_set = True


def reset_repository() -> None:
    """Drop the cached repository so the next get_repository() re-selects
    from the environment (DATABASE_URL → PostgresRepository, RELIEFOS_MEMORY
    or default → InMemoryRepository).

    NOTE: this does NOT force memory mode. Tests that need memory must set
    RELIEFOS_MEMORY=1 (or call set_repository(InMemoryRepository())
    explicitly); tests claiming to exercise PostgreSQL must assert
    type(get_repository()).__name__ == "PostgresRepository". A previous
    version of this function unconditionally cached an InMemoryRepository,
    which silently downgraded DATABASE_URL runs to memory mode.
    """
    global _default_repository, _repository_explicitly_set
    _default_repository = None
    _repository_explicitly_set = False
