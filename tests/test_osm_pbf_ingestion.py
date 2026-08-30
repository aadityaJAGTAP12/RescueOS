"""
Regression tests for OSM PBF ingestion — Phase 5B.1 geometry conversion fix.

Verifies that:
1. load_district_polygons() correctly converts PostGIS WKT to Shapely geometries
2. All four target districts load successfully
3. Geometry types are Polygon/MultiPolygon
4. District IDs are preserved
5. No geometry coordinate corruption
"""

import os
import pytest
from shapely.geometry import Polygon, MultiPolygon, shape
from shapely import wkt as shapely_wkt

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

_db_available = False
if DATABASE_URL:
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _db_available = True
    except Exception:
        pass

pytestmark = pytest.mark.skipif(
    not _db_available,
    reason="PostgreSQL not available. Set DATABASE_URL and ensure DB is running."
)


@pytest.fixture(scope="module")
def db_engine():
    """Shared engine for all tests in this module."""
    from sqlalchemy import create_engine
    engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def db_repo(db_engine):
    """Create PostgresRepository, yield it. Seeds districts if empty."""
    from agent.data.schema import create_all_tables
    from sqlalchemy import text
    create_all_tables(db_engine)
    from agent.data.postgres_repository import PostgresRepository
    repo = PostgresRepository(engine=db_engine)
    # Ensure districts exist for load_district_polygons tests
    with db_engine.connect() as conn:
        result = conn.execute(text("SELECT count(*) FROM districts"))
        count = result.fetchone()[0]
        if count == 0:
            for did, name in [("sivasagar","Sivasagar"),("jorhat","Jorhat"),("charaideo","Charaideo"),("golaghat","Golaghat")]:
                conn.execute(text("INSERT INTO districts (id, name) VALUES (:id, :name) ON CONFLICT (id) DO NOTHING"), {"id": did, "name": name})
            conn.commit()
    yield repo


# ===================================================================
# CORE BUG REGRESSION: WKT -> Shapely conversion
# ===================================================================

class TestWktToShapelyConversion:
    """
    Regression test for the exact failure:
    shape({"type": "WKT", "wkt": row.wkt}) raises GeometryTypeError

    This test constructs the same data form PostgresRepository provides
    and verifies load_district_polygons() produces valid Shapely geometries.
    """

    def test_wkt_loads_converts_polygon(self):
        """shapely.wkt.loads() correctly parses a PostGIS WKT Polygon."""
        wkt_str = "POLYGON ((94.48 26.48, 94.52 26.48, 94.52 26.50, 94.48 26.50, 94.48 26.48))"
        geom = shapely_wkt.loads(wkt_str)
        assert geom is not None
        assert not geom.is_empty
        assert geom.geom_type == "Polygon"
        assert isinstance(geom, Polygon)

    def test_wkt_loads_converts_multipolygon(self):
        """shapely.wkt.loads() correctly parses a PostGIS WKT MultiPolygon."""
        wkt_str = (
            "MULTIPOLYGON ("
            "((94.48 26.48, 94.52 26.48, 94.52 26.50, 94.48 26.50, 94.48 26.48)), "
            "((94.60 26.55, 94.64 26.55, 94.64 26.57, 94.60 26.57, 94.60 26.55))"
            ")"
        )
        geom = shapely_wkt.loads(wkt_str)
        assert geom is not None
        assert not geom.is_empty
        assert geom.geom_type == "MultiPolygon"
        assert isinstance(geom, MultiPolygon)

    def test_shapely_shape_rejects_wkt_type(self):
        """The OLD buggy code — shape() cannot parse a 'WKT' type dict."""
        from shapely.errors import GeometryTypeError
        with pytest.raises(GeometryTypeError):
            shape({"type": "WKT", "wkt": "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))"})

    def test_wkt_with_srid_prefix(self):
        """PostGIS WKT with SRID=4326 prefix is handled by stripping SRID."""
        wkt_str = "SRID=4326;POLYGON ((94.48 26.48, 94.52 26.48, 94.52 26.50, 94.48 26.50, 94.48 26.48))"
        # Strip SRID prefix (as the fixed code does)
        if wkt_str.upper().startswith("SRID="):
            wkt_str = wkt_str.split(";", 1)[1]
        geom = shapely_wkt.loads(wkt_str)
        assert geom is not None
        assert geom.geom_type == "Polygon"
        assert isinstance(geom, Polygon)

    def test_load_district_polygons_returns_valid_geometries(self, db_repo):
        """load_district_polygons() returns valid Shapely geometries for all districts."""
        from scripts.ingest.osm_pbf import load_district_polygons
        polygons = load_district_polygons(db_repo)

        assert len(polygons) >= 1, "At least one district polygon should load"

        for did, geom in polygons.items():
            assert geom is not None, f"[{did}] geometry is None"
            assert not geom.is_empty, f"[{did}] geometry is empty"
            assert geom.geom_type in ("Polygon", "MultiPolygon"), \
                f"[{did}] unexpected geometry type: {geom.geom_type}"
            assert isinstance(geom, (Polygon, MultiPolygon)), \
                f"[{did}] not a Shapely Polygon/MultiPolygon instance"

    def test_all_four_districts_load(self, db_repo):
        """All four target districts must load successfully."""
        from scripts.ingest.osm_pbf import load_district_polygons, TARGET_DISTRICTS
        polygons = load_district_polygons(db_repo)

        for did in TARGET_DISTRICTS:
            assert did in polygons, f"District '{did}' not found in loaded polygons"
            geom = polygons[did]
            assert geom is not None, f"[{did}] geometry is None"
            assert geom.geom_type in ("Polygon", "MultiPolygon"), \
                f"[{did}] unexpected type: {geom.geom_type}"

    def test_district_ids_are_correct(self, db_repo):
        """District IDs in the returned dict must match TARGET_DISTRICTS."""
        from scripts.ingest.osm_pbf import load_district_polygons, TARGET_DISTRICTS
        polygons = load_district_polygons(db_repo)
        assert set(polygons.keys()) == set(TARGET_DISTRICTS)

    def test_geometry_coordinates_are_valid(self, db_repo):
        """Geometry coordinates must be real numbers (not NaN/inf)."""
        import math
        from scripts.ingest.osm_pbf import load_district_polygons
        polygons = load_district_polygons(db_repo)

        for did, geom in polygons.items():
            coords = list(geom.exterior.coords)
            for x, y in coords:
                assert math.isfinite(x) and math.isfinite(y), \
                    f"[{did}] non-finite coordinate: ({x}, {y})"

    def test_geometry_bounds_are_reasonable(self, db_repo):
        """Geometry bounding boxes should be in the Assam region (~26-27N, ~94-95E)."""
        from scripts.ingest.osm_pbf import load_district_polygons
        polygons = load_district_polygons(db_repo)

        for did, geom in polygons.items():
            minx, miny, maxx, maxy = geom.bounds
            assert 90.0 < minx < 100.0, f"[{did}] longitude min {minx} out of range"
            assert 20.0 < miny < 35.0, f"[{did}] latitude min {miny} out of range"
            assert 90.0 < maxx < 100.0, f"[{did}] longitude max {maxx} out of range"
            assert 20.0 < maxy < 35.0, f"[{did}] latitude max {maxy} out of range"

    def test_spatial_filtering_works_with_loaded_polygons(self, db_repo):
        """Spatial filtering should work with the loaded district geometries."""
        from scripts.ingest.osm_pbf import load_district_polygons, filter_by_districts
        import geopandas as gpd
        from shapely.geometry import Point

        polygons = load_district_polygons(db_repo)
        if not polygons:
            pytest.skip("No district polygons loaded")

        # Create a small GeoDataFrame with points inside and outside the first district
        first_did = list(polygons.keys())[0]
        first_poly = polygons[first_did]
        centroid = first_poly.centroid

        gdf = gpd.GeoDataFrame(
            {"id": ["inside", "outside"]},
            geometry=[Point(centroid.x, centroid.y), Point(0, 0)],
            crs="EPSG:4326",
        )

        filtered = filter_by_districts(gdf, {first_did: first_poly})
        inside_count = len(filtered.get(first_did, gdf.iloc[:0]))
        assert inside_count >= 1, "Point inside district should be filtered in"
