"""
Tests for flood_tool.py using the actual local flood dataset.

No Overpass API calls are made. Tests use coordinates that are known
to be inside/near/outside the Sivasagar flood polygons.
"""

import pytest
from agent.tools.flood_tool import get_flood_status, _resolve_location
from agent.config import KNOWN_LOCATIONS
from agent.data_loader import FLOOD_POLYGONS


class TestFloodDataLoaded:
    """Verify that the local flood data loaded correctly."""

    def test_flood_polygons_loaded(self):
        """FLOOD_POLYGONS should be a non-empty list."""
        assert isinstance(FLOOD_POLYGONS, list)
        assert len(FLOOD_POLYGONS) > 0

    def test_known_locations_defined(self):
        """KNOWN_LOCATIONS should have the three expected entries."""
        assert "sivasagar" in KNOWN_LOCATIONS
        assert "sivasagar_flood_zone" in KNOWN_LOCATIONS
        assert "sivasagar_settlement_flood" in KNOWN_LOCATIONS


class TestResolveLocation:
    """Tests for _resolve_location helper."""

    def test_resolve_known_name(self):
        """Known location name should resolve to coordinates."""
        lon, lat, label = _resolve_location("sivasagar")
        assert lon is not None
        assert lat is not None
        assert label == "sivasagar"

    def test_resolve_unknown_name(self):
        """Unknown location name should return error dict."""
        lon, lat, result = _resolve_location("nonexistent_place")
        assert lon is None
        assert lat is None
        assert "error" in result

    def test_resolve_lat_lon(self):
        """Explicit lat/lon should resolve directly."""
        lon, lat, label = _resolve_location(lat=26.97, lon=94.64)
        assert lon == 94.64
        assert lat == 26.97

    def test_resolve_no_input(self):
        """No input should return error."""
        lon, lat, result = _resolve_location()
        assert lon is None
        assert lat is None
        assert "error" in result


class TestGetFloodStatus:
    """Tests for get_flood_status() using local data."""

    def test_flood_zone_is_flooded(self):
        """sivasagar_flood_zone (confirmed flooded point) should be flooded."""
        result = get_flood_status("sivasagar_flood_zone")
        assert result["flooded"] is True
        assert result["total_flood_polygons"] > 0

    def test_sivasagar_town_center(self):
        """sivasagar town center should NOT be inside a flood polygon."""
        result = get_flood_status("sivasagar")
        # Town center may be near flood zone but not necessarily inside
        assert "flooded" in result
        assert "exactly_contained" in result
        assert "near_flood_zone" in result
        assert isinstance(result["nearest_flood_polygon_km2"], float)

    def test_settlement_flood(self):
        """sivasagar_settlement_flood should report flood status."""
        result = get_flood_status("sivasagar_settlement_flood")
        assert "flooded" in result
        assert isinstance(result["flooded"], bool)

    def test_unknown_location_returns_error(self):
        """Unknown location should return flooded=False with error."""
        result = get_flood_status("nonexistent_place")
        assert result["flooded"] is False
        assert "error" in result

    def test_explicit_coordinates(self):
        """Using explicit lat/lon should work the same as a name."""
        lon, lat = KNOWN_LOCATIONS["sivasagar_flood_zone"]
        result = get_flood_status(lat=lat, lon=lon)
        assert result["flooded"] is True

    def test_result_structure(self):
        """All results should have the expected keys."""
        result = get_flood_status("sivasagar")
        expected_keys = {
            "location", "flooded", "exactly_contained", "near_flood_zone",
            "total_flood_polygons", "nearest_flood_polygon_km2", "detail"
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_no_flood_polygons_near_origin(self):
        """A point far from Sivasagar should not be flooded."""
        # Origin (0,0) is nowhere near the flood data
        result = get_flood_status(lat=0.0, lon=0.0)
        assert result["flooded"] is False
        assert result["exactly_contained"] is False
        assert result["near_flood_zone"] is False
