"""
Shared fixtures for ReliefOS tests.

Provides mock data for flood status, building exposure, and medical
accessibility so tests can run without Overpass or Ollama.
"""

import pytest


@pytest.fixture
def mock_flood_status_flooded():
    """Flood status for a flooded location."""
    return {
        "location": "test_flood_zone",
        "flooded": True,
        "exactly_contained": True,
        "near_flood_zone": False,
        "total_flood_polygons": 45,
        "nearest_flood_polygon_km2": 4.88,
        "detail": "EXACTLY CONTAINED: Point is inside a flood polygon (45 flood-affected areas in district)"
    }


@pytest.fixture
def mock_flood_status_near():
    """Flood status for a location near but not inside a flood zone."""
    return {
        "location": "test_near_flood",
        "flooded": True,
        "exactly_contained": False,
        "near_flood_zone": True,
        "total_flood_polygons": 45,
        "nearest_flood_polygon_km2": 4.88,
        "detail": "NEAR FLOOD ZONE: Point is within ~1.1km of a flood polygon"
    }


@pytest.fixture
def mock_flood_status_safe():
    """Flood status for a safe (non-flooded) location."""
    return {
        "location": "test_safe",
        "flooded": False,
        "exactly_contained": False,
        "near_flood_zone": False,
        "total_flood_polygons": 45,
        "nearest_flood_polygon_km2": 0.0,
        "detail": "NOT FLOOD-AFFECTED"
    }


@pytest.fixture
def mock_exposure_high():
    """High building exposure."""
    return {
        "location": "test_high_exposure",
        "total_buildings": 100,
        "exposed_count": 60,
        "exposure_ratio": 0.6,
        "detail": "Building exposure: 100 buildings, 60 exposed (60%)",
        "data_available": True
    }


@pytest.fixture
def mock_exposure_low():
    """Low building exposure."""
    return {
        "location": "test_low_exposure",
        "total_buildings": 50,
        "exposed_count": 3,
        "exposure_ratio": 0.06,
        "detail": "Building exposure: 50 buildings, 3 exposed (6%)",
        "data_available": True
    }


@pytest.fixture
def mock_exposure_none():
    """No exposure data available."""
    return {
        "location": "test_no_data",
        "total_buildings": 0,
        "exposed_count": 0,
        "exposure_ratio": 0.0,
        "detail": "Building exposure: API ERROR. Treat as unknown.",
        "data_available": False
    }


@pytest.fixture
def mock_accessibility_near():
    """Nearby medical facility."""
    return {
        "location": "test_near_medical",
        "medical_distance_km": 2.5,
        "medical_facility_name": "Test Hospital",
        "detail": "Accessibility: Test Hospital at 2.5km",
        "data_available": True
    }


@pytest.fixture
def mock_accessibility_far():
    """Distant medical facility."""
    return {
        "location": "test_far_medical",
        "medical_distance_km": 12.0,
        "medical_facility_name": "Remote Clinic",
        "detail": "Accessibility: Remote Clinic at 12.0km",
        "data_available": True
    }


@pytest.fixture
def mock_accessibility_unknown():
    """Unknown medical accessibility."""
    return {
        "location": "test_unknown_medical",
        "medical_distance_km": -1,
        "medical_facility_name": "Unknown",
        "detail": "Accessibility: No medical facilities found within 20km.",
        "data_available": False
    }
