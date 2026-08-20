"""
Main entry point for ReliefOS multi-agent architecture.

Demonstrates:
1. Multi-location ranking by priority
2. Resource allocation based on priority
3. Multi-agent reasoning via Coordinator (optional conversational mode)

This output MUST match spike.py exactly to confirm the restructuring was successful.
"""

import sys
import os

# Add parent directory to path so we can import agent module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.config import KNOWN_LOCATIONS
from agent.tools.allocation_tool import rank_locations, allocate_resources
from agent.agents.coordinator_agent import coordinator_agent_tool


def main():
    """Main demo: rank all known locations and allocate resources."""
    
    print("\n" + "="*70)
    print("RANKING ALL KNOWN LOCATIONS BY PRIORITY...")
    print("="*70)
    
    all_locations = list(KNOWN_LOCATIONS.keys())
    ranked = rank_locations(all_locations)
    
    print("\n--- RANKED SUMMARY ---")
    for i, r in enumerate(ranked, start=1):
        print(f"#{i}: {r['location']} — PDC {r['pdc_score']} — {r['category']}")
    
    # Example: NGO has 2 boats, 1 medical team, 5000kg food to allocate
    available_resources = {
        "boats": 2,
        "medical_teams": 1,
        "food_kg": 5000,
    }
    
    allocation_plan = allocate_resources(ranked, available_resources)
    print(allocation_plan)


def demo_coordinator_reasoning(location: str):
    """
    (Optional) Run the Coordinator agent for a single location to see
    multi-agent reasoning in action. This output is NOT used for validation
    (validation is done via ranking/allocation above), but shows how the
    multi-agent orchestration works.
    
    Args:
        location: name of location to assess
    """
    print(f"\n\n[COORDINATOR DEMO] Multi-agent reasoning for '{location}'")
    print("=" * 70)
    
    coordinator_response = coordinator_agent_tool(location)
    
    print("\n[COORDINATOR RESPONSE]")
    print(coordinator_response)
    print("=" * 70)


if __name__ == "__main__":
    # Main demo: ranking and allocation (must match spike.py exactly)
    main()
    
    # Optional: show multi-agent reasoning for one location
    # Uncomment to see the Coordinator in action (requires Ollama llama3.2)
    # demo_coordinator_reasoning("sivasagar_flood_zone")
