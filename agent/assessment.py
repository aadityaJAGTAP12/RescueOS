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

import time

from agent.tools.flood_tool import get_flood_status
from agent.tools.exposure_tool import get_building_exposure
from agent.tools.accessibility_tool import get_medical_accessibility
from agent.tools.allocation_tool import calculate_priority
from agent.config import KNOWN_LOCATIONS
from agent.data_loader import get_known_locations, get_all_known_locations
from agent.agents.coordinator_agent import coordinator_synthesize


# ---------------------------------------------------------------------------
# Evidence gathering functions (deterministic, direct tool calls)
# ---------------------------------------------------------------------------

def gather_flood_evidence(location=None, lat=None, lon=None, agent_trace=None):
    """
    Gather flood and building exposure evidence from tools.

    If agent_trace is provided (a list), appends timing entries for each tool call.

    Returns:
        {
            "flood_status": {flooded, exactly_contained, near_flood_zone, ...},
            "exposure": {total_buildings, exposed_count, exposure_ratio, ...},
        }
    """
    loc_label = location or f"({lat:.4f}, {lon:.4f})" if lat and lon else "unknown"

    # Flood status
    _t0 = time.time()
    flood_status = get_flood_status(location=location, lat=lat, lon=lon)
    _t1 = time.time()
    if agent_trace is not None:
        agent_trace.append({
            "agent_name": "flood_assessment_agent",
            "query_portion_handled": f"Flood status check for {loc_label}",
            "started_at": _t0,
            "completed_at": _t1,
            "duration_ms": round((_t1 - _t0) * 1000, 1),
            "tools_called": ["get_flood_status"],
            "output_summary": flood_status.get("detail", "Flood status checked"),
            "raw_output": flood_status,
            "status": "complete",
        })

    # Building exposure
    _t0 = time.time()
    exposure = get_building_exposure(location=location, lat=lat, lon=lon)
    _t1 = time.time()
    if agent_trace is not None:
        agent_trace.append({
            "agent_name": "exposure_agent",
            "query_portion_handled": f"Building exposure analysis for {loc_label}",
            "started_at": _t0,
            "completed_at": _t1,
            "duration_ms": round((_t1 - _t0) * 1000, 1),
            "tools_called": ["get_building_exposure"],
            "output_summary": exposure.get("detail", "Building exposure checked"),
            "raw_output": exposure,
            "status": "complete",
        })

    return {
        "flood_status": flood_status,
        "exposure": exposure,
    }


def gather_accessibility_evidence(location=None, lat=None, lon=None, agent_trace=None):
    """
    Gather medical accessibility evidence from tools.

    If agent_trace is provided (a list), appends timing entries for each tool call.

    Returns:
        {
            "accessibility": {medical_distance_km, medical_facility_name, ...},
        }
    """
    loc_label = location or f"({lat:.4f}, {lon:.4f})" if lat and lon else "unknown"

    _t0 = time.time()
    accessibility = get_medical_accessibility(location=location, lat=lat, lon=lon)
    _t1 = time.time()
    if agent_trace is not None:
        facility_name = accessibility.get("medical_facility_name", "Unknown")
        dist = accessibility.get("medical_distance_km", -1)
        summary = f"Nearest facility: {facility_name} at {dist:.1f}km" if dist >= 0 else "No medical facility data available"
        agent_trace.append({
            "agent_name": "accessibility_agent",
            "query_portion_handled": f"Medical accessibility check for {loc_label}",
            "started_at": _t0,
            "completed_at": _t1,
            "duration_ms": round((_t1 - _t0) * 1000, 1),
            "tools_called": ["get_medical_accessibility"],
            "output_summary": summary,
            "raw_output": accessibility,
            "status": "complete",
        })

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

    Phase 4: Uses repository-backed location resolution when available.
    Falls back to legacy KNOWN_LOCATIONS.

    Returns:
        (lat, lon) on success, (None, None) if location name not found.
    """
    if lat is not None and lon is not None:
        return lat, lon
    if location is not None:
        key = location.strip().lower()
        # Phase 4: Try repository-backed resolution first
        all_locs = get_all_known_locations()
        if key in all_locs:
            lon_val, lat_val = all_locs[key]
            return lat_val, lon_val
        # Fallback to legacy KNOWN_LOCATIONS
        if key in KNOWN_LOCATIONS:
            lon_val, lat_val = KNOWN_LOCATIONS[key]
            return lat_val, lon_val
    return None, None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_relief_assessment(location=None, lat=None, lon=None, use_llm=False, agent_trace=None):
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
        agent_trace: if provided (a list), appends per-agent timing entries

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
    flood_evidence = gather_flood_evidence(location=location, lat=lat, lon=lon, agent_trace=agent_trace)
    access_evidence = gather_accessibility_evidence(location=location, lat=lat, lon=lon, agent_trace=agent_trace)

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
    _t0 = time.time()
    priority = calculate_priority(
        flood_detected=flood_detected,
        exposure_ratio=exposure_ratio,
        nearest_flood_polygon_km2=nearest_flood_polygon_km2,
        medical_distance_km=medical_distance_km,
        data_confidence=data_confidence,
    )
    _t1 = time.time()
    if agent_trace is not None:
        agent_trace.append({
            "agent_name": "allocation_agent",
            "query_portion_handled": f"Priority scoring (PDC) for {loc_label}",
            "started_at": _t0,
            "completed_at": _t1,
            "duration_ms": round((_t1 - _t0) * 1000, 1),
            "tools_called": ["calculate_priority"],
            "output_summary": f"PDC {priority['pdc_score']:.2f} — {priority['category']}",
            "raw_output": priority,
            "status": "complete",
        })

    # --- Step 4: Optional LLM synthesis ---
    llm_synthesis = None
    if use_llm:
        _t0 = time.time()
        try:
            llm_synthesis = coordinator_synthesize(
                location=location, lat=lat, lon=lon,
                flood_data=flood_data,
                exposure_data=exposure_data,
                accessibility_data=accessibility_data,
                priority=priority,
            )
            _t1 = time.time()
            if agent_trace is not None:
                agent_trace.append({
                    "agent_name": "coordinator_agent",
                    "query_portion_handled": f"LLM synthesis for {loc_label}",
                    "started_at": _t0,
                    "completed_at": _t1,
                    "duration_ms": round((_t1 - _t0) * 1000, 1),
                    "tools_called": ["coordinator_synthesize"],
                    "output_summary": (llm_synthesis[:200] + "...") if len(llm_synthesis) > 200 else llm_synthesis,
                    "raw_output": llm_synthesis,
                    "status": "complete",
                })
        except Exception as e:
            _t1 = time.time()
            llm_synthesis = f"LLM synthesis unavailable: {e}"
            if agent_trace is not None:
                agent_trace.append({
                    "agent_name": "coordinator_agent",
                    "query_portion_handled": f"LLM synthesis for {loc_label}",
                    "started_at": _t0,
                    "completed_at": _t1,
                    "duration_ms": round((_t1 - _t0) * 1000, 1),
                    "tools_called": ["coordinator_synthesize"],
                    "output_summary": f"LLM synthesis failed: {type(e).__name__}",
                    "raw_output": str(e),
                    "status": "error",
                })

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
