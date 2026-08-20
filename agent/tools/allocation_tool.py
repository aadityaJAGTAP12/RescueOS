"""
Allocation tools: priority scoring, ranking, and resource allocation.

Extracted from assess_disaster_priority Step 4 and the standalone
rank_locations / allocate_resources functions.

This module contains:
1. calculate_priority() - the v2 recalibrated scoring formula
2. rank_locations() - ranking logic for multiple locations
3. allocate_resources() - greedy resource allocation
"""

import re
from strands import tool
from agent.tools.flood_tool import get_flood_status
from agent.tools.exposure_tool import get_building_exposure
from agent.tools.accessibility_tool import get_medical_accessibility


@tool
def calculate_priority(
    flood_detected: bool,
    exposure_ratio: float,
    nearest_flood_polygon_km2: float,
    medical_distance_km: float,
    data_confidence: str
) -> dict:
    """
    Compute priority score using v2 recalibrated scoring formula.
    
    Returns:
        {
            "pdc_score": float (0.0-1.0),
            "category": str ("NONE", "SAFE", "EXPOSED", "PRIORITY", "HIGH PRIORITY"),
            "recommendation": str
        }
    
    RECALIBRATED (v2) SCORING RATIONALE:
    ====================================
    Testing against 3 real coordinates showed that even a point INSIDE a 
    4.88 sq km flood polygon only produced ~6% building exposure. This is 
    consistent for rural Upper Assam — flood-prone land near rivers is 
    disproportionately farmland, not settlement.
    
    Original scoring (exposure_ratio * 1.5) assumed urban-like building 
    densities and under-scored genuinely flooded rural locations.
    
    Fix: exposure_ratio is now weighted alongside flood_polygon_size 
    (nearest_flood_polygon_km2), not treated as the dominant signal.
    A location inside/near a large flood area is meaningfully at risk 
    regardless of exact building density (roads, farmland, access routes 
    all matter too, not just structure count).
    
    Weights: 35% exposure, 35% flood scale, 30% accessibility
    """
    
    if not flood_detected:
        return {
            "pdc_score": 0.0,
            "category": "NONE",
            "recommendation": "No immediate medical team deployment required at this time."
        }
    
    # Use actual data, with 0.5 (medium) as unknown placeholder
    exp_ratio = exposure_ratio if exposure_ratio >= 0 else 0.5
    med_dist = medical_distance_km
    
    # Compute normalized scores
    exposure_score = min(exp_ratio * 6.0, 1.0)
    flood_scale_score = min(nearest_flood_polygon_km2 / 5.0, 1.0)
    
    if med_dist < 0:
        accessibility_score = 0.5
    elif med_dist > 15:
        accessibility_score = 1.0
    elif med_dist > 5:
        accessibility_score = 0.66
    else:
        accessibility_score = 0.33
    
    # Apply weights: 35% + 35% + 30%
    pdc_score = round(
        (exposure_score * 0.35) + (flood_scale_score * 0.35) + (accessibility_score * 0.30),
        2,
    )
    
    # Categorize
    if pdc_score >= 0.75:
        category = "HIGH PRIORITY"
        recommendation = "URGENT: Deploy medical team immediately with self-sufficiency supplies."
    elif pdc_score >= 0.5:
        category = "PRIORITY"
        recommendation = "Deploy medical team soon; coordinate with local authorities for access."
    elif pdc_score >= 0.25:
        category = "EXPOSED"
        recommendation = "Prepare medical response; monitor situation for escalation."
    else:
        category = "SAFE"
        recommendation = "No immediate medical team deployment required at this time."
    
    return {
        "pdc_score": pdc_score,
        "category": category,
        "recommendation": recommendation
    }


def _extract_pdc_score(assessment_text: str) -> float:
    """Pull the numeric PDC score out of assessment text."""
    match = re.search(r"PDC SCORE:\s+([\d.]+)", assessment_text)
    return float(match.group(1)) if match else 0.0


def _extract_category(assessment_text: str) -> str:
    """Pull the priority category out of assessment text."""
    match = re.search(r"PRIORITY CATEGORY:\s*([^\r\n]+)", assessment_text)
    return match.group(1).strip() if match else "UNKNOWN"


def rank_locations(locations: list[str]) -> list[dict]:
    """
    Assess and rank multiple locations by priority (highest first).
    
    Calls get_flood_status, get_building_exposure, get_medical_accessibility
    for each location, then compute_priority to get PDC scores.
    
    Returns:
        [
            {
                "location": str,
                "pdc_score": float,
                "category": str,
                "flood_status": dict,
                "exposure": dict,
                "accessibility": dict,
                "priority": dict
            },
            ...
        ]
    """
    results = []
    
    for loc in locations:
        # Gather data via tools
        flood_status = get_flood_status(loc)
        exposure = get_building_exposure(loc)
        accessibility = get_medical_accessibility(loc)
        
        # Compute priority
        priority = calculate_priority(
            flood_detected=flood_status["flooded"],
            exposure_ratio=exposure["exposure_ratio"],
            nearest_flood_polygon_km2=flood_status["nearest_flood_polygon_km2"],
            medical_distance_km=accessibility["medical_distance_km"],
            data_confidence="High" if exposure["data_available"] and accessibility["data_available"] else "Medium"
        )
        
        results.append({
            "location": loc,
            "pdc_score": priority["pdc_score"],
            "category": priority["category"],
            "flood_status": flood_status,
            "exposure": exposure,
            "accessibility": accessibility,
            "priority": priority
        })
    
    # Sort by PDC score descending
    results.sort(key=lambda r: r["pdc_score"], reverse=True)
    return results


def allocate_resources(ranked_locations: list[dict], resources: dict) -> str:
    """
    Greedy allocation: highest-priority location gets resources first,
    until each resource type runs out.
    
    This is a deterministic heuristic, not an optimizer — an honest MVP
    simplification documented in the architecture doc.
    
    Args:
        ranked_locations: output from rank_locations()
        resources: {"boats": int, "medical_teams": int, "food_kg": int}
    
    Returns: formatted allocation plan as string
    """
    remaining = dict(resources)
    allocation_log = []
    
    output_lines = []
    output_lines.append("\n" + "=" * 70)
    output_lines.append("RESOURCE ALLOCATION PLAN")
    output_lines.append("=" * 70)
    output_lines.append(f"Available resources: {resources}\n")
    
    for rank, loc_data in enumerate(ranked_locations, start=1):
        loc = loc_data["location"]
        score = loc_data["pdc_score"]
        category = loc_data["category"]
        
        if category.strip().upper() in ("NONE", "SAFE"):
            output_lines.append(
                f"#{rank} {loc.upper()} — PDC {score}, {category} — "
                f"no resources allocated (not flood-affected / low risk)."
            )
            continue
        
        assigned = {}
        for resource_name, amount_needed in [("boats", 1), ("medical_teams", 1), ("food_kg", 1000)]:
            available = remaining.get(resource_name, 0)
            if available <= 0:
                continue
            give = min(amount_needed, available)
            assigned[resource_name] = give
            remaining[resource_name] = available - give
        
        if assigned:
            output_lines.append(
                f"#{rank} {loc.upper()} — PDC {score}, {category} — "
                f"ALLOCATED: {assigned}"
            )
            allocation_log.append({"location": loc, "assigned": assigned})
        else:
            output_lines.append(
                f"#{rank} {loc.upper()} — PDC {score}, {category} — "
                f"NEEDS RESOURCES but none remaining (exhausted by higher-priority areas)."
            )
    
    output_lines.append(f"\nRemaining unallocated resources: {remaining}")
    output_lines.append("=" * 70)
    
    return "\n".join(output_lines)
