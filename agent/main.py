"""
Main entry point for ReliefOS multi-agent architecture.

Demonstrates:
1. Multi-location ranking by priority (deterministic — existing path)
2. Single-location assessment via run_relief_assessment() (deterministic)
3. LLM-enhanced assessment via run_relief_assessment(use_llm=True) (optional)

This output MUST match spike.py exactly to confirm the restructuring was successful.
"""

import sys
import os

# Add parent directory to path so we can import agent module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.config import KNOWN_LOCATIONS
from agent.tools.allocation_tool import rank_locations, allocate_resources
from agent.assessment import run_relief_assessment


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


def demo_assessment():
    """
    Demonstrate the new run_relief_assessment() entry point.
    This is the deterministic path — no Ollama needed.
    """
    print("\n" + "="*70)
    print("SINGLE-LOCATION ASSESSMENT (deterministic)")
    print("="*70)

    result = run_relief_assessment("sivasagar_flood_zone")

    print(f"\nLocation: {result['location']}")
    print(f"Coordinates: {result['coordinates']}")
    print(f"Data Confidence: {result['data_confidence']}")
    print(f"\nFlood Evidence:")
    print(f"  Flooded: {result['evidence']['flood']['flooded']}")
    print(f"  Exactly contained: {result['evidence']['flood']['exactly_contained']}")
    print(f"  Nearest polygon: {result['evidence']['flood']['nearest_flood_polygon_km2']:.2f} sq km")
    print(f"\nExposure Evidence:")
    print(f"  Buildings: {result['evidence']['exposure']['total_buildings']}")
    print(f"  Exposed: {result['evidence']['exposure']['exposed_count']}")
    print(f"  Ratio: {result['evidence']['exposure']['exposure_ratio']:.2%}")
    print(f"\nAccessibility Evidence:")
    print(f"  Medical distance: {result['evidence']['accessibility']['medical_distance_km']:.1f} km")
    print(f"  Facility: {result['evidence']['accessibility']['medical_facility_name']}")
    print(f"\nPriority (deterministic PDC):")
    print(f"  Score: {result['priority']['pdc_score']}")
    print(f"  Category: {result['priority']['category']}")
    print(f"  Recommendation: {result['priority']['recommendation']}")
    print(f"\nLLM Synthesis: {result['llm_synthesis']}")
    print("="*70)


def demo_llm_assessment():
    """
    Demonstrate LLM-enhanced assessment.
    Requires Ollama llama3.2 running locally.
    """
    print("\n" + "="*70)
    print("SINGLE-LOCATION ASSESSMENT (LLM-enhanced)")
    print("="*70)

    result = run_relief_assessment("sivasagar_flood_zone", use_llm=True)

    print(f"\nLocation: {result['location']}")
    print(f"Priority (deterministic PDC):")
    print(f"  Score: {result['priority']['pdc_score']}")
    print(f"  Category: {result['priority']['category']}")
    print(f"\nLLM Synthesis:")
    print(result['llm_synthesis'])
    print("="*70)


if __name__ == "__main__":
    # Main demo: ranking and allocation (must match spike.py exactly)
    main()

    # New: single-location assessment (deterministic, no Ollama)
    demo_assessment()

    # Optional: LLM-enhanced assessment (requires Ollama llama3.2)
    # Uncomment to see the Coordinator in action:
    # demo_llm_assessment()
