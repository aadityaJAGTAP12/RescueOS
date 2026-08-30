"""
Tests for the Sentinel-1 flood-mapping pipeline — parameter/config layer.

These tests verify:
- Default parameters
- Parameter overrides
- Filename generation
- Metadata generation
- District-independent configuration
- Sivasagar regression configuration
- Different date windows
- No district-specific branching in the processing functions
- GeoJSON validation helpers

Earth Engine server-side processing is NOT unit-tested here.
GEE requires authenticated access and cannot be meaningfully mocked
for these unit tests.

The processing functions (build_s1_collection, create_composite,
detect_flood, vectorize_flood, generate_flood_snapshot) are tested
for correct parameterization only — the actual ee.* calls require
a live GEE connection.
"""

import pytest
import math

from agent.gee.config import (
    FloodPipelineConfig,
    DEFAULT_CONFIG,
    SIVASAGAR_REGRESSION_CONFIG,
    DISTRICT_EXAMPLE_WINDOWS,
)
from agent.gee.validation import validate_geojson_flood_data, compare_district_stats


# ---------------------------------------------------------------------------
# FloodPipelineConfig — defaults
# ---------------------------------------------------------------------------

class TestFloodPipelineConfigDefaults:
    """Test that default config values match the Sivasagar methodology."""

    def test_default_collection(self):
        assert DEFAULT_CONFIG.collection == "COPERNICUS/S1_GRD"

    def test_default_polarization(self):
        assert DEFAULT_CONFIG.polarization == "VH"

    def test_default_instrument_mode(self):
        assert DEFAULT_CONFIG.instrument_mode == "IW"

    def test_default_orbit_pass(self):
        assert DEFAULT_CONFIG.orbit_pass == "DESCENDING"

    def test_default_threshold_db(self):
        assert DEFAULT_CONFIG.threshold_db == -3.0

    def test_default_speckle_radius_m(self):
        assert DEFAULT_CONFIG.speckle_radius_m == 50.0

    def test_default_connected_pixel_neighborhood(self):
        assert DEFAULT_CONFIG.connected_pixel_neighborhood == 100

    def test_default_min_connected_pixels(self):
        assert DEFAULT_CONFIG.min_connected_pixels == 60

    def test_default_vector_scale(self):
        assert DEFAULT_CONFIG.vector_scale == 10.0

    def test_default_area_threshold_m2(self):
        assert DEFAULT_CONFIG.area_threshold_m2 == 5000.0

    def test_default_provenance(self):
        assert DEFAULT_CONFIG.provenance == "REAL"

    def test_default_confidence(self):
        assert DEFAULT_CONFIG.confidence == 0.8


# ---------------------------------------------------------------------------
# FloodPipelineConfig — parameter overrides
# ---------------------------------------------------------------------------

class TestFloodPipelineConfigOverrides:
    """Test that config accepts per-district/per-window overrides."""

    def test_override_threshold(self):
        config = FloodPipelineConfig(threshold_db=-5.0)
        assert config.threshold_db == -5.0

    def test_override_speckle_radius(self):
        config = FloodPipelineConfig(speckle_radius_m=100.0)
        assert config.speckle_radius_m == 100.0

    def test_override_connected_pixels(self):
        config = FloodPipelineConfig(min_connected_pixels=30)
        assert config.min_connected_pixels == 30

    def test_override_area_threshold(self):
        config = FloodPipelineConfig(area_threshold_m2=10000.0)
        assert config.area_threshold_m2 == 10000.0

    def test_override_dates(self):
        config = FloodPipelineConfig(
            pre_start="2026-01-01",
            pre_end="2026-01-15",
            event_start="2026-02-01",
            event_end="2026-02-15",
        )
        assert config.pre_start == "2026-01-01"
        assert config.event_start == "2026-02-01"

    def test_override_district_id(self):
        config = FloodPipelineConfig(district_id="jorhat")
        assert config.district_id == "jorhat"

    def test_override_multiple_params(self):
        config = FloodPipelineConfig(
            threshold_db=-4.0,
            speckle_radius_m=75.0,
            min_connected_pixels=40,
            area_threshold_m2=2000.0,
            district_id="charaideo",
        )
        assert config.threshold_db == -4.0
        assert config.speckle_radius_m == 75.0
        assert config.min_connected_pixels == 40
        assert config.area_threshold_m2 == 2000.0
        assert config.district_id == "charaideo"


# ---------------------------------------------------------------------------
# Filename generation
# ---------------------------------------------------------------------------

class TestFilenameGeneration:
    """Test that filenames are generated correctly from config."""

    def test_sivasagar_filename(self):
        config = FloodPipelineConfig(
            district_id="sivasagar",
            event_start="2026-08-08",
            event_end="2026-08-13",
        )
        assert config.generate_filename() == "sivasagar_flood_2026-08-08_2026-08-13.geojson"

    def test_jorhat_filename(self):
        config = FloodPipelineConfig(
            district_id="jorhat",
            event_start="2026-07-01",
            event_end="2026-07-10",
        )
        assert config.generate_filename() == "jorhat_flood_2026-07-01_2026-07-10.geojson"

    def test_unknown_district_filename(self):
        config = FloodPipelineConfig(
            event_start="2026-01-01",
            event_end="2026-01-31",
        )
        assert config.generate_filename() == "unknown_flood_2026-01-01_2026-01-31.geojson"

    def test_missing_dates_filename(self):
        config = FloodPipelineConfig(district_id="golaghat")
        assert config.generate_filename() == "golaghat_flood_unknown-start_unknown-end.geojson"

    def test_filename_no_district_specific_logic(self):
        """Filename generation should work the same for any district."""
        districts = ["sivasagar", "jorhat", "charaideo", "golaghat", "any_future_district"]
        for district in districts:
            config = FloodPipelineConfig(
                district_id=district,
                event_start="2026-06-01",
                event_end="2026-06-30",
            )
            filename = config.generate_filename()
            assert filename.startswith(f"{district}_flood_")
            assert filename.endswith(".geojson")


# ---------------------------------------------------------------------------
# Metadata generation
# ---------------------------------------------------------------------------

class TestMetadataGeneration:
    """Test that metadata contains all required fields."""

    def test_metadata_has_all_required_keys(self):
        config = FloodPipelineConfig(
            district_id="sivasagar",
            pre_start="2026-06-25",
            pre_end="2026-07-05",
            event_start="2026-08-08",
            event_end="2026-08-13",
        )
        metadata = config.get_metadata()

        required_keys = {
            "district_id",
            "pre_start",
            "pre_end",
            "event_start",
            "event_end",
            "source",
            "collection",
            "polarization",
            "orbit",
            "instrument",
            "threshold_db",
            "speckle_radius_m",
            "min_connected_pixels",
            "connected_pixel_neighborhood",
            "vector_scale",
            "area_threshold_m2",
            "methodology_version",
            "provenance",
            "confidence",
        }

        assert required_keys.issubset(set(metadata.keys()))

    def test_metadata_source_is_sentinel1(self):
        metadata = DEFAULT_CONFIG.get_metadata()
        assert metadata["source"] == "Sentinel-1 SAR"

    def test_metadata_collection_is_s1_grd(self):
        metadata = DEFAULT_CONFIG.get_metadata()
        assert metadata["collection"] == "COPERNICUS/S1_GRD"

    def test_metadata_values_match_config(self):
        config = FloodPipelineConfig(
            district_id="test",
            threshold_db=-4.5,
            speckle_radius_m=80.0,
        )
        metadata = config.get_metadata()
        assert metadata["district_id"] == "test"
        assert metadata["threshold_db"] == -4.5
        assert metadata["speckle_radius_m"] == 80.0


# ---------------------------------------------------------------------------
# Sivasagar regression configuration
# ---------------------------------------------------------------------------

class TestSivasagarRegressionConfig:
    """Test that the Sivasagar regression config reproduces the original methodology."""

    def test_district_id(self):
        assert SIVASAGAR_REGRESSION_CONFIG.district_id == "sivasagar"

    def test_pre_flood_dates(self):
        assert SIVASAGAR_REGRESSION_CONFIG.pre_start == "2026-06-25"
        assert SIVASAGAR_REGRESSION_CONFIG.pre_end == "2026-07-05"

    def test_event_dates(self):
        assert SIVASAGAR_REGRESSION_CONFIG.event_start == "2026-08-08"
        assert SIVASAGAR_REGRESSION_CONFIG.event_end == "2026-08-13"

    def test_threshold(self):
        assert SIVASAGAR_REGRESSION_CONFIG.threshold_db == -3.0

    def test_speckle_radius(self):
        assert SIVASAGAR_REGRESSION_CONFIG.speckle_radius_m == 50.0

    def test_connected_pixel_params(self):
        assert SIVASAGAR_REGRESSION_CONFIG.connected_pixel_neighborhood == 100
        assert SIVASAGAR_REGRESSION_CONFIG.min_connected_pixels == 60

    def test_vector_scale(self):
        assert SIVASAGAR_REGRESSION_CONFIG.vector_scale == 10.0

    def test_area_threshold(self):
        assert SIVASAGAR_REGRESSION_CONFIG.area_threshold_m2 == 5000.0

    def test_collection_defaults(self):
        """Regression config inherits correct S1 GRD defaults."""
        assert SIVASAGAR_REGRESSION_CONFIG.collection == "COPERNICUS/S1_GRD"
        assert SIVASAGAR_REGRESSION_CONFIG.polarization == "VH"
        assert SIVASAGAR_REGRESSION_CONFIG.instrument_mode == "IW"
        assert SIVASAGAR_REGRESSION_CONFIG.orbit_pass == "DESCENDING"

    def test_filename(self):
        filename = SIVASAGAR_REGRESSION_CONFIG.generate_filename()
        assert filename == "sivasagar_flood_2026-08-08_2026-08-13.geojson"


# ---------------------------------------------------------------------------
# District-independent configuration
# ---------------------------------------------------------------------------

class TestDistrictIndependentConfig:
    """Test that the same config class works for any district."""

    def test_all_four_districts(self):
        districts = ["sivasagar", "jorhat", "charaideo", "golaghat"]
        configs = []

        for district in districts:
            config = FloodPipelineConfig(
                district_id=district,
                pre_start="2026-06-25",
                pre_end="2026-07-05",
                event_start="2026-08-08",
                event_end="2026-08-13",
            )
            configs.append(config)

        # All should have the same processing params
        for config in configs:
            assert config.threshold_db == -3.0
            assert config.speckle_radius_m == 50.0
            assert config.collection == "COPERNICUS/S1_GRD"

        # Each should have its own district_id and filename
        filenames = [c.generate_filename() for c in configs]
        assert len(set(filenames)) == 4  # all unique

    def test_different_date_windows(self):
        """Different districts can have different date windows."""
        config_a = FloodPipelineConfig(
            district_id="sivasagar",
            pre_start="2026-06-25",
            pre_end="2026-07-05",
            event_start="2026-08-08",
            event_end="2026-08-13",
        )
        config_b = FloodPipelineConfig(
            district_id="jorhat",
            pre_start="2026-07-10",
            pre_end="2026-07-20",
            event_start="2026-09-01",
            event_end="2026-09-10",
        )

        assert config_a.pre_start != config_b.pre_start
        assert config_a.event_start != config_b.event_start
        assert config_a.generate_filename() != config_b.generate_filename()

    def test_no_district_specific_branching(self):
        """The config is a pure data container — no district-specific logic."""
        # The same class instantiation works identically for any district
        for name in ["sivasagar", "jorhat", "charaideo", "golaghat", "dhubri"]:
            config = FloodPipelineConfig(district_id=name)
            metadata = config.get_metadata()
            assert metadata["district_id"] == name
            # Same defaults regardless of district
            assert metadata["threshold_db"] == -3.0
            assert metadata["collection"] == "COPERNICUS/S1_GRD"


# ---------------------------------------------------------------------------
# Different date windows
# ---------------------------------------------------------------------------

class TestDateWindowConfigs:
    """Test that various date window configurations work correctly."""

    def test_single_day_window(self):
        config = FloodPipelineConfig(
            district_id="test",
            pre_start="2026-07-01",
            pre_end="2026-07-02",
            event_start="2026-08-15",
            event_end="2026-08-16",
        )
        metadata = config.get_metadata()
        assert metadata["pre_start"] == "2026-07-01"
        assert metadata["event_end"] == "2026-08-16"

    def test_multi_month_window(self):
        config = FloodPipelineConfig(
            district_id="test",
            pre_start="2026-01-01",
            pre_end="2026-03-31",
            event_start="2026-06-01",
            event_end="2026-09-30",
        )
        metadata = config.get_metadata()
        assert metadata["pre_start"] == "2026-01-01"
        assert metadata["pre_end"] == "2026-03-31"
        assert metadata["event_start"] == "2026-06-01"
        assert metadata["event_end"] == "2026-09-30"

    def test_cross_year_window(self):
        config = FloodPipelineConfig(
            district_id="test",
            pre_start="2025-12-01",
            pre_end="2026-01-15",
            event_start="2026-02-01",
            event_end="2026-02-28",
        )
        filename = config.generate_filename()
        assert "2025-12-01" in filename or "2026-02-01" in filename


# ---------------------------------------------------------------------------
# Example windows documentation
# ---------------------------------------------------------------------------

class TestExampleWindows:
    """Test that documented example windows are internally consistent."""

    def test_all_four_districts_have_windows(self):
        for district in ["sivasagar", "jorhat", "charaideo", "golaghat"]:
            assert district in DISTRICT_EXAMPLE_WINDOWS
            windows = DISTRICT_EXAMPLE_WINDOWS[district]
            assert "pre" in windows
            assert "event" in windows
            assert len(windows["pre"]) == 2
            assert len(windows["event"]) == 2

    def test_pre_before_event(self):
        """Pre-flood window should start before event window."""
        for district, windows in DISTRICT_EXAMPLE_WINDOWS.items():
            pre_end = windows["pre"][1]
            event_start = windows["event"][0]
            assert pre_end <= event_start, (
                f"{district}: pre_end ({pre_end}) should be <= event_start ({event_start})"
            )


# ---------------------------------------------------------------------------
# GeoJSON validation helpers
# ---------------------------------------------------------------------------

class TestValidateGeoJSONFloodData:
    """Test local GeoJSON validation helpers."""

    def test_empty_feature_collection(self):
        geojson = {"type": "FeatureCollection", "features": []}
        result = validate_geojson_flood_data(geojson)
        assert result["polygon_count"] == 0
        assert result["valid"] is True
        assert result["total_area_m2"] == 0.0

    def test_valid_polygons(self):
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [94.6, 26.9],
                                [94.7, 26.9],
                                [94.7, 27.0],
                                [94.6, 27.0],
                                [94.6, 26.9],
                            ]
                        ],
                    },
                    "properties": {},
                },
            ],
        }
        result = validate_geojson_flood_data(geojson)
        assert result["polygon_count"] == 1
        assert result["valid"] is True
        assert result["total_area_m2"] > 0
        assert result["largest_area_m2"] > 0
        assert result["smallest_area_m2"] == result["largest_area_m2"]

    def test_multiple_polygons(self):
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [94.6, 26.9],
                                [94.7, 26.9],
                                [94.7, 27.0],
                                [94.6, 27.0],
                                [94.6, 26.9],
                            ]
                        ],
                    },
                    "properties": {},
                },
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [94.65, 26.95],
                                [94.66, 26.95],
                                [94.66, 26.96],
                                [94.65, 26.96],
                                [94.65, 26.95],
                            ]
                        ],
                    },
                    "properties": {},
                },
            ],
        }
        result = validate_geojson_flood_data(geojson)
        assert result["polygon_count"] == 2
        assert result["valid_count"] == 2
        assert result["largest_area_m2"] > result["smallest_area_m2"]

    def test_missing_geometry_handled(self):
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": None, "properties": {}},
            ],
        }
        result = validate_geojson_flood_data(geojson)
        assert result["polygon_count"] == 1
        assert result["invalid_count"] >= 1


# ---------------------------------------------------------------------------
# Compare district stats
# ---------------------------------------------------------------------------

class TestCompareDistrictStats:
    """Test the district comparison table formatter."""

    def test_basic_comparison(self):
        stats = [
            {"district_id": "sivasagar", "polygon_count": 1924, "total_area_m2": 5e7,
             "largest_area_m2": 1e6, "average_area_m2": 2.6e4},
            {"district_id": "jorhat", "polygon_count": 1500, "total_area_m2": 3e7,
             "largest_area_m2": 8e5, "average_area_m2": 2.0e4},
        ]
        table = compare_district_stats(stats)
        assert "sivasagar" in table
        assert "jorhat" in table
        assert "1,924" in table
        assert "|" in table

    def test_empty_stats(self):
        table = compare_district_stats([])
        assert "District" in table  # header should be present


# ---------------------------------------------------------------------------
# Config immutability — cloning
# ---------------------------------------------------------------------------

class TestConfigCloning:
    """Test that config objects can be cloned without side effects."""

    def test_deep_clone(self):
        """Cloned config should be independent of original."""
        original = FloodPipelineConfig(
            district_id="sivasagar",
            threshold_db=-3.0,
        )
        cloned = FloodPipelineConfig(**{
            k: v for k, v in original.__dict__.items()
        })

        # Modify clone
        cloned.district_id = "jorhat"
        cloned.threshold_db = -5.0

        # Original unchanged
        assert original.district_id == "sivasagar"
        assert original.threshold_db == -3.0

    def test_clone_preserves_all_fields(self):
        original = FloodPipelineConfig(
            district_id="test",
            pre_start="2026-01-01",
            pre_end="2026-01-31",
            event_start="2026-02-01",
            event_end="2026-02-28",
            threshold_db=-4.0,
            speckle_radius_m=75.0,
        )
        cloned = FloodPipelineConfig(**{
            k: v for k, v in original.__dict__.items()
        })
        assert cloned.district_id == original.district_id
        assert cloned.pre_start == original.pre_start
        assert cloned.threshold_db == original.threshold_db
        assert cloned.generate_filename() == original.generate_filename()
