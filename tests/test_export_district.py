"""
Tests for district geometry export to GEE GeoJSON format.

Tests export of all four target districts:
- sivasagar
- jorhat
- charaideo
- golaghat

Uses InMemoryRepository with synthetic but valid district geometries.
No PostGIS required. No external service calls.

Validates:
- Valid GeoJSON output
- District identity (no cross-district geometry substitution)
- Geometry type (Polygon or MultiPolygon)
- CRS is WGS84 (implicit in GeoJSON)
- Required properties present
- Geometry is non-empty
"""

import pytest
from agent.data.repository import InMemoryRepository, set_repository, reset_repository
from agent.data.models import District
from agent.gee.export_district import (
    export_district_geometry,
    export_all_district_geometries,
    validate_district_feature,
    validate_all_features,
    _wkt_to_geojson_geom,
    TARGET_DISTRICTS,
)


# ---------------------------------------------------------------------------
# Test fixtures — synthetic district geometries
# ---------------------------------------------------------------------------

# Small but valid WKT polygons for testing.
# Each district gets a distinct polygon so we can detect cross-district substitution.
# These are NOT real district boundaries — they are minimal test geometries.

DISTRICT_GEOMETRIES = {
    "sivasagar": (
        "SRID=4326;POLYGON((94.60 26.90, 94.70 26.90, 94.70 27.00, 94.60 27.00, 94.60 26.90))"
    ),
    "jorhat": (
        "SRID=4326;POLYGON((94.80 26.70, 94.90 26.70, 94.90 26.80, 94.80 26.80, 94.80 26.70))"
    ),
    "charaideo": (
        "SRID=4326;POLYGON((95.00 26.60, 95.10 26.60, 95.10 26.70, 95.00 26.70, 95.00 26.60))"
    ),
    "golaghat": (
        "SRID=4326;POLYGON((94.30 26.40, 94.40 26.40, 94.40 26.50, 94.30 26.50, 94.30 26.40))"
    ),
}

DISTRICT_NAMES = {
    "sivasagar": "Sivasagar",
    "jorhat": "Jorhat",
    "charaideo": "Charaideo",
    "golaghat": "Golaghat",
}

# MultiPolygon WKT for testing that geometry type is preserved
SIVASAGAR_MULTIPOLYGON_WKT = (
    "SRID=4326;MULTIPOLYGON("
    "((94.60 26.90, 94.70 26.90, 94.70 27.00, 94.60 27.00, 94.60 26.90)),"
    "((94.55 26.85, 94.58 26.85, 94.58 26.88, 94.55 26.88, 94.55 26.85))"
    ")"
)


@pytest.fixture
def repo_with_districts():
    """Create an InMemoryRepository populated with all four target districts."""
    repo = InMemoryRepository()
    for did, wkt in DISTRICT_GEOMETRIES.items():
        district = District(
            id=did,
            name=DISTRICT_NAMES[did],
            state="Assam",
            country="India",
            geometry_wkt=wkt,
        )
        repo.upsert_district(district)
    return repo


@pytest.fixture
def repo_with_multipolygon():
    """Create an InMemoryRepository with a MultiPolygon district."""
    repo = InMemoryRepository()
    district = District(
        id="sivasagar",
        name="Sivasagar",
        state="Assam",
        country="India",
        geometry_wkt=SIVASAGAR_MULTIPOLYGON_WKT,
    )
    repo.upsert_district(district)
    return repo


@pytest.fixture
def repo_empty():
    """Create an empty InMemoryRepository."""
    return InMemoryRepository()


# ---------------------------------------------------------------------------
# Test: export single district geometry
# ---------------------------------------------------------------------------

class TestExportSingleDistrictGeometry:
    """Test export_district_geometry for each target district."""

    def test_export_sivasagar(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        assert feature["type"] == "Feature"
        assert feature["properties"]["district_id"] == "sivasagar"
        assert feature["properties"]["district_name"] == "Sivasagar"

    def test_export_jorhat(self, repo_with_districts):
        feature = export_district_geometry("jorhat", repo=repo_with_districts)
        assert feature["type"] == "Feature"
        assert feature["properties"]["district_id"] == "jorhat"
        assert feature["properties"]["district_name"] == "Jorhat"

    def test_export_charaideo(self, repo_with_districts):
        feature = export_district_geometry("charaideo", repo=repo_with_districts)
        assert feature["type"] == "Feature"
        assert feature["properties"]["district_id"] == "charaideo"
        assert feature["properties"]["district_name"] == "Charaideo"

    def test_export_golaghat(self, repo_with_districts):
        feature = export_district_geometry("golaghat", repo=repo_with_districts)
        assert feature["type"] == "Feature"
        assert feature["properties"]["district_id"] == "golaghat"
        assert feature["properties"]["district_name"] == "Golaghat"


# ---------------------------------------------------------------------------
# Test: valid GeoJSON
# ---------------------------------------------------------------------------

class TestGeoJSONValidity:
    """Verify output is valid GeoJSON."""

    def test_feature_has_type_feature(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        assert feature.get("type") == "Feature"

    def test_feature_has_geometry(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        assert "geometry" in feature
        assert feature["geometry"] is not None

    def test_feature_has_properties(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        assert "properties" in feature
        assert isinstance(feature["properties"], dict)

    def test_geometry_has_type(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        geom = feature["geometry"]
        assert "type" in geom
        assert geom["type"] in ("Polygon", "MultiPolygon")

    def test_geometry_has_coordinates(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        geom = feature["geometry"]
        assert "coordinates" in geom
        assert geom["coordinates"] is not None
        assert len(geom["coordinates"]) > 0

    def test_polygon_geometry_type(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        assert feature["geometry"]["type"] == "Polygon"

    def test_multipolygon_geometry_type(self, repo_with_multipolygon):
        feature = export_district_geometry("sivasagar", repo=repo_with_multipolygon)
        assert feature["geometry"]["type"] == "MultiPolygon"


# ---------------------------------------------------------------------------
# Test: geometry is non-empty
# ---------------------------------------------------------------------------

class TestGeometryNonEmpty:
    """Verify exported geometries are non-empty."""

    def test_sivasagar_nonempty(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        coords = feature["geometry"]["coordinates"]
        assert len(coords) > 0

    def test_jorhat_nonempty(self, repo_with_districts):
        feature = export_district_geometry("jorhat", repo=repo_with_districts)
        coords = feature["geometry"]["coordinates"]
        assert len(coords) > 0

    def test_charaideo_nonempty(self, repo_with_districts):
        feature = export_district_geometry("charaideo", repo=repo_with_districts)
        coords = feature["geometry"]["coordinates"]
        assert len(coords) > 0

    def test_golaghat_nonempty(self, repo_with_districts):
        feature = export_district_geometry("golaghat", repo=repo_with_districts)
        coords = feature["geometry"]["coordinates"]
        assert len(coords) > 0


# ---------------------------------------------------------------------------
# Test: CRS is WGS84
# ---------------------------------------------------------------------------

class TestCRSWGS84:
    """
    GeoJSON spec says CRS is WGS84 by default.
    Verify no explicit CRS field is set (which would be wrong).
    """

    def test_no_crs_field(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        geom = feature["geometry"]
        # GeoJSON should NOT have a "crs" field
        assert "crs" not in geom

    def test_coordinates_are_lon_lat(self, repo_with_districts):
        """Coordinates should be in [lon, lat] order (WGS84)."""
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        ring = feature["geometry"]["coordinates"][0]
        # First point should be in the expected lon/lat range for Assam, India
        lon, lat = ring[0]
        assert 80.0 < lon < 100.0  # Assam longitude range
        assert 20.0 < lat < 30.0  # Assam latitude range


# ---------------------------------------------------------------------------
# Test: district identity (no cross-district substitution)
# ---------------------------------------------------------------------------

class TestDistrictIdentity:
    """Verify each exported feature belongs to the correct district."""

    def test_sivasagar_identity(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        assert feature["properties"]["district_id"] == "sivasagar"

    def test_jorhat_identity(self, repo_with_districts):
        feature = export_district_geometry("jorhat", repo=repo_with_districts)
        assert feature["properties"]["district_id"] == "jorhat"

    def test_charaideo_identity(self, repo_with_districts):
        feature = export_district_geometry("charaideo", repo=repo_with_districts)
        assert feature["properties"]["district_id"] == "charaideo"

    def test_golaghat_identity(self, repo_with_districts):
        feature = export_district_geometry("golaghat", repo=repo_with_districts)
        assert feature["properties"]["district_id"] == "golaghat"

    def test_no_geometry_substitution(self, repo_with_districts):
        """Each district should have different geometry coordinates."""
        geometries = {}
        for did in TARGET_DISTRICTS:
            feature = export_district_geometry(did, repo=repo_with_districts)
            geometries[did] = str(feature["geometry"]["coordinates"])

        # All four should be different
        unique_geometries = set(geometries.values())
        assert len(unique_geometries) == 4, (
            f"Expected 4 unique geometries, got {len(unique_geometries)}. "
            f"Possible cross-district geometry substitution."
        )

    def test_each_district_has_distinct_bbox(self, repo_with_districts):
        """Bounding box of each district should be distinct."""
        bboxes = {}
        for did in TARGET_DISTRICTS:
            feature = export_district_geometry(did, repo=repo_with_districts)
            ring = feature["geometry"]["coordinates"][0]
            lons = [p[0] for p in ring]
            lats = [p[1] for p in ring]
            bboxes[did] = (min(lons), min(lats), max(lons), max(lats))

        unique_bboxes = set(bboxes.values())
        assert len(unique_bboxes) == 4


# ---------------------------------------------------------------------------
# Test: required properties
# ---------------------------------------------------------------------------

class TestRequiredProperties:
    """Verify all required properties are present."""

    def test_has_district_id(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        assert "district_id" in feature["properties"]

    def test_has_district_name(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        assert "district_name" in feature["properties"]

    def test_has_source(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        assert "source" in feature["properties"]

    def test_has_provenance(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        assert "provenance" in feature["properties"]
        assert feature["properties"]["provenance"] == "REAL"

    def test_has_license(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        assert "license" in feature["properties"]


# ---------------------------------------------------------------------------
# Test: export all districts as FeatureCollection
# ---------------------------------------------------------------------------

class TestExportAllDistrictGeometries:
    """Test batch export of all four target districts."""

    def test_returns_featurecollection(self, repo_with_districts):
        fc = export_all_district_geometries(repo=repo_with_districts)
        assert fc["type"] == "FeatureCollection"
        assert "features" in fc

    def test_contains_four_features(self, repo_with_districts):
        fc = export_all_district_geometries(repo=repo_with_districts)
        assert len(fc["features"]) == 4

    def test_all_target_districts_present(self, repo_with_districts):
        fc = export_all_district_geometries(repo=repo_with_districts)
        found_ids = {f["properties"]["district_id"] for f in fc["features"]}
        assert set(TARGET_DISTRICTS).issubset(found_ids)

    def test_no_errors(self, repo_with_districts):
        fc = export_all_district_geometries(repo=repo_with_districts)
        errors = fc.get("_errors") or []
        assert len(errors) == 0

    def test_custom_district_list(self, repo_with_districts):
        fc = export_all_district_geometries(
            district_ids=["sivasagar", "jorhat"],
            repo=repo_with_districts,
        )
        assert len(fc["features"]) == 2
        found_ids = {f["properties"]["district_id"] for f in fc["features"]}
        assert found_ids == {"sivasagar", "jorhat"}


# ---------------------------------------------------------------------------
# Test: error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    """Verify proper error handling."""

    def test_missing_district_raises_valueerror(self, repo_with_districts):
        with pytest.raises(ValueError, match="not found"):
            export_district_geometry("nonexistent_district", repo=repo_with_districts)

    def test_district_without_geometry_raises_valueerror(self, repo_empty):
        district = District(
            id="no_geom",
            name="No Geometry",
            state="Assam",
            country="India",
            geometry_wkt=None,
        )
        repo_empty.upsert_district(district)
        with pytest.raises(ValueError, match="no geometry"):
            export_district_geometry("no_geom", repo=repo_empty)

    def test_empty_repo_raises_valueerror(self, repo_empty):
        with pytest.raises(ValueError, match="not found"):
            export_district_geometry("sivasagar", repo=repo_empty)


# ---------------------------------------------------------------------------
# Test: validation helpers
# ---------------------------------------------------------------------------

class TestValidationHelpers:
    """Test the validation helper functions."""

    def test_validate_valid_feature(self, repo_with_districts):
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        result = validate_district_feature(feature)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_all_features(self, repo_with_districts):
        fc = export_all_district_geometries(repo=repo_with_districts)
        features = fc["features"]
        result = validate_all_features(features)
        assert result["all_valid"] is True
        assert result["total"] == 4
        assert result["valid"] == 4
        assert result["invalid"] == 0

    def test_validate_detects_missing_district_id(self):
        feature = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            "properties": {"district_name": "Test"},
        }
        result = validate_district_feature(feature)
        assert result["valid"] is False
        assert any("district_id" in e for e in result["errors"])

    def test_validate_detects_wrong_geometry_type(self):
        feature = {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            "properties": {"district_id": "test", "district_name": "Test"},
        }
        result = validate_district_feature(feature)
        assert result["valid"] is False
        assert any("Polygon" in e for e in result["errors"])

    def test_validate_detects_empty_coordinates(self):
        feature = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": []},
            "properties": {"district_id": "test", "district_name": "Test"},
        }
        result = validate_district_feature(feature)
        assert result["valid"] is False

    def test_validate_detects_not_feature(self):
        feature = {
            "type": "GeometryCollection",
            "geometries": [],
        }
        result = validate_district_feature(feature)
        assert result["valid"] is False


# ---------------------------------------------------------------------------
# Test: wkt_to_geojson_geom helper
# ---------------------------------------------------------------------------

class TestWktToGeojsonGeom:
    """Test the internal WKT to GeoJSON conversion helper."""

    def test_polygon(self):
        wkt = "SRID=4326;POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        geom = _wkt_to_geojson_geom(wkt)
        assert geom is not None
        assert geom["type"] == "Polygon"

    def test_multipolygon(self):
        wkt = "SRID=4326;MULTIPOLYGON(((0 0, 1 0, 1 1, 0 1, 0 0)), ((2 2, 3 2, 3 3, 2 3, 2 2)))"
        geom = _wkt_to_geojson_geom(wkt)
        assert geom is not None
        assert geom["type"] == "MultiPolygon"

    def test_strips_srid(self):
        wkt = "SRID=4326;POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        geom = _wkt_to_geojson_geom(wkt)
        assert "crs" not in geom

    def test_empty_string(self):
        assert _wkt_to_geojson_geom("") is None

    def test_none(self):
        assert _wkt_to_geojson_geom(None) is None

    def test_invalid_wkt(self):
        assert _wkt_to_geojson_geom("NOT VALID WKT") is None


# ---------------------------------------------------------------------------
# Test: no district-specific code branches
# ---------------------------------------------------------------------------

class TestDistrictIndependence:
    """Verify the same code path handles all four districts identically."""

    def test_same_properties_keys_for_all(self, repo_with_districts):
        """All four districts should have identical property keys."""
        key_sets = []
        for did in TARGET_DISTRICTS:
            feature = export_district_geometry(did, repo=repo_with_districts)
            keys = set(feature["properties"].keys())
            key_sets.append(keys)

        # All should have the same keys
        assert all(ks == key_sets[0] for ks in key_sets), (
            "Different property key sets across districts — possible district-specific branching"
        )

    def test_same_geometry_type_for_all(self, repo_with_districts):
        """All four districts should have the same geometry type (Polygon)."""
        types = []
        for did in TARGET_DISTRICTS:
            feature = export_district_geometry(did, repo=repo_with_districts)
            types.append(feature["geometry"]["type"])

        assert all(t == "Polygon" for t in types), (
            f"Expected all Polygon, got {types}"
        )

    def test_all_exportable(self, repo_with_districts):
        """All four districts should export without error."""
        for did in TARGET_DISTRICTS:
            feature = export_district_geometry(did, repo=repo_with_districts)
            assert feature["type"] == "Feature"
            assert feature["properties"]["district_id"] == did


# ---------------------------------------------------------------------------
# Test: Sivasagar regression config (from Phase 5C.1)
# ---------------------------------------------------------------------------

class TestSivasagarRegressionCompatibility:
    """Verify exported Sivasagar geometry is compatible with the flood pipeline config."""

    def test_sivasagar_bbox_in_pipeline_range(self, repo_with_districts):
        """Sivasagar exported geometry should be near the original AOI rectangle."""
        feature = export_district_geometry("sivasagar", repo=repo_with_districts)
        ring = feature["geometry"]["coordinates"][0]
        lons = [p[0] for p in ring]
        lats = [p[1] for p in ring]

        # Original AOI was [94.55, 26.85, 95.05, 27.15]
        # Our test polygon is [94.60, 26.90, 94.70, 27.00] — within that range
        assert min(lons) >= 94.5
        assert max(lons) <= 95.1
        assert min(lats) >= 26.8
        assert max(lats) <= 27.2


# ---------------------------------------------------------------------------
# Test: TARGET_DISTRICTS constant
# ---------------------------------------------------------------------------

class TestTargetDistrictsConstant:
    """Verify the TARGET_DISTRICTS list is correct."""

    def test_has_four_districts(self):
        assert len(TARGET_DISTRICTS) == 4

    def test_contains_all_targets(self):
        assert "sivasagar" in TARGET_DISTRICTS
        assert "jorhat" in TARGET_DISTRICTS
        assert "charaideo" in TARGET_DISTRICTS
        assert "golaghat" in TARGET_DISTRICTS
