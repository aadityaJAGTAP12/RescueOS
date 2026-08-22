"""
ReliefOS Assessment Entry Point.

This module provides the clean application-level function for running
a ReliefOS disaster assessment. It separates:

1. Deterministic data gathering (tool calls)
2. Deterministic PDC calculation (calculate_priority)
3. Optional LLM synthesis (Strands coordinator)

The deterministic path always works without Ollama.
The LLM path is an optional enrichment layer.

Architecture:

    User/Application
           |
    run_relief_assessment()
           |
    +------+------+
    |             |
    v             v
  Deterministic  Optional LLM
  data gathering  synthesis
    |             |
    v             v
  Tools/data    Coordinator
    |          (Strands Agent)
    v             |
  calculate_priority()    |
    |                     |
    v                     v
  Structured ReliefOS Result
"""

from agent.tools.flood_tool import get_flood_status
from agent.tools.exposure_tool import get_building_exposure
from agent.tools.accessibility_tool import get_medical_accessibility
from agent.tools.allocation_tool import calculate_priority
from agent.config import KNOWN_LOCATIONS
from agent.agents.coordinator_agent import coordinator_synthesize


# ---------------------------------------------------------------------------
# Evidence gathering functions (deterministic, direct tool calls)
# ---------------------------------------------------------------------------

def gather_flood_evidence(location=None, lat=None, lon=None):
    """
    Gather flood and building exposure evidence from tools.

    Returns:
        {
            "flood_status": {flooded, exactly_contained, near_flood_zone, ...},
            "exposure": {total_buildings, exposed_count, exposure_ratio, ...},
        }
    """
    flood_status = get_flood_status(location=location, lat=lat, lon=lon)
    exposure = get_building_exposure(location=location, lat=lat, lon=lon)
    return {
        "flood_status": flood_status,
        "exposure": exposure,
    }


def gather_accessibility_evidence(location=None, lat=None, lon=None):
    """
    Gather medical accessibility evidence from tools.

    Returns:
        {
            "accessibility": {medical_distance_km, medical_facility_name, ...},
        }
    """
    accessibility = get_medical_accessibility(location=location, lat=lat, lon=lon)
    return {
        "accessibility": accessibility,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _determine_data_confidence(exposure, accessibility):
    """
    Deterministically compute data confidence from evidence availability.

    Both building exposure AND medical accessibility data must be available
    for High confidence. Otherwise Medium.
    """
    if exposure.get("data_available") and accessibility.get("data_available"):
        return "High"
    return "Medium"


def _resolve_location_label(location=None, lat=None, lon=None):
    """Resolve a human-readable location label from inputs."""
    if location is not None:
        return location
    if lat is not None and lon is not None:
        return f"({lat:.4f}, {lon:.4f})"
    return "unknown"


def _resolve_coordinates(location=None, lat=None, lon=None):
    """
    Resolve lat/lon from either a known location name or explicit coordinates.

    Returns:
        (lat, lon) on success, (None, None) if location name not found.
    """
    if lat is not None and lon is not None:
        return lat, lon
    if location is not None:
        key = location.strip().lower()
        if key in KNOWN_LOCATIONS:
            lon_val, lat_val = KNOWN_LOCATIONS[key]
            return lat_val, lon_val
    return None, None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_relief_assessment(location=None, lat=None, lon=None, use_llm=False):
    """
    Clean entry point for a ReliefOS disaster assessment.

    Deterministic path (always works, no Ollama needed):
        - Gathers flood, exposure, accessibility data from tools
        - Calculates PDC deterministically via calculate_priority()
        - Returns structured result

    LLM-enhanced path (requires Ollama when use_llm=True):
        - Same deterministic data gathering and PDC calculation
        - Invokes Strands coordinator for LLM-powered synthesis
        - Returns structured result with LLM recommendation

    Args:
        location: known location name (e.g. "sivasagar_flood_zone")
        lat: latitude coordinate (decimal degrees)
        lon: longitude coordinate (decimal degrees)
        use_llm: if True, invoke LLM coordinator for synthesis (requires Ollama)

    Returns:
        {
            "location": str,               # human-readable location label
            "coordinates": {               # resolved coordinates
                "lat": float or None,
                "lon": float or None,
            },
            "evidence": {                  # raw evidence from tools
                "flood": {...},
                "exposure": {...},
                "accessibility": {...},
            },
            "priority": {                  # deterministic PDC result
                "pdc_score": float,
                "category": str,
                "recommendation": str,
            },
            "data_confidence": str,        # "High" or "Medium"
            "llm_synthesis": str or None,  # LLM output if use_llm=True
        }
    """
    loc_label = _resolve_location_label(location, lat, lon)
    res_lat, res_lon = _resolve_coordinates(location, lat, lon)

    # --- Step 1: Gather evidence (deterministic, direct tool calls) ---
    flood_evidence = gather_flood_evidence(location=location, lat=lat, lon=lon)
    access_evidence = gather_accessibility_evidence(location=location, lat=lat, lon=lon)

    # --- Step 2: Extract values for PDC (deterministic) ---
    flood_data = flood_evidence["flood_status"]
    exposure_data = flood_evidence["exposure"]
    accessibility_data = access_evidence["accessibility"]

    flood_detected = flood_data["flooded"]
    exposure_ratio = exposure_data["exposure_ratio"]
    nearest_flood_polygon_km2 = flood_data["nearest_flood_polygon_km2"]
    medical_distance_km = accessibility_data["medical_distance_km"]
    data_confidence = _determine_data_confidence(exposure_data, accessibility_data)

    # --- Step 3: Calculate PDC (deterministic) ---
    priority = calculate_priority(
        flood_detected=flood_detected,
        exposure_ratio=exposure_ratio,
        nearest_flood_polygon_km2=nearest_flood_polygon_km2,
        medical_distance_km=medical_distance_km,
        data_confidence=data_confidence,
    )

    # --- Step 4: Optional LLM synthesis ---
    llm_synthesis = None
    if use_llm:
        try:
            llm_synthesis = coordinator_synthesize(
                location=location, lat=lat, lon=lon,
                flood_data=flood_data,
                exposure_data=exposure_data,
                accessibility_data=accessibility_data,
                priority=priority,
            )
        except Exception as e:
            llm_synthesis = f"LLM synthesis unavailable: {e}"

    # --- Step 5: Build structured result ---
    result = {
        "location": loc_label,
        "coordinates": {
            "lat": res_lat,
            "lon": res_lon,
        },
        "evidence": {
            "flood": flood_data,
            "exposure": exposure_data,
            "accessibility": accessibility_data,
        },
        "priority": priority,
        "data_confidence": data_confidence,
        "llm_synthesis": llm_synthesis,
    }

    return result
