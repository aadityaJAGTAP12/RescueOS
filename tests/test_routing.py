"""Tests for the OSRM routing tool."""

import pytest
from unittest.mock import patch, MagicMock
from agent.tools.routing_tool import (
    get_route,
    check_osrm_health,
    check_route_flood_intersection,
    _fallback_to_haversine,
    get_multiple_routes,
    get_route_for_allocation,
)


class TestOSRMHealth:
    """Test OSRM health check."""

    @patch("agent.tools.routing_tool.requests.get")
    def test_osrm_healthy(self, mock_get):
        """Test successful health check."""
        mock_get.return_value = MagicMock(status_code=200)
        assert check_osrm_health() is True
        mock_get.assert_called_once_with("http://localhost:5001/health", timeout=5)

    @patch("agent.tools.routing_tool.requests.get")
    def test_osrm_unhealthy(self, mock_get):
        """Test failed health check."""
        mock_get.return_value = MagicMock(status_code=500)
        assert check_osrm_health() is False

    @patch("agent.tools.routing_tool.requests.get")
    def test_osrm_connection_error(self, mock_get):
        """Test connection error."""
        from requests import ConnectionError
        mock_get.side_effect = ConnectionError("Connection refused")
        assert check_osrm_health() is False


class TestHaversineFallback:
    """Test haversine fallback when OSRM is unavailable."""

    def test_fallback_returns_unavailable_status(self):
        """Test that fallback explicitly marks status as unavailable."""
        result = _fallback_to_haversine(
            start_lat=26.98,
            start_lon=94.66,
            end_lat=27.0,
            end_lon=94.7,
            reason="Test reason"
        )
        assert result["status"] == "unavailable"
        assert "Test reason" in result["source"]

    def test_fallback_distance_matches_haversine(self):
        """Test that fallback distance matches haversine_km calculation."""
        from agent.data_loader import haversine_km
        
        start_lat, start_lon = 26.98, 94.66
        end_lat, end_lon = 27.0, 94.7
        
        expected_distance = haversine_km(start_lon, start_lat, end_lon, end_lat)
        result = _fallback_to_haversine(start_lat, start_lon, end_lat, end_lon, "test")
        
        assert result["distance_km"] == round(expected_distance, 2)

    def test_fallback_geometry_is_straight_line(self):
        """Test that fallback geometry is just two points (straight line)."""
        result = _fallback_to_haversine(26.98, 94.66, 27.0, 94.7, "test")
        assert len(result["geometry"]) == 2
        assert result["geometry"][0] == [94.66, 26.98]
        assert result["geometry"][1] == [94.7, 27.0]


class TestGetRoute:
    """Test get_route function with mocked OSRM."""

    @patch("agent.tools.routing_tool.check_osrm_health")
    def test_osrm_unavailable_falls_back(self, mock_health):
        """Test fallback when OSRM is unavailable."""
        mock_health.return_value = False
        
        result = get_route(
            start_lat=26.98,
            start_lon=94.66,
            end_lat=27.0,
            end_lon=94.7
        )
        
        assert result["status"] == "unavailable"
        assert "routing unavailable" in result["distance_method"]

    @patch("agent.tools.routing_tool.requests.get")
    @patch("agent.tools.routing_tool.check_osrm_health")
    def test_osrm_success(self, mock_health, mock_get):
        """Test successful OSRM route."""
        mock_health.return_value = True
        
        # Mock OSRM response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": "Ok",
            "routes": [{
                "distance": 15000,  # 15 km
                "duration": 1800,   # 30 minutes
                "geometry": {
                    "coordinates": [
                        [94.66, 26.98],
                        [94.67, 26.99],
                        [94.68, 27.0],
                        [94.7, 27.0]
                    ]
                }
            }]
        }
        mock_get.return_value = mock_response
        
        result = get_route(
            start_lat=26.98,
            start_lon=94.66,
            end_lat=27.0,
            end_lon=94.7
        )
        
        assert result["status"] == "success"
        assert result["distance_km"] == 15.0
        assert result["duration_minutes"] == 30.0
        assert len(result["geometry"]) == 4
        assert result["distance_method"] == "OSRM road routing"

    @patch("agent.tools.routing_tool.requests.get")
    @patch("agent.tools.routing_tool.check_osrm_health")
    def test_osrm_no_route_found(self, mock_health, mock_get):
        """Test OSRM returns no route."""
        mock_health.return_value = True
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": "NoRoute",
            "routes": []
        }
        mock_get.return_value = mock_response
        
        result = get_route(
            start_lat=26.98,
            start_lon=94.66,
            end_lat=27.0,
            end_lon=94.7
        )
        
        assert result["status"] == "unavailable"
        assert "No route found" in result["source"]

    @patch("agent.tools.routing_tool.requests.get")
    @patch("agent.tools.routing_tool.check_osrm_health")
    def test_osrm_request_timeout(self, mock_health, mock_get):
        """Test OSRM request timeout."""
        mock_health.return_value = True
        
        from requests import RequestException
        mock_get.side_effect = RequestException("Connection timed out")
        
        result = get_route(
            start_lat=26.98,
            start_lon=94.66,
            end_lat=27.0,
            end_lon=94.7
        )
        
        assert result["status"] == "unavailable"
        assert "timed out" in result["source"]

    @patch("agent.tools.routing_tool.requests.get")
    @patch("agent.tools.routing_tool.check_osrm_health")
    def test_osrm_request_uses_overview_full(self, mock_health, mock_get):
        """Verify get_route() sends overview=full and geometries=geojson to OSRM.

        Regression test: ensuring full route geometry is returned so that
        flood-intersection detection receives unsimplified coordinates.
        """
        mock_health.return_value = True

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": "Ok",
            "routes": [{
                "distance": 15000,
                "duration": 1800,
                "geometry": {
                    "coordinates": [
                        [94.66, 26.98],
                        [94.68, 27.0],
                        [94.7, 27.0]
                    ]
                }
            }]
        }
        mock_get.return_value = mock_response

        get_route(
            start_lat=26.98,
            start_lon=94.66,
            end_lat=27.0,
            end_lon=94.7
        )

        # Confirm requests.get was called (the route request, not just health)
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args

        # Assert exact OSRM geometry parameters
        assert call_kwargs.kwargs["params"]["overview"] == "full"
        assert call_kwargs.kwargs["params"]["geometries"] == "geojson"


class TestMultipleRoutes:
    """Test get_multiple_routes function."""

    @patch("agent.tools.routing_tool.get_route")
    def test_multiple_routes(self, mock_route):
        """Test routing to multiple destinations."""
        # Use side_effect to return a new dict for each call
        def route_side_effect(**kwargs):
            return {
                "status": "success",
                "distance_km": 10.0,
                "duration_minutes": 15.0,
                "geometry": [[94.66, 26.98], [94.7, 27.0]],
                "distance_method": "OSRM road routing"
            }
        mock_route.side_effect = route_side_effect
        
        destinations = [
            {"lat": 27.0, "lon": 94.7, "id": "loc1"},
            {"lat": 27.1, "lon": 94.8, "id": "loc2"},
        ]
        
        results = get_multiple_routes(
            origin_lat=26.98,
            origin_lon=94.66,
            destinations=destinations
        )
        
        assert len(results) == 2
        # get_multiple_routes adds destination_id to each route result
        assert results[0]["destination_id"] == "loc1"
        assert results[1]["destination_id"] == "loc2"
        assert mock_route.call_count == 2
        
        # Verify first call was for loc1
        first_call = mock_route.call_args_list[0]
        assert first_call.kwargs["end_lat"] == 27.0
        assert first_call.kwargs["end_lon"] == 94.7
        
        # Verify second call was for loc2
        second_call = mock_route.call_args_list[1]
        assert second_call.kwargs["end_lat"] == 27.1
        assert second_call.kwargs["end_lon"] == 94.8


class TestRouteForAllocation:
    """Test get_route_for_allocation function."""

    @patch("agent.tools.routing_tool.get_route")
    def test_allocation_route_metadata(self, mock_route):
        """Test that allocation route includes metadata."""
        mock_route.return_value = {
            "status": "success",
            "distance_km": 10.0,
            "duration_minutes": 15.0,
            "geometry": [[94.66, 26.98], [94.7, 27.0]],
            "distance_method": "OSRM road routing"
        }
        
        result = get_route_for_allocation(
            origin_lat=26.98,
            origin_lon=94.66,
            destination_lat=27.0,
            destination_lon=94.7,
            destination_name="Test Location"
        )
        
        assert result["destination_name"] == "Test Location"
        assert result["origin"] == {"lat": 26.98, "lon": 94.66}
        assert result["destination"] == {"lat": 27.0, "lon": 94.7}


class TestCheckRouteFloodIntersection:
    """Test flood-crossing detection for routes (Phase 2)."""

    def test_route_crossing_known_flood_polygon(self):
        """Route that passes through the largest flood polygon (index 868).
        
        Polygon 868 bounds: lon 94.6559-94.7264, lat 26.9882-27.0337
        A route from (94.66, 26.99) to (94.72, 27.01) crosses right through it.
        """
        # Route geometry: [lon, lat] pairs crossing the polygon
        geometry = [
            [94.66, 26.99],   # just inside polygon bounds
            [94.67, 27.00],   # through the polygon
            [94.68, 27.005],  # through the polygon
            [94.70, 27.02],   # through the polygon
            [94.72, 27.01],   # near polygon edge
        ]
        result = check_route_flood_intersection(geometry)
        
        assert result["crosses_flood_zone"] is True
        assert len(result["intersecting_polygons"]) > 0
        assert result["warning"] is not None
        assert "flood-affected" in result["warning"]
        
        # Verify polygon data is real
        for poly_info in result["intersecting_polygons"]:
            assert poly_info["polygon_area_km2"] > 0
            assert len(poly_info["approximate_location"]) == 2
            # Location should be [lat, lon] — lat in Assam range
            lat, lon = poly_info["approximate_location"]
            assert 26.0 < lat < 28.0
            assert 94.0 < lon < 95.5

    def test_route_avoiding_flood_polygon(self):
        """Route that stays far from any flood polygon — no false positive.
        
        Flood data extent: lon 94.55-95.05, lat 26.85-27.15.
        Use coordinates well outside this range.
        """
        geometry = [
            [95.10, 26.50],   # well outside all flood polygons
            [95.15, 26.55],
            [95.20, 26.60],
        ]
        result = check_route_flood_intersection(geometry)
        
        assert result["crosses_flood_zone"] is False
        assert len(result["intersecting_polygons"]) == 0
        assert result["warning"] is None

    def test_empty_geometry(self):
        """Empty geometry should return no crossing."""
        result = check_route_flood_intersection([])
        assert result["crosses_flood_zone"] is False
        assert result["intersecting_polygons"] == []
        assert result["warning"] is None

    def test_single_point_geometry(self):
        """Single-point geometry (not a line) should return no crossing."""
        result = check_route_flood_intersection([[94.66, 27.00]])
        assert result["crosses_flood_zone"] is False

    def test_identical_points_geometry(self):
        """Degenerate geometry with identical points should not crash."""
        result = check_route_flood_intersection([[94.66, 27.00], [94.66, 27.00]])
        assert result["crosses_flood_zone"] is False

    def test_haversine_fallback_includes_flood_fields(self):
        """Haversine fallback response includes flood detection fields."""
        # Route through the known flood polygon
        result = _fallback_to_haversine(
            start_lat=26.99, start_lon=94.66,
            end_lat=27.01, end_lon=94.72,
            reason="test"
        )
        assert "crosses_flood_zone" in result
        assert "intersecting_polygons" in result
        assert "flood_warning" in result
        # This straight line DOES cross a flood polygon
        assert result["crosses_flood_zone"] is True

    def test_haversine_fallback_safe_route_no_flood(self):
        """Haversine fallback for a safe route shows no flood crossing."""
        result = _fallback_to_haversine(
            start_lat=26.50, start_lon=95.10,
            end_lat=26.55, end_lon=95.15,
            reason="test"
        )
        assert result["crosses_flood_zone"] is False
        assert result["intersecting_polygons"] == []
        assert result["flood_warning"] is None

    @patch("agent.tools.routing_tool.check_osrm_health")
    def test_osrm_route_includes_flood_fields(self, mock_health):
        """OSRM success response includes flood detection fields."""
        mock_health.return_value = True
        
        with patch("agent.tools.routing_tool.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "code": "Ok",
                "routes": [{
                    "distance": 15000,
                    "duration": 1800,
                    "geometry": {
                        "coordinates": [
                            [94.66, 26.99],
                            [94.67, 27.00],
                            [94.68, 27.005],
                            [94.70, 27.02],
                            [94.72, 27.01],
                        ]
                    }
                }]
            }
            mock_get.return_value = mock_response
            
            result = get_route(
                start_lat=26.99, start_lon=94.66,
                end_lat=27.01, end_lon=94.72
            )
            
            assert "crosses_flood_zone" in result
            assert "intersecting_polygons" in result
            assert "flood_warning" in result
            assert result["crosses_flood_zone"] is True
            assert result["flood_warning"] is not None
            assert "WARNING" in result["message"]
