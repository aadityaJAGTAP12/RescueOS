"""
Medical accessibility tool: finds nearest medical facility via Overpass API.

Extracted from Step 2 of assess_disaster_priority.
Includes cache-first pattern and error handling.
Accepts either a known location name or explicit lat/lon coordinates.
"""

import requests
from strands import tool
from agent.config import KNOWN_LOCATIONS, OVERPASS_URL, OVERPASS_HEADERS
from agent.data_loader import haversine_km, _load_from_cache, _save_to_cache
from agent.tools.flood_tool import _resolve_location, _cache_key_for_coords


@tool
def get_medical_accessibility(location: str = None, lat: float = None, lon: float = None) -> dict:
    """
    Find the nearest medical facility (hospital or clinic) within 20km radius.

    Accepts EITHER a known location name OR explicit lat/lon coordinates.

    Uses cache-first pattern: checks local cache before hitting Overpass API.
    On timeout/error, returns honest "UNAVAILABLE" message (not confirmed absence).

    Args:
        location: known location name (e.g. "sivasagar_flood_zone")
        lat: latitude coordinate (decimal degrees)
        lon: longitude coordinate (decimal degrees)

    Returns:
        {
            "location": str,
            "medical_distance_km": float or -1 if unavailable,
            "medical_facility_name": str,
            "detail": str,
            "data_available": bool
        }
    """
    print(f"  [Tool: get_medical_accessibility] location='{location}' lat={lat} lon={lon}")

    # Resolve location from name or coordinates
    point_lon, point_lat, location_label = _resolve_location(location, lat, lon)
    if point_lon is None:
        return {
            "location": str(location or "unknown"),
            "medical_distance_km": -1,
            "medical_facility_name": "Unknown",
            "detail": location_label.get("detail", "No location provided."),
            "data_available": False,
            "error": location_label.get("error", "No location provided.")
        }

    # Determine cache key: use name if known, coordinate string otherwise
    cache_key = location.strip().lower() if location else _cache_key_for_coords(point_lat, point_lon)

    radius_m = 20000

    query = f"""
    [out:json][timeout:30];
    (
      node["amenity"="hospital"](around:{radius_m},{point_lat},{point_lon});
      node["amenity"="clinic"](around:{radius_m},{point_lat},{point_lon});
    );
    out body;
    """

    # Try cache first
    cached_data = _load_from_cache("accessibility", cache_key)

    if cached_data:
        data = cached_data
    else:
        try:
            response = requests.post(
                OVERPASS_URL,
                data={"data": query},
                headers=OVERPASS_HEADERS,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            _save_to_cache("accessibility", cache_key, data)
        except requests.exceptions.Timeout:
            return {
                "location": location_label,
                "medical_distance_km": -1,
                "medical_facility_name": "Unknown",
                "detail": "Accessibility: TIMEOUT on Overpass API. Treat as unknown, not as confirmed absence.",
                "data_available": False,
                "error": "TIMEOUT on Overpass API (medical accessibility)"
            }
        except Exception as e:
            print(f"    [DEBUG] Medical accessibility API error: {type(e).__name__}: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"    [DEBUG] HTTP Status: {e.response.status_code}")
            return {
                "location": location_label,
                "medical_distance_km": -1,
                "medical_facility_name": "Unknown",
                "detail": f"Accessibility: API ERROR ({type(e).__name__}). Treat as unknown, not as confirmed absence.",
                "data_available": False,
                "error": f"API ERROR: {type(e).__name__}: {str(e)}"
            }

    # Parse facilities
    facilities = data.get("elements", [])

    if not facilities:
        return {
            "location": location_label,
            "medical_distance_km": -1,
            "medical_facility_name": "Unknown",
            "detail": "Accessibility: No medical facilities found within 20km.",
            "data_available": False
        }

    nearest = min(
        facilities,
        key=lambda f: haversine_km(point_lon, point_lat, f["lon"], f["lat"])
    )
    medical_distance_km = haversine_km(point_lon, point_lat, nearest["lon"], nearest["lat"])
    medical_facility_name = nearest.get("tags", {}).get("name", "Unnamed facility")

    return {
        "location": location_label,
        "medical_distance_km": medical_distance_km,
        "medical_facility_name": medical_facility_name,
        "detail": f"Accessibility: {medical_facility_name} at {medical_distance_km:.1f}km",
        "data_available": True
    }
