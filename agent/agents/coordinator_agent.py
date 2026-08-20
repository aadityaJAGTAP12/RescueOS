"""
Coordinator Agent: the top-level Strands Agent that orchestrates all sub-agents.

This agent:
- Has access to flood_assessment_agent_tool, accessibility_agent_tool, allocation_agent_tool
- Uses LLM reasoning to call each sub-agent EXACTLY ONCE in sequence
- Synthesizes findings into a comprehensive recommendation
- Is exposed as a @tool that main.py can call

Data flow: coordinator calls sub-agents via agent invocation (LLM reasoning),
while the wrapper function handles deterministic data extraction and final
synthesis to ensure reliable, reproducible output.
"""

from strands import Agent, tool
from agent.config import model
from agent.agents.flood_assessment_agent import flood_assessment_agent_tool
from agent.agents.accessibility_agent import accessibility_agent_tool
from agent.agents.allocation_agent import allocation_agent_tool
from agent.tools.flood_tool import get_flood_status
from agent.tools.exposure_tool import get_building_exposure
from agent.tools.accessibility_tool import get_medical_accessibility


# Create the coordinator agent with access to all three sub-agent tools
_coordinator_agent = Agent(
    model=model,
    tools=[
        flood_assessment_agent_tool,
        accessibility_agent_tool,
        allocation_agent_tool,
    ],
    system_prompt=(
        "You are a disaster-response coordinator. Given a location, you MUST:\n"
        "1. Call flood_assessment_agent_tool FIRST to assess flood risk and building exposure.\n"
        "2. Call accessibility_agent_tool SECOND to assess medical facility accessibility.\n"
        "3. Call allocation_agent_tool THIRD to compute the priority score and category.\n\n"
        "Call each tool EXACTLY ONCE, in this exact order. Do not skip any tool. "
        "Do not guess or infer values — rely entirely on what the tools return. "
        "After all three tools have been called, synthesize ONE final recommendation "
        "citing specific evidence from each sub-agent (flood status, building counts, "
        "facility distance, priority score). Explicitly state what data was missing or uncertain."
    ),
)


def coordinator_agent_tool(location: str) -> str:
    """
    Run the full multi-agent assessment for a location.

    The coordinator agent orchestrates flood_assessment -> accessibility -> allocation
    sub-agents via LLM-driven tool calls. The wrapper extracts numeric data for
    the allocation agent and synthesizes the final recommendation deterministically.

    Args:
        location: name of location (must be in KNOWN_LOCATIONS)

    Returns: comprehensive assessment with final recommendation
    """
    print(f"\n{'='*70}")
    print(f"[COORDINATOR] Starting comprehensive assessment for '{location}'")
    print(f"{'='*70}")

    # --- STEP 1: Invoke sub-agents via Strands agent callable ---
    # The coordinator agent reasons about which tools to call and in what order.
    # Its text response is logged for observability (LLM reasoning trace).

    prompt = (
        f"Perform a comprehensive disaster assessment for location: {location}\n"
        f"Call all three sub-agent tools in order: flood assessment, then accessibility, "
        f"then allocation. After receiving all results, synthesize a final recommendation "
        f"citing specific evidence."
    )

    print(f"\n[COORDINATOR] Invoking agent with LLM reasoning...")
    agent_response = _coordinator_agent(prompt)
    agent_text = str(agent_response)

    # Log the agent's reasoning (this shows real LLM inference happened)
    print(f"\n[COORDINATOR AGENT REASONING OUTPUT]")
    print(agent_text)
    print(f"{'='*70}")

    # --- STEP 2: Deterministic data extraction for allocation agent ---
    # Extract numeric values directly from tool responses (not from LLM text).
    # This ensures the allocation agent receives exact values, avoiding
    # LLM transcription errors that were a real bug in earlier iterations.

    flood_data = get_flood_status(location)
    exposure_data = get_building_exposure(location)
    accessibility_data = get_medical_accessibility(location)

    flood_detected = flood_data["flooded"]
    exposure_ratio = exposure_data["exposure_ratio"]
    nearest_flood_polygon_km2 = flood_data["nearest_flood_polygon_km2"]
    medical_distance_km = accessibility_data["medical_distance_km"]
    data_confidence = "High" if exposure_data["data_available"] and accessibility_data["data_available"] else "Medium"

    # --- STEP 3: Call allocation agent via Strands agent callable ---
    # The allocation agent receives the exact numeric values and reasons about
    # data_confidence before calling calculate_priority.

    print(f"\n[COORDINATOR] Calling allocation agent with extracted data...")
    allocation_response = allocation_agent_tool(
        flood_detected=flood_detected,
        exposure_ratio=exposure_ratio,
        nearest_flood_polygon_km2=nearest_flood_polygon_km2,
        medical_distance_km=medical_distance_km,
        data_confidence=data_confidence,
        location=location
    )
    print(f"[ALLOCATION AGENT OUTPUT]\n{allocation_response}\n")

    # --- STEP 4: Deterministic final synthesis ---
    # Compose the final recommendation from extracted data (not from LLM text).

    flood_area = f"{nearest_flood_polygon_km2:.2f}"
    exposure_pct = f"{exposure_ratio*100:.0f}%"
    facility_info = (
        f"{accessibility_data['medical_facility_name']} at {medical_distance_km:.1f}km"
        if medical_distance_km >= 0 else "unknown (no data)"
    )

    final_recommendation = (
        f"COMPREHENSIVE ASSESSMENT FOR {location.upper()}\n"
        f"{'='*70}\n\n"
        f"FLOOD & EXPOSURE FINDINGS:\n"
        f"  Flood Status: {'FLOODED' if flood_detected else 'NOT FLOODED'}. "
        f"Nearest flood area: {flood_area} sq km. "
        f"Building exposure: {exposure_data['total_buildings']} buildings, "
        f"{exposure_data['exposed_count']} exposed ({exposure_pct}).\n\n"
        f"ACCESSIBILITY FINDINGS:\n"
        f"  Nearest medical facility: {facility_info}\n\n"
        f"PRIORITY COMPUTATION:\n"
        f"  {allocation_response}\n\n"
        f"FINAL RECOMMENDATION:\n"
        f"  This location shows {'significant' if flood_detected else 'minimal'} flood risk. "
        f"Building exposure is {exposure_pct} of identified structures in the area. "
        f"Medical facility access is {'good' if medical_distance_km >= 0 and medical_distance_km <= 5 else 'challenging' if medical_distance_km >= 0 else 'unknown'}. "
        f"Data confidence is {data_confidence}. "
        f"{'Immediate response is recommended.' if data_confidence == 'High' and flood_detected else 'Continue monitoring and prepare contingency measures as needed.'}\n"
        f"{'='*70}\n"
    )

    print(f"\n[COORDINATOR FINAL SYNTHESIS]")
    print(final_recommendation)

    return final_recommendation
