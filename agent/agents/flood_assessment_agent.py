"""
Flood Assessment Agent: a Strands Agent that reasons about flood extent and building exposure.

This agent:
- Has access to flood_tool and exposure_tool
- Uses LLM reasoning to call both tools for a given location
- Synthesizes findings into a brief assessment
- Is exposed as a @tool (agents-as-tools pattern) so Coordinator can call it
"""

from strands import Agent, tool
from agent.config import model
from agent.tools.flood_tool import get_flood_status
from agent.tools.exposure_tool import get_building_exposure


# Create the internal agent with access to flood and exposure tools
_flood_assessment_agent = Agent(
    model=model,
    tools=[get_flood_status, get_building_exposure],
    system_prompt=(
        "You are a disaster-response analyst specializing in flood risk assessment. "
        "For a given location, you MUST call BOTH tools:\n"
        "1. Call get_flood_status FIRST to check flood status and flood polygon size.\n"
        "2. Call get_building_exposure SECOND to check building exposure in flood zones.\n\n"
        "Call each tool EXACTLY ONCE. Do not guess or infer values a tool would provide. "
        "After calling both tools, summarize the flood risk and building exposure findings "
        "clearly, citing the specific numbers returned by the tools (e.g., flood polygon area, "
        "building counts, exposure percentage). "
        "If a tool returns an error or unavailable data, state that explicitly."
    ),
)


@tool
def flood_assessment_agent_tool(location: str) -> str:
    """
    Delegates to the flood assessment agent, which reasons about flood
    extent and building exposure for a location using its own tools.

    Args:
        location: name of location (must be in KNOWN_LOCATIONS)

    Returns: agent's assessment of flood risk and building exposure
    """
    print(f"\n[SUB-AGENT CALLED] flood_assessment_agent for '{location}'")
    response = _flood_assessment_agent(
        f"Assess flood risk and building exposure for location: {location}"
    )
    return str(response)
