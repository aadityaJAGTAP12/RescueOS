"""
Accessibility Agent: a Strands Agent that reasons about medical/road accessibility.

This agent:
- Has access to medical_accessibility tool and road_status tool
- Uses LLM reasoning to call tools for a given location
- Accepts either a known location name or explicit lat/lon coordinates
- Reasons about accessibility challenges and road conditions
- Is exposed as a @tool (agents-as-tools pattern) so Coordinator can call it
"""

from strands import Agent, tool
from agent.config import model
from agent.tools.accessibility_tool import get_medical_accessibility
from agent.tools.road_status_tool import get_road_status


# Create the internal agent with access to accessibility and road status tools
_accessibility_agent = Agent(
    model=model,
    tools=[get_medical_accessibility, get_road_status],
    system_prompt=(
        "You are a disaster-response analyst specializing in accessibility and logistics assessment. "
        "For a given location, you MUST call BOTH tools:\n"
        "1. Call get_medical_accessibility to find the nearest medical facility.\n"
        "2. Call get_road_status to check if roads near the location are flood-affected.\n\n"
        "Both tools accept EITHER a location name OR explicit lat/lon coordinates. "
        "Use whichever was provided in the request. "
        "Call each tool EXACTLY ONCE. Do not guess or infer values the tools would provide. "
        "After calling both tools, reason about the medical facility distance, road conditions, "
        "and overall accessibility challenges. Summarize the findings clearly, citing the "
        "specific facility name, distance, and road status returned by the tools. "
        "If a tool returns an error or unavailable data, state that explicitly."
    ),
)


@tool
def accessibility_agent_tool(location: str = None, lat: float = None, lon: float = None) -> str:
    """
    Delegates to the accessibility agent, which reasons about medical
    facility accessibility and road conditions for a location using its own tools.

    Accepts EITHER a known location name OR explicit lat/lon coordinates.

    Args:
        location: name of location (e.g. "sivasagar_flood_zone")
        lat: latitude coordinate (decimal degrees)
        lon: longitude coordinate (decimal degrees)

    Returns: agent's assessment of medical accessibility and road status
    """
    loc_desc = location or f"({lat}, {lon})"
    print(f"\n[SUB-AGENT CALLED] accessibility_agent for '{loc_desc}'")

    if lat is not None and lon is not None:
        prompt = (
            f"Assess medical facility accessibility, road conditions, and logistics "
            f"challenges for coordinates: lat={lat}, lon={lon}"
        )
    else:
        prompt = (
            f"Assess medical facility accessibility, road conditions, and logistics "
            f"challenges for location: {location}"
        )

    response = _accessibility_agent(prompt)
    return str(response)
