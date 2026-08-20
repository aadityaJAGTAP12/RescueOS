"""
Medical accessibility tool: finds nearest medical facility via Overpass API.

Extracted from Step 2 of assess_disaster_priority.
Includes cache-first pattern and error handling.
"""

import requests
from strands import tool
from agent.config import KNOWN_LOCATIONS, OVERPASS_URL, OVERPASS_HEADERS
from agent.data_loader import haversine_km, _load_from_cache, _save_to_cache


@tool
def get_medical_accessibility(location: str) -> dict:
    """
    Find the nearest medical facility (hospital or clinic) within 20km radius.
    
    Uses cache-first pattern: checks local cache before hitting Overpass API.
    On timeout/error, returns honest "UNAVAILABLE" message (not confirmed absence).
    
    Returns:
        {
            "location": str,
            "medical_distance_km": float or -1 if unavailable,
            "medical_facility_name": str,
            "detail": str,
            "data_available": bool
        }
    """
    print(f"  [Tool: get_medical_accessibility] location='{location}'")
    
    # Validate location
    key = location.strip().lower()
    if key not in KNOWN_LOCATIONS:
        return {
            "location": location,
            "medical_distance_km": -1,
            "medical_facility_name": "Unknown",
            "detail": f"No coordinate data available for '{location}'.",
            "data_available": False,
            "error": f"Location '{location}' not in KNOWN_LOCATIONS."
        }
    
    lon, lat = KNOWN_LOCATIONS[key]
    radius_m = 20000
    
    query = f"""
    [out:json][timeout:30];
    (
      node["amenity"="hospital"](around:{radius_m},{lat},{lon});
      node["amenity"="clinic"](around:{radius_m},{lat},{lon});
    );
    out body;
    """
    
    # Try cache first
    cached_data = _load_from_cache("accessibility", location)
    
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
            _save_to_cache("accessibility", location, data)
        except requests.exceptions.Timeout:
            return {
                "location": location,
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
                "location": location,
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
            "location": location,
            "medical_distance_km": -1,
            "medical_facility_name": "Unknown",
            "detail": "Accessibility: No medical facilities found within 20km.",
            "data_available": False
        }
    
    nearest = min(
        facilities,
        key=lambda f: haversine_km(lon, lat, f["lon"], f["lat"])
    )
    medical_distance_km = haversine_km(lon, lat, nearest["lon"], nearest["lat"])
    medical_facility_name = nearest.get("tags", {}).get("name", "Unnamed facility")
    
    return {
        "location": location,
        "medical_distance_km": medical_distance_km,
        "medical_facility_name": medical_facility_name,
        "detail": f"Accessibility: {medical_facility_name} at {medical_distance_km:.1f}km",
        "data_available": True
    }
