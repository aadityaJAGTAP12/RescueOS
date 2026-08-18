import json
from shapely.geometry import shape, Point
from strands import Agent, tool
from strands.models.ollama import OllamaModel
 
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
# Tool 1: REAL flood data tool
# ---------------------------------------------------------------------------
 
@tool
def get_flood_extent(location: str) -> str:
    """
    Checks real satellite-derived flood data (Sentinel-1 SAR, pre/post change
    detection) to determine if a given location is affected by flooding.
    Use this FIRST before any other analysis.
    """
    print(f"[TOOL CALLED] get_flood_extent(location='{location}')")
 
    key = location.strip().lower()
    if key not in KNOWN_LOCATIONS:
        return f"No coordinate data available for '{location}'. Cannot determine flood status."
 
    lon, lat = KNOWN_LOCATIONS[key]
    point = Point(lon, lat)
 
    is_flooded = any(
        poly.contains(point) or poly.distance(point) < 0.01 for poly in FLOOD_POLYGONS
    )
 
    total_flood_polygons = len(FLOOD_POLYGONS)
 
    if is_flooded:
        return (
            f"Flood data for {location}: FLOODING DETECTED near this location, "
            f"based on Sentinel-1 SAR change-detection analysis (source: NASA/Copernicus, "
            f"processed via Google Earth Engine). {total_flood_polygons} flood-affected "
            f"areas identified in the surrounding district. Confidence: Medium "
            f"(satellite-derived, not ground-verified)."
        )
    else:
        return (
            f"Flood data for {location}: No flood polygon detected at this exact point, "
            f"though {total_flood_polygons} flood-affected areas exist elsewhere in the "
            f"surrounding district. This location may still be at risk from nearby flooding."
        )
 
# ---------------------------------------------------------------------------
# Tool 2: REAL accessibility/medical facility tool (OpenStreetMap Overpass API)
# ---------------------------------------------------------------------------
 
import requests
import math
 
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
 
def haversine_km(lon1, lat1, lon2, lat2):
    """Straight-line distance in km between two lon/lat points."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
 
 
@tool
def get_accessibility_data(location: str) -> str:
    """
    Queries real OpenStreetMap data to find the nearest hospital/clinic and
    assess road access around a given location. Use this AFTER checking flood data.
    """
    print(f"[TOOL CALLED] get_accessibility_data(location='{location}')")
 
    key = location.strip().lower()
    if key not in KNOWN_LOCATIONS:
        return f"No coordinate data available for '{location}'. Cannot assess accessibility."
 
    lon, lat = KNOWN_LOCATIONS[key]
    radius_m = 20000  # search within 20km
 
    query = f"""
    [out:json][timeout:30];
    (
      node["amenity"="hospital"](around:{radius_m},{lat},{lon});
      node["amenity"="clinic"](around:{radius_m},{lat},{lon});
    );
    out body;
    """
 
    try:
        response = requests.post(OVERPASS_URL, data={"data": query}, timeout=35)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return (
            f"Accessibility data for {location}: UNAVAILABLE — could not reach "
            f"OpenStreetMap data source ({str(e)}). Cannot determine medical facility "
            f"distance. Treat as unknown, not as 'no facilities exist'."
        )
 
    facilities = data.get("elements", [])
 
    if not facilities:
        return (
            f"Accessibility data for {location}: no hospitals or clinics found in "
            f"OpenStreetMap within {radius_m/1000:.0f}km. This may mean there are none "
            f"nearby, OR that this rural area is under-mapped in OSM — treat with caution, "
            f"not as confirmed absence of medical care."
        )
 
    nearest = min(
        facilities,
        key=lambda f: haversine_km(lon, lat, f["lon"], f["lat"])
    )
    distance = haversine_km(lon, lat, nearest["lon"], nearest["lat"])
    facility_name = nearest.get("tags", {}).get("name", "Unnamed facility")
 
    return (
        f"Accessibility data for {location}: nearest medical facility is "
        f"'{facility_name}', approximately {distance:.1f}km away (source: OpenStreetMap, "
        f"straight-line distance, not road-network distance). "
        f"{len(facilities)} total medical facilities found within {radius_m/1000:.0f}km. "
        f"NOTE: population and road-cutoff-status data not yet integrated in this tool — "
        f"treat this as partial evidence only."
    )
 
 
# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
 
agent = Agent(
    model=model,
    tools=[get_flood_extent, get_accessibility_data],
    system_prompt=(
        "You are a disaster-response assistant. You MUST call BOTH tools before answering: "
        "first call get_flood_extent, then call get_accessibility_data. "
        "Do not answer until you have called both tools. "
        "Never guess or infer information a tool would provide — always call the tool instead. "
        "Stick closely to facts the tools actually returned — do not add general disaster-"
        "response knowledge (like disease risk) that the tools did not report. "
        "After both tool calls, give a short prioritized recommendation citing "
        "the specific numbers and confidence level returned by the tools, and clearly "
        "state what information is still missing or uncertain."
    ),
)

# ---------------------------------------------------------------------------
# Run agent query
# ---------------------------------------------------------------------------

print(">>> About to call agent...")
response = agent("Should we send a medical team to Sivasagar?")
print(">>> Agent call completed")
print("\n--- FINAL AGENT RESPONSE ---")
print(response)
