import json
from shapely.geometry import shape, Point
from strands import Agent, tool
from strands.models.ollama import OllamaModel
import requests
import math
import os

# ---------------------------------------------------------------------------
# Load real flood data (from your Earth Engine Sentinel-1 export)
# ---------------------------------------------------------------------------

with open("data/sivasagar_flood.geojson", "r") as f:
    FLOOD_DATA = json.load(f)

FLOOD_POLYGONS = [shape(feature["geometry"]) for feature in FLOOD_DATA["features"]]

# Known reference point for Sivasagar town center
KNOWN_LOCATIONS = {
    "sivasagar": (94.6393, 26.9701),  # (longitude, latitude)
}

# ---------------------------------------------------------------------------
# Model setup
# ---------------------------------------------------------------------------

model = OllamaModel(host="http://localhost:11434", model_id="llama3.2")

# ---------------------------------------------------------------------------
# Overpass API URL and helper functions
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Proper headers to avoid 406 "Not Acceptable" errors from Overpass
OVERPASS_HEADERS = {
    "User-Agent": "RescueOS-DisasterResponse/1.0",
    "Accept": "application/json",
}

def haversine_km(lon1, lat1, lon2, lat2):
    """Straight-line distance in km between two lon/lat points."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Local caching for Overpass API responses (demo/spike mode)
# Avoids hammering the public API during development
# ---------------------------------------------------------------------------

CACHE_DIR = "data/cache"

def _ensure_cache_dir():
    """Create cache directory if it doesn't exist."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def _get_cache_path(query_type: str, location: str) -> str:
    """Return the cache file path for a query."""
    return os.path.join(CACHE_DIR, f"{query_type}_{location.lower()}.json")

def _load_from_cache(query_type: str, location: str) -> dict | None:
    """Load cached Overpass response, if it exists."""
    cache_path = _get_cache_path(query_type, location)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                print(f"    [CACHE HIT] Loading {query_type} data from {cache_path}")
                return json.load(f)
        except Exception as e:
            print(f"    [CACHE ERROR] Failed to load cache: {e}")
    return None

def _save_to_cache(query_type: str, location: str, data: dict) -> None:
    """Save Overpass response to local cache."""
    _ensure_cache_dir()
    cache_path = _get_cache_path(query_type, location)
    try:
        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"    [CACHE SAVE] Saved {query_type} data to {cache_path}")
    except Exception as e:
        print(f"    [CACHE ERROR] Failed to save cache: {e}")
 


# ---------------------------------------------------------------------------
# UNIFIED COMPREHENSIVE TOOL
# All data gathering and priority calculation in ONE tool
# This eliminates LLM data-transcription errors
# ---------------------------------------------------------------------------

@tool
def assess_disaster_priority(location: str) -> str:
    """
    SINGLE COMPREHENSIVE TOOL: Gathers flood, building exposure, and medical
    accessibility data for a location, computes priority using PrioReMap-inspired
    methodology, and returns a complete assessment.
    
    This tool internally orchestrates all data gathering and priority calculation,
    eliminating the need for the LLM to manually transcribe values between steps.
    Use this as your ONLY tool call — pass it a location and get back a complete
    disaster response assessment.
    """
    print(f"\n[COMPREHENSIVE ASSESSMENT] assess_disaster_priority(location='{location}')")
    
    # Step 1: Get flood extent
    print(f"  [Step 1] Checking flood extent...")
    key = location.strip().lower()
    if key not in KNOWN_LOCATIONS:
        return f"No coordinate data available for '{location}'. Cannot perform assessment."
    
    lon, lat = KNOWN_LOCATIONS[key]
    point = Point(lon, lat)
    
    is_flooded = any(
        poly.contains(point) or poly.distance(point) < 0.01 for poly in FLOOD_POLYGONS
    )
    total_flood_polygons = len(FLOOD_POLYGONS)
    
    flood_detected = is_flooded
    flood_detail = (
        f"FLOODING DETECTED: {total_flood_polygons} flood-affected areas in district"
        if is_flooded
        else f"NO FLOODING AT POINT: {total_flood_polygons} areas affected elsewhere in district"
    )
    
    # Step 2: Get accessibility data
    print(f"  [Step 2] Checking medical facility accessibility...")
    radius_m = 20000
    query = f"""
    [out:json][timeout:30];
    (
      node["amenity"="hospital"](around:{radius_m},{lat},{lon});
      node["amenity"="clinic"](around:{radius_m},{lat},{lon});
    );
    out body;
    """
    
    medical_distance_km = -1
    medical_facility_name = "Unknown"
    accessibility_detail = "Accessibility: UNAVAILABLE"
    
    # Try cache first
    cached_data = _load_from_cache("accessibility", location)
    
    if cached_data:
        data = cached_data
    else:
        try:
            response = requests.post(OVERPASS_URL, data={"data": query}, headers=OVERPASS_HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()
            _save_to_cache("accessibility", location, data)
        except requests.exceptions.Timeout:
            accessibility_detail = "Accessibility: TIMEOUT on Overpass API"
            data = None
        except Exception as e:
            print(f"    [DEBUG] Medical accessibility API error: {type(e).__name__}: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"    [DEBUG] HTTP Status: {e.response.status_code}")
            accessibility_detail = f"Accessibility: API ERROR ({type(e).__name__})"
            data = None
    
    if data:
        facilities = data.get("elements", [])
        
        if facilities:
            nearest = min(
                facilities,
                key=lambda f: haversine_km(lon, lat, f["lon"], f["lat"])
            )
            medical_distance_km = haversine_km(lon, lat, nearest["lon"], nearest["lat"])
            medical_facility_name = nearest.get("tags", {}).get("name", "Unnamed facility")
            accessibility_detail = f"Accessibility: {medical_facility_name} at {medical_distance_km:.1f}km"
    
    # Step 3: Get building exposure
    print(f"  [Step 3] Checking building exposure...")
    radius_m = 5000
    query = f"""
    [out:json][timeout:30];
    (
      way["building"](around:{radius_m},{lat},{lon});
    );
    out body;
    >;
    out skel qt;
    """
    
    exposure_ratio = 0.0
    total_buildings = 0
    exposed_count = 0
    exposure_detail = "Building exposure: UNAVAILABLE"
    
    # Try cache first
    cached_data = _load_from_cache("buildings", location)
    
    if cached_data:
        data = cached_data
    else:
        try:
            response = requests.post(OVERPASS_URL, data={"data": query}, headers=OVERPASS_HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()
            _save_to_cache("buildings", location, data)
        except requests.exceptions.Timeout:
            exposure_detail = "Building exposure: TIMEOUT on Overpass API"
            data = None
        except Exception as e:
            print(f"    [DEBUG] Building exposure API error: {type(e).__name__}: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"    [DEBUG] HTTP Status: {e.response.status_code}")
            exposure_detail = f"Building exposure: API ERROR ({type(e).__name__})"
            data = None
    
    if data:
        buildings = [el for el in data.get("elements", []) if el.get("type") == "way"]
        total_buildings = len(buildings)
        
        if total_buildings > 0:
            for building in buildings:
                node_coords = [
                    (n["lon"], n["lat"])
                    for n in data["elements"]
                    if n.get("type") == "node" and n["id"] in building.get("nodes", [])
                ]
                if not node_coords:
                    continue
                centroid_lon = sum(c[0] for c in node_coords) / len(node_coords)
                centroid_lat = sum(c[1] for c in node_coords) / len(node_coords)
                b_point = Point(centroid_lon, centroid_lat)
                if any(poly.contains(b_point) for poly in FLOOD_POLYGONS):
                    exposed_count += 1
            
            exposure_ratio = exposed_count / total_buildings if total_buildings else 0
            exposure_detail = f"Building exposure: {total_buildings} buildings, {exposed_count} exposed ({exposure_ratio*100:.0f}%)"
    
    # Step 4: Calculate priority (NO LLM INVOLVEMENT — pure deterministic computation)
    print(f"  [Step 4] Computing priority...")
    
    if not flood_detected:
        category = "NONE"
        pdc_score = 0.0
    else:
        # Use actual data, with 0.5 (medium) as unknown placeholder
        exp_ratio = exposure_ratio if total_buildings > 0 else 0.5
        med_dist = medical_distance_km if medical_distance_km >= 0 else -1
        
        exposure_score = min(exp_ratio * 1.5, 1.0)
        
        if med_dist < 0:
            accessibility_score = 0.5
        elif med_dist > 15:
            accessibility_score = 1.0
        elif med_dist > 5:
            accessibility_score = 0.66
        else:
            accessibility_score = 0.33
        
        pdc_score = round((exposure_score + accessibility_score) / 2, 2)
        
        if pdc_score >= 0.75:
            category = "HIGH PRIORITY"
        elif pdc_score >= 0.5:
            category = "PRIORITY"
        elif pdc_score >= 0.25:
            category = "EXPOSED"
        else:
            category = "SAFE"
    
    # Assemble final assessment
    data_confidence = "Medium" if total_buildings == 0 or medical_distance_km < 0 else "High"
    
    assessment = (
        f"\n{'='*70}\n"
        f"DISASTER RESPONSE ASSESSMENT FOR {location.upper()}\n"
        f"{'='*70}\n"
        f"Flood Status:       {flood_detail}\n"
        f"Building Exposure:  {exposure_detail}\n"
        f"Medical Access:     {accessibility_detail}\n"
        f"{'='*70}\n"
        f"PRIORITY CATEGORY:  {category}\n"
        f"PDC SCORE:          {pdc_score} (0-1 scale, higher = more urgent)\n"
        f"DATA CONFIDENCE:    {data_confidence}\n"
        f"{'='*70}\n"
        f"RECOMMENDATION:\n"
    )
    
    if category == "HIGH PRIORITY":
        assessment += "URGENT: Deploy medical team immediately with self-sufficiency supplies.\n"
    elif category == "PRIORITY":
        assessment += "Deploy medical team soon; coordinate with local authorities for access.\n"
    elif category == "EXPOSED":
        assessment += "Prepare medical response; monitor situation for escalation.\n"
    else:
        assessment += "No immediate medical team deployment required at this time.\n"
    
    assessment += (
        f"\nData gaps or uncertainty: "
        f"{'None' if data_confidence == 'High' else 'Building exposure and/or medical distance data unavailable or incomplete.'}\n"
        f"{'='*70}\n"
    )
    
    return assessment


# ---------------------------------------------------------------------------
# Agent with SINGLE UNIFIED TOOL
# ---------------------------------------------------------------------------

agent = Agent(
    model=model,
    tools=[assess_disaster_priority],
    system_prompt=(
        "You are a disaster-response assistant. For any location query, "
        "call the assess_disaster_priority tool with the location name. "
        "This tool will internally gather all necessary data (flood extent, "
        "building exposure, medical accessibility) and compute a priority score. "
        "Wait for the complete assessment result, then summarize the recommendation "
        "for the user in plain language, focusing on the priority category and "
        "what action is recommended."
    ),
)

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

print("\n" + "="*70)
print("QUERYING AGENT...")
print("="*70)

# Call the tool directly first to show raw structured output
print("\n[DIRECT TOOL CALL]")
raw_assessment = assess_disaster_priority("Sivasagar")
print(raw_assessment)

# Then show agent's paraphrase
print("\n[AGENT PARAPHRASE]")
response = agent("Should we send a medical team to Sivasagar?")
print(response)
print("="*70)
