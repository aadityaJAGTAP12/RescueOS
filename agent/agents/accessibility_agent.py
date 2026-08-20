"""
Accessibility Agent: a Strands Agent that reasons about medical/road accessibility.

This agent:
- Has access to medical_accessibility tool
- Uses LLM reasoning to call the tool for a given location
- Reasons about accessibility challenges and implications
- Is exposed as a @tool (agents-as-tools pattern) so Coordinator can call it
"""

from strands import Agent, tool
from agent.config import model
from agent.tools.accessibility_tool import get_medical_accessibility


# Create the internal agent with access to accessibility tool
_accessibility_agent = Agent(
    model=model,
    tools=[get_medical_accessibility],
    system_prompt=(
        "You are a disaster-response analyst specializing in accessibility and logistics assessment. "
        "For a given location, you MUST call the get_medical_accessibility tool. "
        "Call it EXACTLY ONCE. Do not guess or infer values the tool would provide. "
        "After calling the tool, reason about the medical facility distance and "
        "accessibility challenges. Summarize the findings clearly, citing the "
        "specific facility name and distance returned by the tool. "
        "If the tool returns an error or unavailable data, state that explicitly."
    ),
)


@tool
def accessibility_agent_tool(location: str) -> str:
    """
    Delegates to the accessibility agent, which reasons about medical
    facility accessibility and logistics for a location using its own tools.

    Args:
        location: name of location (must be in KNOWN_LOCATIONS)

    Returns: agent's assessment of medical accessibility
    """
    print(f"\n[SUB-AGENT CALLED] accessibility_agent for '{location}'")
    response = _accessibility_agent(
        f"Assess medical facility accessibility and logistics challenges for location: {location}"
    )
    return str(response)
