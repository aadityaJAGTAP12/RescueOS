"""
Allocation Agent: a Strands Agent that computes priority scores from disaster assessment data.

This agent:
- Has access to calculate_priority tool
- Receives data from flood, exposure, and accessibility assessments as text context
- Reasons about data completeness to determine data_confidence
- Calls calculate_priority with the right arguments
- Explains the priority reasoning
- Is exposed as a @tool (agents-as-tools pattern) so Coordinator can call it
"""

from strands import Agent, tool
from agent.config import model
from agent.tools.allocation_tool import calculate_priority


# Create the internal agent with access to priority calculation tool
_allocation_agent = Agent(
    model=model,
    tools=[calculate_priority],
    system_prompt=(
        "You are a disaster-response prioritization analyst. "
        "You will receive a structured data summary with exact numeric values for: "
        "flood_detected, exposure_ratio, nearest_flood_polygon_km2, and medical_distance_km.\n\n"
        "Your job is to:\n"
        "1. READ the data summary and determine data_confidence based on completeness:\n"
        "   - If BOTH building exposure AND medical accessibility data are available: data_confidence = 'High'\n"
        "   - If EITHER is missing or unavailable: data_confidence = 'Medium'\n"
        "2. Call calculate_priority with the EXACT values provided in the data summary.\n"
        "   Do NOT modify, round, or guess any numeric values. Pass them through exactly.\n"
        "   If a value is listed as 'unavailable', use -1 for medical_distance_km or 0.0 for exposure_ratio.\n"
        "3. Report the PDC score, category, and recommendation from the tool result.\n\n"
        "CRITICAL: Do NOT invent or estimate numeric values. Only use the exact numbers provided."
    ),
)


@tool
def allocation_agent_tool(
    flood_detected: bool,
    exposure_ratio: float,
    nearest_flood_polygon_km2: float,
    medical_distance_km: float,
    data_confidence: str,
    location: str = ""
) -> str:
    """
    Delegates to the allocation agent, which reasons about data completeness
    and computes the priority score using the calculate_priority tool.

    Args:
        flood_detected: whether location is in/near flood zone
        exposure_ratio: proportion of buildings in flood zone (0-1)
        nearest_flood_polygon_km2: size of nearest flood polygon
        medical_distance_km: distance to nearest medical facility (-1 if unknown)
        data_confidence: 'High' or 'Medium' based on data availability
        location: (optional) location name for logging

    Returns: prioritization explanation and recommendation
    """
    print(f"\n[SUB-AGENT CALLED] allocation_agent for '{location}'")

    # Build a structured data summary for the agent to reason about
    data_summary = (
        f"DATA SUMMARY FOR LOCATION: {location}\n"
        f"flood_detected: {flood_detected}\n"
        f"exposure_ratio: {exposure_ratio}\n"
        f"nearest_flood_polygon_km2: {nearest_flood_polygon_km2}\n"
        f"medical_distance_km: {medical_distance_km} "
        f"({'available' if medical_distance_km >= 0 else 'unavailable'})\n"
        f"data_confidence: {data_confidence}\n"
    )

    prompt = (
        f"Given the following disaster assessment data, determine the data_confidence "
        f"based on completeness, then call calculate_priority with the exact values.\n\n"
        f"{data_summary}\n"
        f"Call calculate_priority now with these exact parameters."
    )

    response = _allocation_agent(prompt)
    return str(response)
