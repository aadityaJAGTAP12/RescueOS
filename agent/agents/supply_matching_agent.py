"""
Supply Matching Agent: matches community-reported needs to supply recommendations.

This agent:
- Has access to get_reports_near and match_supplies tools
- Uses LLM reasoning to retrieve community reports and recommend supplies
- Always flags self-reported data as unverified
- Is exposed as a @tool (agents-as-tools pattern) so Coordinator can call it
"""

from strands import Agent, tool
from agent.config import model
from agent.community_reports import get_reports_near


@tool
def get_reports_near_tool(lat: float, lon: float, radius_km: float = 3.0) -> str:
    """
    Retrieve self-reported community needs near a location.

    Args:
        lat: center latitude
        lon: center longitude
        radius_km: search radius in km (default 3.0)

    Returns: formatted list of nearby community reports
    """
    reports = get_reports_near(lat, lon, radius_km)

    if not reports:
        return (
            f"No community reports found within {radius_km}km of ({lat:.4f}, {lon:.4f}). "
            f"This does NOT mean there are no people in need — it means no self-reported "
            f"data exists for this location."
        )

    lines = [f"Found {len(reports)} community report(s) within {radius_km}km:"]
    for r in reports:
        lines.append(
            f"  - Report {r['id']}: {r['people_count']} people "
            f"({r.get('children', 0)} children, {r.get('elderly', 0)} elderly) "
            f"at ({r['lat']:.4f}, {r['lon']:.4f}), ~{r['distance_km']}km away. "
            f"Needs: {', '.join(r['needs']) if r['needs'] else 'none specified'}. "
            f"Note: {r.get('note', 'none')}"
        )
    lines.append(
        "IMPORTANT: This is self-reported, unverified data. "
        "Treat with lower confidence than satellite-derived data."
    )
    return "\n".join(lines)


@tool
def match_supplies(
    total_people: int,
    children_count: int,
    elderly_count: int,
    needs_reported: list[str]
) -> dict:
    """
    Deterministic rule-based supply recommendation based on aggregated
    reported needs. This is a deterministic function, NOT computed by the LLM.

    Args:
        total_people: total number of people
        children_count: number of children
        elderly_count: number of elderly
        needs_reported: list of need categories reported

    Returns:
        {
            "recommended_supplies": list of str,
            "reasoning": str
        }
    """
    recommended = []
    reasoning_parts = []

    # Base supplies for any reported need
    recommended.append("emergency_kits")
    reasoning_parts.append("Emergency kits for all affected individuals")

    # Children-specific supplies
    if children_count > 0:
        recommended.append("baby_food")
        recommended.append("child_appropriate_food")
        recommended.append("diapers")
        reasoning_parts.append(
            f"Child-specific supplies: {children_count} children identified — "
            f"baby food, child-appropriate food, and diapers recommended"
        )

    # Elderly-specific supplies
    if elderly_count > 0:
        recommended.append("mobility_assistance")
        recommended.append("accessible_transport_priority")
        reasoning_parts.append(
            f"Elderly-specific supplies: {elderly_count} elderly identified — "
            f"mobility assistance and accessible transport priority recommended"
        )

    # Need-based supplies
    if "medical" in needs_reported:
        recommended.append("medical_kits")
        reasoning_parts.append("Medical kits requested (specific medical needs)")

    if "food" in needs_reported:
        recommended.append("food_rations")
        reasoning_parts.append("Food rations requested")

    if "water" in needs_reported:
        recommended.append("water_purification")
        recommended.append("clean_water_containers")
        reasoning_parts.append("Clean water and purification supplies requested")

    if "sanitary_supplies" in needs_reported:
        recommended.append("sanitary_kits")
        reasoning_parts.append("Sanitary kits requested")

    if "infant_care" in needs_reported:
        recommended.append("infant_formula")
        recommended.append("baby_blankets")
        reasoning_parts.append("Infant care supplies requested")

    if "shelter" in needs_reported:
        recommended.append("tarpaulins")
        recommended.append("blankets")
        reasoning_parts.append("Shelter materials requested")

    if "transport" in needs_reported:
        recommended.append("boat_priority")
        reasoning_parts.append("Transport assistance requested — boat priority")

    # Remove duplicates while preserving order
    seen = set()
    unique_recommended = []
    for s in recommended:
        if s not in seen:
            seen.add(s)
            unique_recommended.append(s)

    return {
        "recommended_supplies": unique_recommended,
        "reasoning": "; ".join(reasoning_parts) if reasoning_parts else "No specific needs reported"
    }


# Create the supply matching agent
_supply_matching_agent = Agent(
    model=model,
    tools=[get_reports_near_tool, match_supplies],
    system_prompt=(
        "You are a supply matching specialist for disaster response. "
        "Given a location, you MUST:\n"
        "1. Call get_reports_near_tool to retrieve self-reported community needs.\n"
        "2. If reports exist, call match_supplies with the aggregated needs data.\n"
        "3. If no reports exist, say so clearly rather than guessing.\n\n"
        "CRITICAL: This data is self-reported and unverified — ALWAYS state this "
        "explicitly. Do not treat it with the same confidence as satellite-derived data. "
        "Cite specific report details when making recommendations."
    ),
)


@tool
def supply_matching_agent_tool(lat: float, lon: float) -> str:
    """
    Delegates to the supply matching agent, which retrieves community reports
    and recommends supplies based on reported needs.

    Args:
        lat: latitude of the location to check
        lon: longitude of the location to check

    Returns: agent's supply matching recommendation
    """
    print(f"\n[SUB-AGENT CALLED] supply_matching_agent for ({lat:.4f}, {lon:.4f})")
    prompt = (
        f"Check for community reports near coordinates: lat={lat}, lon={lon}\n"
        f"Retrieve any reports, then recommend supplies based on the reported needs."
    )
    response = _supply_matching_agent(prompt)
    return str(response)
