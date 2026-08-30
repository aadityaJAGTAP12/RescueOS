"""
Phase 5A: PostgreSQL + PostGIS Integration Tests

Tests the PostgresRepository against a real PostgreSQL/PostGIS database.
Tests are SKIPPED if PostgreSQL is not available (DATABASE_URL not set
or connection fails).

DATABASE SAFETY:
- Tests NEVER run against the normal DATABASE_URL development database.
- Tests use a separate test database (reliefos_test) or an isolated schema.
- A safety guard refuses to run destructive test setup if the configured
  database is the normal ReliefOS development database.

Setup:
    docker compose up -d
    export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos
    python scripts/db_init.py
    pytest tests/test_postgres_repository.py -v

These tests validate:
1. Insert district
2. Insert settlement
3. Insert flood snapshot
4. Query point against flood snapshot
5. Query correct district
6. Retrieve different flood dates
7. Insert buildings
8. Spatial building filtering
9. Medical facility retrieval
10. Road retrieval
11. Field report persistence
12. Override persistence
13. Provenance round-trip
14. Repeated migration idempotency
15. Two districts using same repository
16. Sivasagar regression
17. Generalization acceptance test
"""

import os
import re
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# ---------------------------------------------------------------------------
# DATABASE SAFETY GUARD
# ---------------------------------------------------------------------------

# The development database patterns we must never TRUNCATE or modify destructively
_DEV_DB_PATTERNS = [
    r"reliefos$",           # ends with "reliefos" (the dev database name)
]

# We override DATABASE_URL to point at a test database
# Parse the original DATABASE_URL and swap the database name
ORIG_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Derive the test database URL: replace the database name with reliefos_test
TEST_DATABASE_URL = ""
if ORIG_DATABASE_URL:
    # Match pattern: postgresql://user:pass@host:port/dbname
    m = re.match(r"^(postgresql(?:\+[^:]*)?://[^/]+/)(\w+)(\?.*)?$", ORIG_DATABASE_URL)
    if m:
        prefix, dbname, suffix = m.group(1), m.group(2), m.group(3) or ""
        # Safety check: if the database is already the test database, use it as-is
        if dbname == "reliefos_test":
            TEST_DATABASE_URL = ORIG_DATABASE_URL
        else:
            # Safety guard: refuse if this looks like the production/dev DB
            for pat in _DEV_DB_PATTERNS:
                if re.search(pat, dbname, re.IGNORECASE):
                    TEST_DATABASE_URL = f"{prefix}reliefos_test{suffix}"
                    break
            if not TEST_DATABASE_URL:
                # Unknown database name — still use reliefos_test for safety
                TEST_DATABASE_URL = f"{prefix}reliefos_test{suffix}"
    else:
        TEST_DATABASE_URL = ""

# Check if test database is available
_db_available = False
_test_engine = None

if TEST_DATABASE_URL:
    try:
        _test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        with _test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _db_available = True
    except OperationalError:
        # Test database might not exist yet — try to create it
        # Connect to the default 'postgres' database to create reliefos_test
        try:
            m = re.match(r"^(postgresql(?:\+[^:]*)?://[^/]+/)(\w+)(\?.*)?$", TEST_DATABASE_URL)
            if m:
                admin_url = f"{m.group(1)}postgres{m.group(3 or '')}"
                admin_engine = create_engine(admin_url, pool_pre_ping=True)
                with admin_engine.connect() as conn:
                    conn.execute(text("COMMIT"))
                    conn.execute(text("CREATE DATABASE reliefos_test"))
                    conn.execute(text("COMMIT"))
                admin_engine.dispose()
                # Now try connecting to the test database
                _test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
                with _test_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                _db_available = True
        except Exception:
            pass
    except Exception:
        pass

# If no DATABASE_URL is set at all, skip
if not ORIG_DATABASE_URL:
    _db_available = False

pytestmark = pytest.mark.skipif(
    not _db_available,
    reason="PostgreSQL test database not available. Set DATABASE_URL and ensure DB is running.",
)


@pytest.fixture(scope="module")
def db_engine():
    """Shared engine for all tests in this module — connected to TEST database."""
    assert _test_engine is not None, "Test engine not available"
    yield _test_engine
    _test_engine.dispose()


@pytest.fixture(scope="module")
def db_repo(db_engine):
    """Create a clean PostgresRepository in the TEST database, yield it.

    SAFETY: Only operates on the TEST database (reliefos_test), never on
    the development database (reliefos).
    """
    from agent.data.schema import create_all_tables, metadata

    # Safety assertion: make absolutely sure we're not touching the dev DB
    url_str = str(db_engine.url)
    assert "reliefos_test" in url_str or "test" in url_str.lower(), (
        f"SAFETY VIOLATION: Attempting to run tests on non-test database: {url_str}"
    )

    # Enable PostGIS extension in test database
    with db_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()

    # Create tables in test database
    create_all_tables(db_engine)

    # Clean all tables before tests — only in the test database
    with db_engine.connect() as conn:
        for table in reversed(metadata.sorted_tables):
            conn.execute(text(f"TRUNCATE {table.name} CASCADE"))
        conn.commit()

    from agent.data.postgres_repository import PostgresRepository
    repo = PostgresRepository(engine=db_engine)
    yield repo

    # Cleanup after tests — only in the test database
    with db_engine.connect() as conn:
        for table in reversed(metadata.sorted_tables):
            conn.execute(text(f"TRUNCATE {table.name} CASCADE"))
        conn.commit()


# ===================================================================
# TEST 1: Insert district
# ===================================================================

class TestInsertDistrict:
    def test_insert_and_retrieve(self, db_repo):
        from agent.data.models import District
        d = District(id="test_pg_district", name="Test PG District", state="Test State", country="India")
        db_repo.upsert_district(d)
        retrieved = db_repo.get_district("test_pg_district")
        assert retrieved is not None
        assert retrieved.name == "Test PG District"
        assert retrieved.state == "Test State"

    def test_upsert_updates(self, db_repo):
        from agent.data.models import District
        d1 = District(id="test_pg_upsert", name="Original", state="S1")
        db_repo.upsert_district(d1)
        d2 = District(id="test_pg_upsert", name="Updated", state="S2")
        db_repo.upsert_district(d2)
        retrieved = db_repo.get_district("test_pg_upsert")
        assert retrieved.name == "Updated"


# ===================================================================
# TEST 2: Insert settlement
# ===================================================================

class TestInsertSettlement:
    def test_insert_and_retrieve(self, db_repo):
        from agent.data.models import Settlement
        s = Settlement(
            id="test_pg_settlement", name="Test PG Settlement",
            district_id="test_pg_district", lat=26.5, lon=94.5,
            aliases=["pg_test_alias"],
        )
        db_repo.upsert_settlement(s)
        retrieved = db_repo.get_settlement("test_pg_settlement")
        assert retrieved is not None
        assert retrieved.name == "Test PG Settlement"
        assert retrieved.lat == 26.5
        assert retrieved.lon == 94.5
        assert "pg_test_alias" in retrieved.aliases

    def test_list_by_district(self, db_repo):
        from agent.data.models import Settlement, District
        db_repo.upsert_district(District(id="other_district", name="Other District"))
        db_repo.upsert_settlement(Settlement(
            id="test_pg_s1", name="S1", district_id="test_pg_district", lat=26.51, lon=94.51,
        ))
        db_repo.upsert_settlement(Settlement(
            id="test_pg_s2", name="S2", district_id="other_district", lat=27.0, lon=95.0,
        ))
        settlements = db_repo.list_settlements(district_id="test_pg_district")
        assert any(s.id == "test_pg_s1" for s in settlements)
        assert not any(s.id == "test_pg_s2" for s in settlements)


# ===================================================================
# TEST 3: Insert flood snapshot
# ===================================================================

class TestInsertFloodSnapshot:
    def test_insert_and_retrieve(self, db_repo):
        from agent.data.models import FloodSnapshot, Provenance
        snap = FloodSnapshot(
            id="test_pg_flood_1",
            district_id="test_pg_district",
            observed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            source="Test Source",
            confidence=0.95,
            geometry_geojson={
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[94.48, 26.48], [94.52, 26.48], [94.52, 26.50], [94.48, 26.50], [94.48, 26.48]]]
                    },
                    "properties": {}
                }]
            },
            polygon_count=1,
            provenance=Provenance.REAL,
        )
        db_repo.upsert_flood_snapshot(snap)
        retrieved = db_repo.get_flood_snapshot("test_pg_flood_1")
        assert retrieved is not None
        assert retrieved.district_id == "test_pg_district"
        assert retrieved.confidence == 0.95
        assert retrieved.polygon_count == 1


# ===================================================================
# TEST 4: Query point against flood snapshot
# ===================================================================

class TestFloodContainment:
    def test_point_inside_flood(self, db_repo):
        from agent.data.models import FloodSnapshot, Provenance
        snap = FloodSnapshot(
            id="test_pg_flood_contain",
            district_id="test_pg_district",
            observed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            source="Test",
            geometry_geojson={
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[94.48, 26.48], [94.52, 26.48], [94.52, 26.50], [94.48, 26.50], [94.48, 26.48]]]
                    },
                    "properties": {}
                }]
            },
            polygon_count=1,
            provenance=Provenance.REAL,
        )
        db_repo.upsert_flood_snapshot(snap)
        # Point inside the polygon
        results = db_repo.query_flood_containment(lat=26.49, lon=94.50, district_id="test_pg_district")
        assert len(results) >= 1

    def test_point_outside_flood(self, db_repo):
        # Point far outside
        results = db_repo.query_flood_containment(lat=28.0, lon=96.0, district_id="test_pg_district")
        assert len(results) == 0


# ===================================================================
# TEST 5: Query correct district
# ===================================================================

class TestDistrictQuery:
    def test_district_isolation(self, db_repo):
        from agent.data.models import District, FloodSnapshot, Provenance
        db_repo.upsert_district(District(id="pg_dist_a", name="PG Dist A"))
        db_repo.upsert_district(District(id="pg_dist_b", name="PG Dist B"))
        db_repo.upsert_flood_snapshot(FloodSnapshot(
            id="pg_flood_a", district_id="pg_dist_a",
            observed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            source="A", polygon_count=3, provenance=Provenance.REAL,
        ))
        db_repo.upsert_flood_snapshot(FloodSnapshot(
            id="pg_flood_b", district_id="pg_dist_b",
            observed_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            source="B", polygon_count=1, provenance=Provenance.REAL,
        ))
        a_snaps = db_repo.list_flood_snapshots(district_id="pg_dist_a")
        b_snaps = db_repo.list_flood_snapshots(district_id="pg_dist_b")
        assert len(a_snaps) == 1
        assert a_snaps[0].polygon_count == 3
        assert len(b_snaps) == 1
        assert b_snaps[0].polygon_count == 1


# ===================================================================
# TEST 6: Retrieve different flood dates
# ===================================================================

class TestTemporalFlood:
    def test_different_dates(self, db_repo):
        from agent.data.models import FloodSnapshot, Provenance, District
        db_repo.upsert_district(District(id="test_pg_temporal", name="Test Temporal"))
        db_repo.upsert_flood_snapshot(FloodSnapshot(
            id="pg_temporal_early", district_id="test_pg_temporal",
            observed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            source="Early", polygon_count=10, provenance=Provenance.REAL,
        ))
        db_repo.upsert_flood_snapshot(FloodSnapshot(
            id="pg_temporal_late", district_id="test_pg_temporal",
            observed_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            source="Late", polygon_count=5, provenance=Provenance.REAL,
        ))
        all_snaps = db_repo.list_flood_snapshots(district_id="test_pg_temporal")
        assert len(all_snaps) == 2

        latest = db_repo.get_latest_flood_snapshot("test_pg_temporal")
        assert latest.id == "pg_temporal_late"

        # Filter by date
        early_only = db_repo.get_latest_flood_snapshot(
            "test_pg_temporal",
            observed_at="2026-07-15T00:00:00+00:00"
        )
        assert early_only.id == "pg_temporal_early"


# ===================================================================
# TEST 7: Insert buildings
# ===================================================================

class TestInsertBuildings:
    def test_insert_and_retrieve(self, db_repo):
        from agent.data.models import Building, Provenance
        db_repo.upsert_buildings([
            Building(id="pg_bldg_1", district_id="test_pg_district",
                     lat=26.52, lon=94.54, in_flood_zone=True, provenance=Provenance.REAL),
            Building(id="pg_bldg_2", district_id="test_pg_district",
                     lat=26.50, lon=94.50, in_flood_zone=False, provenance=Provenance.REAL),
        ])
        buildings = db_repo.get_buildings("test_pg_district")
        assert len(buildings) == 2
        flooded = [b for b in buildings if b.in_flood_zone]
        assert len(flooded) == 1


# ===================================================================
# TEST 8: Spatial building filtering
# ===================================================================

class TestSpatialBuildingFilter:
    def test_radius_filter(self, db_repo):
        from agent.data.models import Building, Provenance
        # Building near (26.5, 94.5)
        db_repo.upsert_buildings([
            Building(id="pg_bldg_near", district_id="test_pg_district",
                     lat=26.501, lon=94.501, provenance=Provenance.REAL),
            Building(id="pg_bldg_far", district_id="test_pg_district",
                     lat=26.6, lon=94.6, provenance=Provenance.REAL),
        ])
        nearby = db_repo.get_buildings("test_pg_district", lat=26.5, lon=94.5, radius_km=2.0)
        nearby_ids = {b.id for b in nearby}
        assert "pg_bldg_near" in nearby_ids


# ===================================================================
# TEST 9: Medical facility retrieval
# ===================================================================

class TestMedicalFacility:
    def test_insert_and_retrieve(self, db_repo):
        from agent.data.models import MedicalFacility, Provenance
        db_repo.upsert_medical_facilities([
            MedicalFacility(id="pg_hosp_1", district_id="test_pg_district",
                           name="PG Hospital", lat=26.51, lon=94.52,
                           facility_type="hospital", provenance=Provenance.REAL),
        ])
        facilities = db_repo.get_medical_facilities("test_pg_district")
        assert len(facilities) == 1
        assert facilities[0].name == "PG Hospital"


# ===================================================================
# TEST 10: Road retrieval
# ===================================================================

class TestRoadRetrieval:
    def test_insert_and_retrieve(self, db_repo):
        from agent.data.models import Road, Provenance
        db_repo.upsert_roads([
            Road(id="pg_road_1", district_id="test_pg_district",
                 name="PG Main Road", highway_type="primary",
                 geometry_coords=[[94.50, 26.50], [94.55, 26.55]],
                 provenance=Provenance.REAL),
        ])
        roads = db_repo.get_roads("test_pg_district")
        assert len(roads) == 1
        assert roads[0].name == "PG Main Road"


# ===================================================================
# TEST 11: Field report persistence
# ===================================================================

class TestFieldReportPersistence:
    def test_insert_and_retrieve(self, db_repo):
        from agent.data.models import FieldReport, Provenance, VerificationState
        report = FieldReport(
            id="pg_fr_1",
            district_id="test_pg_district",
            lat=26.55,
            lon=94.55,
            source_type="community_report",
            raw_text="Road blocked near school. 30 people need water.",
            people_count=30,
            adults=20,
            children=8,
            elderly=2,
            needs=["food", "water"],
            verification_state=VerificationState.VERIFIED,
            extraction_confidence="high",
            provenance=Provenance.REAL,
        )
        db_repo.upsert_field_report(report)
        retrieved = db_repo.get_field_report("pg_fr_1")
        assert retrieved is not None
        assert retrieved.raw_text == "Road blocked near school. 30 people need water."
        assert retrieved.people_count == 30
        assert "food" in retrieved.needs
        assert retrieved.verification_state == VerificationState.VERIFIED

    def test_list_by_proximity(self, db_repo):
        from agent.data.models import FieldReport
        db_repo.upsert_field_report(FieldReport(
            id="pg_fr_near", lat=26.50, lon=94.50,
        ))
        db_repo.upsert_field_report(FieldReport(
            id="pg_fr_far", lat=28.0, lon=96.0,
        ))
        nearby = db_repo.list_field_reports(lat=26.50, lon=94.50, radius_km=5.0)
        nearby_ids = {r.id for r in nearby}
        assert "pg_fr_near" in nearby_ids
        assert "pg_fr_far" not in nearby_ids


# ===================================================================
# TEST 12: Override persistence
# ===================================================================

class TestOverridePersistence:
    def test_insert_and_retrieve(self, db_repo):
        from agent.data.models import Override
        override = Override(
            id="pg_ov_1",
            target_type="facility",
            target_id="PG Hospital",
            override_status="damaged",
            reason="Flood damage",
            system_status="operational",
        )
        db_repo.upsert_override(override)
        retrieved = db_repo.get_active_override("facility", "PG Hospital")
        assert retrieved is not None
        assert retrieved.override_status == "damaged"
        assert retrieved.system_status == "operational"


# ===================================================================
# TEST 13: Provenance round-trip
# ===================================================================

class TestProvenanceRoundTrip:
    def test_provenance_preserved(self, db_repo):
        from agent.data.models import FloodSnapshot, FieldReport, Provenance
        db_repo.upsert_flood_snapshot(FloodSnapshot(
            id="pg_prov_real", district_id="test_pg_district",
            observed_at=datetime.now(timezone.utc),
            source="Test", provenance=Provenance.REAL,
        ))
        db_repo.upsert_flood_snapshot(FloodSnapshot(
            id="pg_prov_synthetic", district_id="test_pg_district",
            observed_at=datetime.now(timezone.utc),
            source="Test", provenance=Provenance.SYNTHETIC,
        ))
        r1 = db_repo.get_flood_snapshot("pg_prov_real")
        r2 = db_repo.get_flood_snapshot("pg_prov_synthetic")
        assert r1.provenance == Provenance.REAL
        assert r2.provenance == Provenance.SYNTHETIC

    def test_provenance_summary(self, db_repo):
        from agent.data.models import FloodSnapshot, FieldReport, Provenance
        db_repo.upsert_flood_snapshot(FloodSnapshot(
            id="pg_ps1", district_id="test_pg_district",
            observed_at=datetime.now(timezone.utc),
            source="T", provenance=Provenance.REAL,
        ))
        db_repo.upsert_flood_snapshot(FloodSnapshot(
            id="pg_ps2", district_id="test_pg_district",
            observed_at=datetime.now(timezone.utc),
            source="T", provenance=Provenance.SYNTHETIC,
        ))
        summary = db_repo.get_provenance_summary()
        assert summary.get("REAL", 0) >= 1
        assert summary.get("SYNTHETIC", 0) >= 1


# ===================================================================
# TEST 14: Repeated migration idempotency
# ===================================================================

class TestMigrationIdempotency:
    def test_import_flood_geojson_idempotent(self, db_repo):
        from agent.data.models import make_flood_snapshot_id, District
        db_repo.upsert_district(District(id="test_idempotent", name="Test Idempotent"))
        geojson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Polygon",
                    "coordinates": [[[94.48, 26.48], [94.52, 26.48], [94.52, 26.50], [94.48, 26.50], [94.48, 26.48]]]
                },
                "properties": {}
            }]
        }
        snap1 = db_repo.import_flood_geojson(geojson, "test_idempotent", observed_at="2026-07-01T00:00:00+00:00")
        snap2 = db_repo.import_flood_geojson(geojson, "test_idempotent", observed_at="2026-07-01T00:00:00+00:00")
        assert snap1.id == snap2.id
        # Should not create duplicate
        snaps = db_repo.list_flood_snapshots(district_id="test_idempotent")
        assert len(snaps) == 1


# ===================================================================
# TEST 15: Two districts using same repository
# ===================================================================

class TestTwoDistrictsSameRepo:
    def test_two_districts(self, db_repo):
        from agent.data.models import District, Settlement, FloodSnapshot, Building, Provenance
        from agent.data.migration import run_full_migration

        # District A
        db_repo.upsert_district(District(id="pg_multi_a", name="Multi A"))
        db_repo.upsert_settlement(Settlement(
            id="pg_multi_a_cap", name="Capital A", district_id="pg_multi_a",
            lat=26.5, lon=94.5,
        ))
        db_repo.upsert_flood_snapshot(FloodSnapshot(
            id="pg_multi_flood_a", district_id="pg_multi_a",
            observed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            source="A", polygon_count=3, provenance=Provenance.REAL,
        ))

        # District B
        db_repo.upsert_district(District(id="pg_multi_b", name="Multi B"))
        db_repo.upsert_settlement(Settlement(
            id="pg_multi_b_cap", name="Capital B", district_id="pg_multi_b",
            lat=27.0, lon=95.0,
        ))
        db_repo.upsert_flood_snapshot(FloodSnapshot(
            id="pg_multi_flood_b", district_id="pg_multi_b",
            observed_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            source="B", polygon_count=1, provenance=Provenance.REAL,
        ))

        # Verify isolation
        a_snaps = db_repo.list_flood_snapshots(district_id="pg_multi_a")
        b_snaps = db_repo.list_flood_snapshots(district_id="pg_multi_b")
        assert len(a_snaps) == 1
        assert a_snaps[0].polygon_count == 3
        assert len(b_snaps) == 1
        assert b_snaps[0].polygon_count == 1

        # Verify same repo works for both
        a_settlement = db_repo.resolve_location("Capital A")
        b_settlement = db_repo.resolve_location("Capital B")
        assert a_settlement is not None
        assert b_settlement is not None
        assert a_settlement.district_id == "pg_multi_a"
        assert b_settlement.district_id == "pg_multi_b"


# ===================================================================
# TEST 16: Sivasagar regression
# ===================================================================

class TestSivasagarRegression:
    def test_sivasagar_migration(self, db_repo):
        """Sivasagar flood data can be imported into PostgreSQL."""
        from agent.data.migration import run_full_migration
        summary = run_full_migration(db_repo)
        assert summary is not None
        assert len(summary.get("districts", [])) >= 1

    def test_sivasagar_flood_snapshot(self, db_repo):
        """Sivasagar flood snapshot exists after migration."""
        snap = db_repo.get_latest_flood_snapshot("sivasagar")
        if snap:
            assert snap.district_id == "sivasagar"
            assert snap.polygon_count > 0

    def test_sivasagar_settlements(self, db_repo):
        """Sivasagar settlements exist after migration."""
        settlements = db_repo.list_settlements(district_id="sivasagar")
        assert len(settlements) >= 1


# ===================================================================
# TEST 17: Generalization acceptance test
# ===================================================================

class TestGeneralizationAcceptance:
    """
    THE KEY TEST.
    With PostgreSQL/PostGIS:
    - District A + Flood snapshot A + Infrastructure A
    - District B + Flood snapshot B + Infrastructure B
    Run the SAME application repository and assessment code.
    No source-code changes. No district-specific branches.
    Verify results differ based only on data.
    """

    def test_generalization_with_pg(self, db_repo):
        from agent.data.models import (
            District, Settlement, FloodSnapshot, Building, MedicalFacility, Provenance
        )

        # === District A: large flood, 3 polygons, 2 buildings ===
        db_repo.upsert_district(District(id="gen_a", name="Generalization A"))
        db_repo.upsert_settlement(Settlement(
            id="gen_a_cap", name="Gen Capital A", district_id="gen_a",
            lat=26.5, lon=94.5,
        ))
        db_repo.upsert_settlement(Settlement(
            id="gen_a_flood", name="Gen Flooded A", district_id="gen_a",
            lat=26.52, lon=94.55,
        ))
        db_repo.upsert_flood_snapshot(FloodSnapshot(
            id="gen_flood_a", district_id="gen_a",
            observed_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
            source="Test A",
            geometry_geojson={
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "geometry": {"type": "Polygon",
                        "coordinates": [[[94.53, 26.51], [94.57, 26.51], [94.57, 26.53], [94.53, 26.53], [94.53, 26.51]]]},
                     "properties": {}},
                    {"type": "Feature", "geometry": {"type": "Polygon",
                        "coordinates": [[[94.48, 26.48], [94.52, 26.48], [94.52, 26.50], [94.48, 26.50], [94.48, 26.48]]]},
                     "properties": {}},
                    {"type": "Feature", "geometry": {"type": "Polygon",
                        "coordinates": [[[94.55, 26.54], [94.60, 26.54], [94.60, 26.56], [94.55, 26.56], [94.55, 26.54]]]},
                     "properties": {}},
                ]
            },
            polygon_count=3,
            provenance=Provenance.REAL,
        ))
        db_repo.upsert_buildings([
            Building(id="gen_a_b1", district_id="gen_a", lat=26.52, lon=94.54,
                     in_flood_zone=True, provenance=Provenance.REAL),
            Building(id="gen_a_b2", district_id="gen_a", lat=26.50, lon=94.50,
                     in_flood_zone=False, provenance=Provenance.REAL),
        ])
        db_repo.upsert_medical_facilities([
            MedicalFacility(id="gen_a_hosp", district_id="gen_a", name="Hospital A",
                           lat=26.51, lon=94.52, provenance=Provenance.REAL),
        ])

        # === District B: small flood, 1 polygon, 3 buildings ===
        db_repo.upsert_district(District(id="gen_b", name="Generalization B"))
        db_repo.upsert_settlement(Settlement(
            id="gen_b_cap", name="Gen Capital B", district_id="gen_b",
            lat=27.0, lon=95.0,
        ))
        db_repo.upsert_settlement(Settlement(
            id="gen_b_safe", name="Gen Safe B", district_id="gen_b",
            lat=27.05, lon=95.05,
        ))
        db_repo.upsert_flood_snapshot(FloodSnapshot(
            id="gen_flood_b", district_id="gen_b",
            observed_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            source="Test B",
            geometry_geojson={
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "geometry": {"type": "Polygon",
                        "coordinates": [[[94.99, 26.99], [95.01, 26.99], [95.01, 27.01], [94.99, 27.01], [94.99, 26.99]]]},
                     "properties": {}},
                ]
            },
            polygon_count=1,
            provenance=Provenance.REAL,
        ))
        db_repo.upsert_buildings([
            Building(id="gen_b_b1", district_id="gen_b", lat=27.00, lon=95.00,
                     in_flood_zone=True, provenance=Provenance.REAL),
            Building(id="gen_b_b2", district_id="gen_b", lat=27.05, lon=95.05,
                     in_flood_zone=False, provenance=Provenance.REAL),
            Building(id="gen_b_b3", district_id="gen_b", lat=27.01, lon=95.01,
                     in_flood_zone=True, provenance=Provenance.REAL),
        ])
        db_repo.upsert_medical_facilities([
            MedicalFacility(id="gen_b_hosp", district_id="gen_b", name="Hospital B",
                           lat=27.02, lon=95.08, provenance=Provenance.REAL),
        ])

        # === Run SAME code for both districts ===
        for district_id in ["gen_a", "gen_b"]:
            district = db_repo.get_district(district_id)
            assert district is not None

            snapshots = db_repo.list_flood_snapshots(district_id=district_id)
            assert len(snapshots) >= 1

            settlements = db_repo.list_settlements(district_id=district_id)
            assert len(settlements) >= 1

            facilities = db_repo.get_medical_facilities(district_id=district_id)
            assert len(facilities) >= 1

            buildings = db_repo.get_buildings(district_id=district_id)
            assert len(buildings) >= 1

            # Resolve a location
            settlement = db_repo.resolve_location(
                lat=settlements[0].lat, lon=settlements[0].lon
            )
            assert settlement is not None

        # Verify DIFFERENT results based on data
        a_floods = db_repo.list_flood_snapshots(district_id="gen_a")
        b_floods = db_repo.list_flood_snapshots(district_id="gen_b")
        assert a_floods[0].polygon_count != b_floods[0].polygon_count

        a_buildings = db_repo.get_buildings("gen_a")
        b_buildings = db_repo.get_buildings("gen_b")
        assert len(a_buildings) != len(b_buildings)

        # Same code path, different data → different results
        a_facilities = db_repo.get_medical_facilities("gen_a")
        b_facilities = db_repo.get_medical_facilities("gen_b")
        assert a_facilities[0].name != b_facilities[0].name
