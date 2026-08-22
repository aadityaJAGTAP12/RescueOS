"""
Coordinator Agent: optional LLM enrichment for ReliefOS assessments.

This module provides two capabilities:

1. coordinator_synthesize() — called by run_relief_assessment() when use_llm=True.
   Receives pre-gathered evidence and asks the LLM to synthesize an
   evidence-based recommendation. The LLM does NOT calculate PDC or
   gather data — those are done deterministically by run_relief_assessment().

2. coordinator_agent_tool() — standalone Strands agent for interactive use.
   The LLM orchestrates specialist sub-agents via tool calls.

Architecture:

    run_relief_assessment(use_llm=True)
        |
        v
    coordinator_synthesize(evidence, priority)
        |
        v
    Strands Agent reviews evidence
        |
        +--> (optionally) calls specialist agents for deeper analysis
        |
        v
    LLM synthesizes recommendation text
        |
        v
    Returns structured result (PDC already computed deterministically)

Key design principle:
    - The LLM adds value in INTERPRETATION and SYNTHESIS
    - The LLM does NOT compute numerical scores (PDC is deterministic)
    - The LLM does NOT gather data (tools do that deterministically)
    - The LLM CAN call specialist agents for deeper analysis when useful
"""

from strands import Agent, tool
from agent.config import model, KNOWN_LOCATIONS
from agent.agents.flood_assessment_agent import flood_assessment_agent_tool
from agent.agents.accessibility_agent import accessibility_agent_tool
from agent.agents.supply_matching_agent import supply_matching_agent_tool
from agent.community_reports import get_reports_near


# ---------------------------------------------------------------------------
# Strands Agent for LLM synthesis
# ---------------------------------------------------------------------------

_coordinator_agent = Agent(
    model=model,
    tools=[
        flood_assessment_agent_tool,
        accessibility_agent_tool,
        supply_matching_agent_tool,
    ],
    system_prompt=(
        "You are a disaster-response coordinator. You have already received "
        "structured evidence from deterministic tool calls. Your job is to:\n\n"
        "1. REVIEW the flood evidence, exposure data, and accessibility data.\n"
        "2. If community reports are mentioned, call supply_matching_agent_tool "
        "to get supply recommendations.\n"
        "3. Synthesize a clear, evidence-based recommendation.\n\n"
        "CRITICAL RULES:\n"
        "- Always cite specific numbers from the evidence (building counts, "
        "distances, polygon areas, PDC scores).\n"
        "- NEVER invent or estimate numerical values. Only use what is provided.\n"
        "- If data is missing or uncertain, state that explicitly.\n"
        "- The PDC score and category have already been computed deterministically. "
        "Do not override them.\n"
        "- Your role is INTERPRETATION, not recalculation."
    ),
)


# ---------------------------------------------------------------------------
# coordinator_synthesize() — called by run_relief_assessment()
# ---------------------------------------------------------------------------

def coordinator_synthesize(
    location=None,
    lat=None,
    lon=None,
    flood_data=None,
    exposure_data=None,
    accessibility_data=None,
    priority=None,
):
    """
    LLM-powered synthesis for a ReliefOS assessment.

    Called by run_relief_assessment() when use_llm=True.
    Evidence and PDC are already computed deterministically.
    The LLM's job is to interpret the evidence and produce a recommendation.

    Args:
        location: location name or None
        lat/lon: coordinates or None
        flood_data: flood status dict from get_flood_status()
        exposure_data: building exposure dict from get_building_exposure()
        accessibility_data: accessibility dict from get_medical_accessibility()
        priority: PDC result dict from calculate_priority()

    Returns:
        LLM-generated synthesis string (not authoritative — PDC is authoritative)
    """
    loc_desc = location or f"({lat}, {lon})"

    # Build evidence context for the LLM
    flood_status_str = _format_flood_status(flood_data)
    exposure_pct = f"{exposure_data.get('exposure_ratio', 0) * 100:.0f}%"
    facility_info = _format_facility_info(accessibility_data)

    # Check for community reports
    has_reports = False
    lookup_lat, lookup_lon = None, None
    if lat is not None and lon is not None:
        lookup_lat, lookup_lon = lat, lon
    elif location is not None:
        key = location.strip().lower()
        if key in KNOWN_LOCATIONS:
            lookup_lon, lookup_lat = KNOWN_LOCATIONS[key]

    if lookup_lat is not None and lookup_lon is not None:
        nearby = get_reports_near(lookup_lat, lookup_lon, radius_km=3.0)
        has_reports = len(nearby) > 0

    # Build prompt with all evidence
    evidence_text = (
        f"EVIDENCE FOR {loc_desc.upper()}:\n\n"
        f"FLOOD STATUS:\n"
        f"  {flood_status_str}\n"
        f"  Flooded: {flood_data.get('flooded', False)}\n"
        f"  Exactly contained: {flood_data.get('exactly_contained', False)}\n"
        f"  Near flood zone: {flood_data.get('near_flood_zone', False)}\n"
        f"  Nearest flood polygon: {flood_data.get('nearest_flood_polygon_km2', 0):.2f} sq km\n"
        f"  Total flood polygons in district: {flood_data.get('total_flood_polygons', 0)}\n\n"
        f"BUILDING EXPOSURE:\n"
        f"  Total buildings: {exposure_data.get('total_buildings', 0)}\n"
        f"  Exposed buildings: {exposure_data.get('exposed_count', 0)}\n"
        f"  Exposure ratio: {exposure_pct}\n"
        f"  Data available: {exposure_data.get('data_available', False)}\n\n"
        f"ACCESSIBILITY:\n"
        f"  {facility_info}\n"
        f"  Medical distance: {accessibility_data.get('medical_distance_km', -1)} km\n"
        f"  Data available: {accessibility_data.get('data_available', False)}\n\n"
        f"DETERMINISTIC PRIORITY (do NOT override):\n"
        f"  PDC Score: {priority.get('pdc_score', 0.0)}\n"
        f"  Category: {priority.get('category', 'UNKNOWN')}\n"
        f"  Recommendation: {priority.get('recommendation', 'N/A')}\n\n"
        f"Community reports available: {has_reports}\n"
    )

    if has_reports:
        evidence_text += (
            "Community reports exist for this location. "
            "Call supply_matching_agent_tool with the coordinates to get "
            "supply recommendations based on self-reported community needs.\n"
        )

    prompt = (
        f"Review the following disaster assessment evidence and synthesize "
        f"a clear, evidence-based recommendation.\n\n"
        f"{evidence_text}\n"
        f"Cite specific numbers. State what data was missing or uncertain. "
        f"The PDC score is the authoritative priority metric — do not recalculate."
    )

    response = _coordinator_agent(prompt)
    return str(response)


# ---------------------------------------------------------------------------
# coordinator_agent_tool() — standalone Strands agent for interactive use
# ---------------------------------------------------------------------------

@tool
def coordinator_agent_tool(location=None, lat=None, lon=None):
    """
    Run the full multi-agent assessment via Strands agent orchestration.

    This is the standalone entry point for interactive use. The LLM
    orchestrates specialist sub-agents via tool calls.

    For the programmatic entry point, use run_relief_assessment() instead.

    Args:
        location: known location name (e.g. "sivasagar_flood_zone")
        lat: latitude coordinate (decimal degrees)
        lon: longitude coordinate (decimal degrees)

    Returns:
        LLM-generated comprehensive assessment string
    """
    loc_desc = location or f"({lat}, {lon})"

    # Build prompt for the LLM
    if lat is not None and lon is not None:
        prompt = (
            f"Perform a comprehensive disaster assessment for coordinates: "
            f"lat={lat}, lon={lon}\n"
            f"Call flood_assessment_agent_tool and accessibility_agent_tool "
            f"to gather evidence. Then synthesize a recommendation."
        )
    else:
        prompt = (
            f"Perform a comprehensive disaster assessment for location: {location}\n"
            f"Call flood_assessment_agent_tool and accessibility_agent_tool "
            f"to gather evidence. Then synthesize a recommendation."
        )

    response = _coordinator_agent(prompt)
    return str(response)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_flood_status(flood_data):
    """Format flood status into a human-readable string."""
    if flood_data.get("exactly_contained"):
        return "EXACTLY INSIDE FLOOD ZONE"
    elif flood_data.get("near_flood_zone"):
        return "NEAR FLOOD ZONE (within ~1.1km, not inside polygon)"
    else:
        return "NOT FLOOD-AFFECTED"


def _format_facility_info(accessibility_data):
    """Format medical facility info into a human-readable string."""
    dist = accessibility_data.get("medical_distance_km", -1)
    name = accessibility_data.get("medical_facility_name", "Unknown")
    if dist >= 0:
        return f"{name} at {dist:.1f}km"
    return "unknown (no data)"
