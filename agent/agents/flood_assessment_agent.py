"""
Flood Assessment Agent: a Strands Agent that reasons about flood extent and building exposure.

This agent:
- Has access to flood_tool, exposure_tool, and region_scan_tool
- Uses LLM reasoning to call tools for a given location or region
- Accepts either a known location name or explicit lat/lon coordinates
- Can scan a region to find all flood-affected points
- Synthesizes findings into a brief assessment
- Is exposed as a @tool (agents-as-tools pattern) so Coordinator can call it
"""

from strands import Agent, tool
from agent.config import model
from agent.tools.flood_tool import get_flood_status
from agent.tools.exposure_tool import get_building_exposure
from agent.tools.region_scan_tool import scan_region


# Create the internal agent with access to flood, exposure, and region scan tools
_flood_assessment_agent = Agent(
    model=model,
    tools=[get_flood_status, get_building_exposure, scan_region],
    system_prompt=(
        "You are a disaster-response analyst specializing in flood risk assessment. "
        "For a given location, you MUST call BOTH tools:\n"
        "1. Call get_flood_status FIRST to check flood status and flood polygon size.\n"
        "2. Call get_building_exposure SECOND to check building exposure in flood zones.\n\n"
        "Both tools accept EITHER a location name OR explicit lat/lon coordinates. "
        "Use whichever was provided in the request. "
        "Call each tool EXACTLY ONCE. Do not guess or infer values a tool would provide. "
        "After calling both tools, summarize the flood risk and building exposure findings "
        "clearly, citing the specific numbers returned by the tools (e.g., flood polygon area, "
        "building counts, exposure percentage). "
        "If a tool returns an error or unavailable data, state that explicitly.\n\n"
        "You also have access to scan_region, which scans a rectangular area for flood-affected "
        "points. Use it ONLY when asked to scan a region. For single-location assessment, "
        "use get_flood_status and get_building_exposure."
    ),
)


@tool
def flood_assessment_agent_tool(location: str = None, lat: float = None, lon: float = None) -> str:
    """
    Delegates to the flood assessment agent, which reasons about flood
    extent and building exposure for a location using its own tools.

    Accepts EITHER a known location name OR explicit lat/lon coordinates.

    Args:
        location: name of location (e.g. "sivasagar_flood_zone")
        lat: latitude coordinate (decimal degrees)
        lon: longitude coordinate (decimal degrees)

    Returns: agent's assessment of flood risk and building exposure
    """
    loc_desc = location or f"({lat}, {lon})"
    print(f"\n[SUB-AGENT CALLED] flood_assessment_agent for '{loc_desc}'")

    if lat is not None and lon is not None:
        prompt = f"Assess flood risk and building exposure for coordinates: lat={lat}, lon={lon}"
    else:
        prompt = f"Assess flood risk and building exposure for location: {location}"

    response = _flood_assessment_agent(prompt)
    return str(response)


@tool
def scan_region_agent_tool(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    grid_size_km: float = 2.0
) -> str:
    """
    Delegates to the flood assessment agent to scan a region for flood-affected points.

    Args:
        min_lat: southern boundary latitude
        min_lon: western boundary longitude
        max_lat: northern boundary latitude
        max_lon: eastern boundary longitude
        grid_size_km: spacing between grid points in km (default 2.0)

    Returns: agent's assessment of which points in the region are flooded
    """
    print(f"\n[SUB-AGENT CALLED] flood_assessment_agent for region scan")
    prompt = (
        f"Scan the region from ({min_lat},{min_lon}) to ({max_lat},{max_lon}) "
        f"with grid spacing of {grid_size_km}km. "
        f"Call scan_region with these parameters and summarize which areas are flood-affected."
    )
    response = _flood_assessment_agent(prompt)
    return str(response)
