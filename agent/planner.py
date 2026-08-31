"""
ReliefOS Operational Planner / Query Orchestrator

Dynamically selects and combines existing ReliefOS capabilities to answer
natural language disaster-response questions.

Architecture:
    User Query (string)
        ↓
    parse_operational_query()  [existing - LLM-assisted]
        ↓
    PlannerOrchestrator.plan()
        ↓
    Capability selection (deterministic, based on parsed intent)
        ↓
    Tool execution (using existing tools)
        ↓
    Evidence aggregation
        ↓
    Recommendation synthesis
        ↓
    Structured result with full evidence trail

Key design principles:
- District-agnostic: reasons from database state, not hardcoded names
- Reuses existing tools: never reimplements flood/exposure/routing
- Evidence-based: every recommendation exposes why it was produced
- Human-in-the-loop: advisory, never autonomous command
- Honest about uncertainty and data gaps
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Planning Contract — structured internal representation
# ---------------------------------------------------------------------------

@dataclass
class PlanningRequest:
    """Structured representation of what the user wants to accomplish.

    Extracted from the raw query by the query parser, then enriched
    by the planner with resolved locations and resource constraints.
    """
    raw_query: str
    intent: str  # "assessment" | "allocation" | "general"
    locations: list[str] = field(default_factory=list)
    district_scope: list[str] = field(default_factory=list)
    resources: dict = field(default_factory=dict)  # e.g. {"boats": 3, "medical_teams": 2}
    resource_phrases: list[dict] = field(default_factory=list)  # raw resource mentions
    requested_capabilities: dict = field(default_factory=dict)
    prioritization_criteria: list[str] = field(default_factory=list)
    parse_confidence: str = "low"
    clarification_needed: list[dict] = field(default_factory=list)


@dataclass
class PlanningResult:
    """Structured output from the planner.

    Contains the recommendation, supporting evidence, constraints,
    uncertainty, and data gaps — everything a human coordinator needs
    to make an informed decision.
    """
    raw_query: str
    recommendation: str
    why: str
    evidence: dict = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    ranked_locations: list[dict] = field(default_factory=list)
    allocation_plan: str | None = None
    routing_info: dict | None = None
    clarification_needed: list[dict] = field(default_factory=list)
    parse_confidence: str = "low"


# ---------------------------------------------------------------------------
# Capability registry — maps intent + capabilities to tool calls
# ---------------------------------------------------------------------------

# Which tools are needed for each capability
CAPABILITY_TOOLS = {
    "flood_intelligence": ["get_flood_status"],
    "exposure_analysis": ["get_building_exposure"],
    "accessibility_check": ["get_medical_accessibility"],
    "road_status": ["get_road_status"],
    "priority_ranking": ["get_flood_status", "get_building_exposure", "get_medical_accessibility", "calculate_priority"],
    "resource_allocation": ["rank_locations", "allocate_resources"],
    "route_optimization": ["get_route"],
    "field_intelligence": ["get_field_reports"],
    "cross_district_comparison": ["list_flood_snapshots", "list_settlements"],
}


# ---------------------------------------------------------------------------
# Planner Orchestrator
# ---------------------------------------------------------------------------

class PlannerOrchestrator:
    """Generalized operational planner that dynamically selects and
    combines existing ReliefOS tools to answer disaster-response queries.

    The planner does NOT contain district-specific scenario branches.
    It reasons from database state and query constraints.
    """

    def __init__(self, repository=None, get_flood_status=None, get_building_exposure=None, get_medical_accessibility=None):
        """Initialize with an optional repository reference.

        Args:
            repository: DataRepository instance (uses get_repository() if None)
            get_flood_status: optional override for flood status tool (for testing)
            get_building_exposure: optional override for exposure tool (for testing)
            get_medical_accessibility: optional override for accessibility tool (for testing)
        """
        if repository is None:
            from agent.data.repository import get_repository
            self._repo = get_repository()
        else:
            self._repo = repository
        self._get_flood_status = get_flood_status
        self._get_building_exposure = get_building_exposure
        self._get_medical_accessibility = get_medical_accessibility

    def plan(self, raw_query: str, parsed_query: dict | None = None) -> PlanningResult:
        """Main entry point: take a raw query and produce a plan.

        Args:
            raw_query: the coordinator's natural language query
            parsed_query: optional pre-parsed query dict (from parse_operational_query)

        Returns:
            PlanningResult with recommendation, evidence, and supporting info
        """
        t_start = time.time()

        # Step 1: Parse query if not already parsed
        if parsed_query is None:
            from agent.tools.query_parser_tool import parse_operational_query
            parsed_query = parse_operational_query(raw_query)

        # Step 2: Build structured planning request
        request = self._build_planning_request(raw_query, parsed_query)

        # Step 3: Determine required capabilities
        capabilities = self._select_capabilities(request)

        # Step 4: Resolve locations from database
        resolved_locations = self._resolve_locations(request)

        # Step 5: Execute tools based on capabilities
        evidence = self._execute_tools(request, capabilities, resolved_locations)

        # Step 6: Rank locations if needed
        ranked = []
        if request.requested_capabilities.get("priority_ranking") or request.intent == "allocation":
            ranked = self._rank_locations(resolved_locations, evidence)

        # Step 7: Allocate resources if needed
        allocation_plan = None
        if request.requested_capabilities.get("resource_allocation") and request.resources:
            allocation_plan = self._allocate_resources(ranked, request.resources)

        # Step 8: Synthesize recommendation
        result = self._synthesize(
            request=request,
            capabilities=capabilities,
            resolved_locations=resolved_locations,
            evidence=evidence,
            ranked_locations=ranked,
            allocation_plan=allocation_plan,
        )

        t_end = time.time()
        result.evidence["planning_time_ms"] = round((t_end - t_start) * 1000, 1)

        return result

    # -------------------------------------------------------------------
    # Step 2: Build planning request from parsed query
    # -------------------------------------------------------------------

    def _build_planning_request(self, raw_query: str, parsed: dict) -> PlanningRequest:
        """Convert parsed query dict into a structured PlanningRequest."""

        # Extract resource constraints
        resources = {}
        resource_phrases = parsed.get("resources_mentioned", [])
        for r in resource_phrases:
            rtype = r.get("resource_type", "other")
            qty = r.get("quantity_numeric")
            if qty is not None:
                # Map resource types to canonical constraint keys
                key = _resource_type_to_constraint_key(rtype, r.get("unit", ""))
                if key:
                    resources[key] = qty

        # Determine district scope from resolved locations
        district_scope = self._infer_district_scope(parsed.get("locations_mentioned", []))

        return PlanningRequest(
            raw_query=raw_query,
            intent=parsed.get("intent", "general"),
            locations=parsed.get("locations_mentioned", []),
            district_scope=district_scope,
            resources=resources,
            resource_phrases=resource_phrases,
            requested_capabilities=parsed.get("requested_capabilities", {}),
            prioritization_criteria=parsed.get("prioritization_criteria", []),
            parse_confidence=parsed.get("parse_confidence", "low"),
            clarification_needed=parsed.get("clarification_needed", []),
        )

    def _infer_district_scope(self, locations_mentioned: list[str]) -> list[str]:
        """Infer district scope from location mentions.

        Uses the repository to check if any mentioned locations resolve
        to specific districts. If no specific locations mentioned,
        returns all districts (regional query).
        """
        if not locations_mentioned:
            # No specific locations — regional query
            districts = self._repo.list_districts()
            return [d.id for d in districts]

        # Try to resolve each mentioned location to a district
        district_ids = set()
        for loc_text in locations_mentioned:
            settlement = self._repo.resolve_location(name=loc_text)
            if settlement:
                district_ids.add(settlement.district_id)

        if district_ids:
            return list(district_ids)

        # Couldn't resolve any — default to all districts
        districts = self._repo.list_districts()
        return [d.id for d in districts]

    # -------------------------------------------------------------------
    # Step 3: Capability selection
    # -------------------------------------------------------------------

    def _select_capabilities(self, request: PlanningRequest) -> list[str]:
        """Deterministically select which capabilities are needed.

        Based on:
        - User's requested capabilities (from query parser)
        - Intent (assessment vs allocation vs general)
        - Resource constraints (if resources mentioned, need allocation)
        """
        caps = []

        if request.intent == "assessment":
            caps.extend(["flood_intelligence", "exposure_analysis", "accessibility_check"])

        if request.intent == "allocation":
            caps.extend(["flood_intelligence", "exposure_analysis", "accessibility_check", "priority_ranking", "resource_allocation"])

        # Add explicitly requested capabilities
        for cap_name, requested in request.requested_capabilities.items():
            if requested and cap_name not in caps:
                # Map capability names
                if cap_name == "priority_ranking" and "priority_ranking" not in caps:
                    caps.append("priority_ranking")
                elif cap_name == "resource_allocation" and "resource_allocation" not in caps:
                    caps.append("resource_allocation")
                elif cap_name == "route_optimization":
                    caps.append("route_optimization")

        # General queries still get basic flood intelligence
        if request.intent == "general" and not caps:
            caps.append("flood_intelligence")

        # Always include cross-district comparison and field intelligence
        # for awareness — fundamental to any operational assessment
        if "cross_district_comparison" not in caps:
            caps.append("cross_district_comparison")
        if "field_intelligence" not in caps:
            caps.append("field_intelligence")

        return caps

    # -------------------------------------------------------------------
    # Step 4: Location resolution
    # -------------------------------------------------------------------

    def _resolve_locations(self, request: PlanningRequest) -> list[dict]:
        """Resolve mentioned locations to coordinates using the repository.

        Returns list of {name, lat, lon, district_id, settlement_id}.
        If no specific locations mentioned, uses settlement centroids
        from all districts in scope.
        """
        resolved = []

        if request.locations:
            for loc_text in request.locations:
                settlement = self._repo.resolve_location(name=loc_text)
                if settlement:
                    resolved.append({
                        "name": settlement.name,
                        "lat": settlement.lat,
                        "lon": settlement.lon,
                        "district_id": settlement.district_id,
                        "settlement_id": settlement.id,
                    })
                else:
                    # Try as district name
                    district = self._repo.get_district(loc_text.lower().replace(" ", "_"))
                    if district:
                        # Use district centroid (approximate)
                        from shapely import wkt
                        geom = wkt.loads(district.geometry_wkt)
                        centroid = geom.centroid
                        resolved.append({
                            "name": district.name,
                            "lat": centroid.y,
                            "lon": centroid.x,
                            "district_id": district.id,
                            "settlement_id": None,
                        })

        # If no locations resolved, use all settlements in scope
        if not resolved:
            for district_id in request.district_scope:
                settlements = self._repo.list_settlements(district_id=district_id)
                for s in settlements[:3]:  # Limit to top 3 per district for performance
                    resolved.append({
                        "name": s.name,
                        "lat": s.lat,
                        "lon": s.lon,
                        "district_id": s.district_id,
                        "settlement_id": s.id,
                    })

        return resolved

    # -------------------------------------------------------------------
    # Step 5: Tool execution
    # -------------------------------------------------------------------

    def _execute_tools(
        self,
        request: PlanningRequest,
        capabilities: list[str],
        resolved_locations: list[dict],
    ) -> dict:
        """Execute the appropriate tools based on selected capabilities.

        Returns aggregated evidence dict keyed by tool/capability name.
        """
        # Use injected tools if provided, otherwise import from modules
        if self._get_flood_status is not None:
            _get_flood_status = self._get_flood_status
        else:
            from agent.tools import flood_tool
            _get_flood_status = flood_tool.get_flood_status

        if self._get_building_exposure is not None:
            _get_building_exposure = self._get_building_exposure
        else:
            from agent.tools import exposure_tool
            _get_building_exposure = exposure_tool.get_building_exposure

        if self._get_medical_accessibility is not None:
            _get_medical_accessibility = self._get_medical_accessibility
        else:
            from agent.tools import accessibility_tool
            _get_medical_accessibility = accessibility_tool.get_medical_accessibility

        evidence = {
            "flood": {},
            "exposure": {},
            "accessibility": {},
            "priority": {},
            "field_reports": {},
            "flood_snapshots": {},
        }

        tools_used = []

        for loc in resolved_locations:
            loc_key = loc["name"]

            # Flood intelligence
            if "flood_intelligence" in capabilities or "priority_ranking" in capabilities:
                try:
                    flood = _get_flood_status(location=loc_key, lat=loc["lat"], lon=loc["lon"])
                    evidence["flood"][loc_key] = flood
                    tools_used.append("get_flood_status")
                except Exception as e:
                    evidence["flood"][loc_key] = {"error": str(e)}

            # Exposure analysis
            if "exposure_analysis" in capabilities or "priority_ranking" in capabilities:
                try:
                    exposure = _get_building_exposure(location=loc_key, lat=loc["lat"], lon=loc["lon"])
                    evidence["exposure"][loc_key] = exposure
                    tools_used.append("get_building_exposure")
                except Exception as e:
                    evidence["exposure"][loc_key] = {"error": str(e)}

            # Accessibility check
            if "accessibility_check" in capabilities or "priority_ranking" in capabilities:
                try:
                    access = _get_medical_accessibility(location=loc_key, lat=loc["lat"], lon=loc["lon"])
                    evidence["accessibility"][loc_key] = access
                    tools_used.append("get_medical_accessibility")
                except Exception as e:
                    evidence["accessibility"][loc_key] = {"error": str(e)}

        # Cross-district comparison: get flood snapshot summaries
        if "cross_district_comparison" in capabilities:
            for district_id in request.district_scope:
                try:
                    snapshots = self._repo.list_flood_snapshots(district_id=district_id)
                    evidence["flood_snapshots"][district_id] = [
                        {
                            "id": s.id,
                            "observed_at": s.observed_at.isoformat() if s.observed_at else None,
                            "polygon_count": s.polygon_count,
                            "source": s.source,
                            "provenance": s.provenance.value,
                        }
                        for s in snapshots
                    ]
                    tools_used.append("list_flood_snapshots")
                except Exception as e:
                    evidence["flood_snapshots"][district_id] = {"error": str(e)}

        # Field intelligence: check for recent field reports
        if "field_intelligence" in capabilities:
            for district_id in request.district_scope:
                try:
                    reports = self._repo.list_field_reports(district_id=district_id)
                    evidence["field_reports"][district_id] = [
                        {
                            "id": r.id,
                            "source_type": r.source_type,
                            "people_count": r.people_count,
                            "needs": r.needs,
                            "observed_at": (r.observed_at.isoformat() if hasattr(r.observed_at, 'isoformat') else str(r.observed_at)) if r.observed_at else None,
                        }
                        for r in reports
                    ]
                    tools_used.append("list_field_reports")
                except Exception as e:
                    evidence["field_reports"][district_id] = {"error": str(e)}

        evidence["tools_used"] = list(set(tools_used))
        return evidence

    # -------------------------------------------------------------------
    # Step 6: Location ranking
    # -------------------------------------------------------------------

    def _rank_locations(
        self,
        resolved_locations: list[dict],
        evidence: dict,
    ) -> list[dict]:
        """Rank locations by priority using existing PDC scoring.

        Uses flood status, exposure, and accessibility evidence
        to compute priority scores for each location.
        """
        from agent.tools.allocation_tool import calculate_priority

        ranked = []

        for loc in resolved_locations:
            loc_key = loc["name"]

            flood_data = evidence.get("flood", {}).get(loc_key, {})
            exposure_data = evidence.get("exposure", {}).get(loc_key, {})
            access_data = evidence.get("accessibility", {}).get(loc_key, {})

            # Skip locations with errors
            if "error" in flood_data:
                continue

            flood_detected = flood_data.get("flooded", False)
            exposure_ratio = exposure_data.get("exposure_ratio", 0.0)
            nearest_flood_km2 = flood_data.get("nearest_flood_polygon_km2", 0.0)
            medical_dist = access_data.get("medical_distance_km", -1)

            # Determine data confidence
            data_conf = "High" if (
                exposure_data.get("data_available", False) and
                access_data.get("data_available", False)
            ) else "Medium"

            priority = calculate_priority(
                flood_detected=flood_detected,
                exposure_ratio=exposure_ratio,
                nearest_flood_polygon_km2=nearest_flood_km2,
                medical_distance_km=medical_dist,
                data_confidence=data_conf,
            )

            ranked.append({
                "location": loc_key,
                "lat": loc["lat"],
                "lon": loc["lon"],
                "district_id": loc["district_id"],
                "pdc_score": priority["pdc_score"],
                "category": priority["category"],
                "recommendation": priority["recommendation"],
                "flood_status": flood_data,
                "exposure": exposure_data,
                "accessibility": access_data,
            })

        # Sort by PDC score descending
        ranked.sort(key=lambda r: r["pdc_score"], reverse=True)
        return ranked

    # -------------------------------------------------------------------
    # Step 7: Resource allocation
    # -------------------------------------------------------------------

    def _allocate_resources(
        self,
        ranked_locations: list[dict],
        resources: dict,
    ) -> str:
        """Allocate resources to ranked locations using greedy heuristic.

        Uses the existing allocate_resources() from allocation_tool.
        """
        from agent.tools.allocation_tool import allocate_resources

        if not ranked_locations or not resources:
            return "No allocation needed — no ranked locations or resources."

        return allocate_resources(ranked_locations, resources)

    # -------------------------------------------------------------------
    # Step 8: Recommendation synthesis
    # -------------------------------------------------------------------

    def _synthesize(
        self,
        request: PlanningRequest,
        capabilities: list[str],
        resolved_locations: list[dict],
        evidence: dict,
        ranked_locations: list[dict],
        allocation_plan: str | None,
    ) -> PlanningResult:
        """Synthesize a human-readable recommendation from evidence.

        Follows the structured output format:
        RECOMMENDATION / WHY / EVIDENCE / CONSTRAINTS / UNCERTAINTY / DATA GAPS
        """
        # Build recommendation based on intent and evidence
        if request.intent == "allocation" and ranked_locations:
            recommendation = self._build_allocation_recommendation(ranked_locations, request, allocation_plan)
            why = self._build_allocation_reasoning(ranked_locations, evidence)
        elif request.intent == "assessment" and ranked_locations:
            recommendation = self._build_assessment_recommendation(ranked_locations, request)
            why = self._build_assessment_reasoning(ranked_locations, evidence)
        else:
            recommendation = self._build_general_recommendation(request, evidence)
            why = "Based on available flood intelligence and district data."

        # Collect uncertainty
        uncertainty = self._collect_uncertainty(evidence, resolved_locations)

        # Collect data gaps
        data_gaps = self._collect_data_gaps(evidence, resolved_locations)

        # Collect constraints
        constraints = self._build_constraints(request)

        # Build evidence summary
        evidence_summary = self._build_evidence_summary(evidence, ranked_locations)

        return PlanningResult(
            raw_query=request.raw_query,
            recommendation=recommendation,
            why=why,
            evidence=evidence_summary,
            constraints=constraints,
            uncertainty=uncertainty,
            data_gaps=data_gaps,
            tools_used=evidence.get("tools_used", []),
            ranked_locations=ranked_locations,
            allocation_plan=allocation_plan,
            clarification_needed=request.clarification_needed,
            parse_confidence=request.parse_confidence,
        )

    # -------------------------------------------------------------------
    # Recommendation builders
    # -------------------------------------------------------------------

    def _build_allocation_recommendation(
        self,
        ranked: list[dict],
        request: PlanningRequest,
        allocation_plan: str | None,
    ) -> str:
        """Build recommendation for resource allocation queries."""
        affected = [r for r in ranked if r["category"] not in ("NONE", "SAFE")]

        if not affected:
            return (
                "RECOMMENDATION: No flood-affected locations identified in the "
                "queried scope. No immediate resource deployment needed."
            )

        lines = ["RECOMMENDATION:"]
        lines.append(
            f"Deploy resources to {len(affected)} flood-affected location(s), "
            f"prioritized by priority score."
        )
        lines.append("")
        lines.append("PRIORITY ORDER:")
        for i, loc in enumerate(affected[:5], 1):
            lines.append(
                f"  {i}. {loc['location']} ({loc['district_id']}) — "
                f"PDC {loc['pdc_score']}, {loc['category']}"
            )

        if allocation_plan:
            lines.append("")
            lines.append(allocation_plan)

        return "\n".join(lines)

    def _build_assessment_recommendation(
        self,
        ranked: list[dict],
        request: PlanningRequest,
    ) -> str:
        """Build recommendation for assessment queries."""
        affected = [r for r in ranked if r["category"] not in ("NONE", "SAFE")]

        if not affected:
            return (
                "RECOMMENDATION: All queried locations appear safe from immediate "
                "flood risk. Continue monitoring."
            )

        lines = ["RECOMMENDATION:"]
        highest = affected[0]
        lines.append(
            f"Highest priority: {highest['location']} ({highest['district_id']}) — "
            f"PDC {highest['pdc_score']}, {highest['category']}"
        )
        lines.append(f"{highest['recommendation']}")
        lines.append("")
        lines.append(f"Total affected locations: {len(affected)}")

        return "\n".join(lines)

    def _build_general_recommendation(
        self,
        request: PlanningRequest,
        evidence: dict,
    ) -> str:
        """Build recommendation for general informational queries."""
        # Summarize flood state across districts
        snapshots = evidence.get("flood_snapshots", {})
        if snapshots:
            lines = ["CURRENT FLOOD INTELLIGENCE SUMMARY:"]
            for district_id, snaps in sorted(snapshots.items()):
                if isinstance(snaps, list) and snaps:
                    latest = snaps[0]
                    lines.append(
                        f"  {district_id}: {latest['polygon_count']} flood polygons, "
                        f"observed {latest['observed_at']}, "
                        f"source: {latest['source']} ({latest['provenance']})"
                    )
                elif isinstance(snaps, list) and not snaps:
                    lines.append(f"  {district_id}: No flood snapshots available")
            return "\n".join(lines)

        return "RECOMMENDATION: Insufficient data to provide a specific recommendation."

    def _build_allocation_reasoning(
        self,
        ranked: list[dict],
        evidence: dict,
    ) -> str:
        """Build the WHY explanation for allocation recommendations."""
        affected = [r for r in ranked if r["category"] not in ("NONE", "SAFE")]
        if not affected:
            return "No flood-affected locations found."

        lines = ["WHY:"]
        lines.append(
            f"{len(affected)} location(s) show active flood impact based on "
            f"Sentinel-1 SAR flood data, building exposure analysis, and "
            f"medical accessibility assessment."
        )

        # Cite specific evidence for top location
        top = affected[0]
        flood_detail = top.get("flood_status", {}).get("detail", "")
        if flood_detail:
            lines.append(f"Top location ({top['location']}): {flood_detail}")

        return "\n".join(lines)

    def _build_assessment_reasoning(
        self,
        ranked: list[dict],
        evidence: dict,
    ) -> str:
        """Build the WHY explanation for assessment recommendations."""
        affected = [r for r in ranked if r["category"] not in ("NONE", "SAFE")]
        if not affected:
            return "All locations assessed as low-risk based on current flood data."

        lines = ["WHY:"]
        for loc in affected[:3]:
            flood = loc.get("flood_status", {})
            exposure = loc.get("exposure", {})
            access = loc.get("accessibility", {})
            lines.append(
                f"- {loc['location']}: flood={'yes' if flood.get('flooded') else 'no'}, "
                f"exposure_ratio={exposure.get('exposure_ratio', 0):.1%}, "
                f"nearest_medical={access.get('medical_distance_km', -1):.1f}km"
            )

        return "\n".join(lines)

    # -------------------------------------------------------------------
    # Evidence, uncertainty, gaps
    # -------------------------------------------------------------------

    def _build_evidence_summary(self, evidence: dict, ranked: list[dict]) -> dict:
        """Build a structured evidence summary."""
        summary = {
            "tools_used": evidence.get("tools_used", []),
            "flood_snapshots": evidence.get("flood_snapshots", {}),
            "field_reports": evidence.get("field_reports", {}),
            "location_assessments": {},
        }

        for loc in ranked:
            summary["location_assessments"][loc["location"]] = {
                "flooded": loc.get("flood_status", {}).get("flooded", False),
                "exactly_contained": loc.get("flood_status", {}).get("exactly_contained", False),
                "near_flood_zone": loc.get("flood_status", {}).get("near_flood_zone", False),
                "exposure_ratio": loc.get("exposure", {}).get("exposure_ratio", 0),
                "medical_distance_km": loc.get("accessibility", {}).get("medical_distance_km", -1),
                "pdc_score": loc.get("pdc_score", 0),
                "category": loc.get("category", "UNKNOWN"),
            }

        return summary

    def _collect_uncertainty(self, evidence: dict, resolved_locations: list[dict]) -> list[str]:
        """Identify sources of uncertainty in the evidence."""
        uncertainty = []

        # Check if flood data is available
        snapshots = evidence.get("flood_snapshots", {})
        for district_id, snaps in snapshots.items():
            if isinstance(snaps, list) and not snaps:
                uncertainty.append(
                    f"No flood snapshot available for {district_id} — "
                    f"flood status unknown"
                )
            elif isinstance(snaps, list) and snaps:
                latest = snaps[0]
                # Check staleness
                if latest.get("observed_at"):
                    uncertainty.append(
                        f"{district_id} flood data observed: {latest['observed_at']} — "
                        f"conditions may have changed"
                    )

        # Check exposure data availability
        for loc in resolved_locations:
            loc_key = loc["name"]
            exposure = evidence.get("exposure", {}).get(loc_key, {})
            if not exposure.get("data_available", False):
                uncertainty.append(
                    f"Building exposure data unavailable for {loc_key} — "
                    f"exposure estimate is uncertain"
                )

        # Check accessibility data
        for loc in resolved_locations:
            loc_key = loc["name"]
            access = evidence.get("accessibility", {}).get(loc_key, {})
            if access.get("medical_distance_km", -1) < 0:
                uncertainty.append(
                    f"Medical accessibility data unavailable for {loc_key}"
                )

        return uncertainty

    def _collect_data_gaps(self, evidence: dict, resolved_locations: list[dict]) -> list[str]:
        """Identify important data gaps."""
        gaps = []

        # Check for field reports
        field_reports = evidence.get("field_reports", {})
        for district_id, reports in field_reports.items():
            if isinstance(reports, list) and not reports:
                gaps.append(
                    f"No recent field reports for {district_id} — "
                    f"situation on the ground is not confirmed"
                )

        # Check for road status data
        # (Not queried by default, so always a gap unless explicitly requested)
        gaps.append(
            "Road status data not queried — access routes may be "
            "flood-affected but are not reflected in this assessment"
        )

        return gaps

    def _build_constraints(self, request: PlanningRequest) -> list[str]:
        """Build list of constraints from the request."""
        constraints = []

        for r in request.resource_phrases:
            if r.get("quantity_numeric") is not None:
                constraints.append(
                    f"Resource: {r['raw_phrase']} ({r['quantity_numeric']} {r.get('unit', 'units')})"
                )

        if request.district_scope:
            constraints.append(
                f"District scope: {', '.join(request.district_scope)}"
            )

        return constraints


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _resource_type_to_constraint_key(resource_type: str, unit: str) -> str | None:
    """Map a resource type + unit to a canonical constraint key."""
    unit_lower = (unit or "").lower()
    rt_lower = (resource_type or "").lower()

    if rt_lower == "transport" or "boat" in unit_lower:
        return "boats"
    elif rt_lower == "medical" or "team" in unit_lower:
        return "medical_teams"
    elif rt_lower == "food" or "kg" in unit_lower:
        return "food_kg"
    elif rt_lower == "water":
        return "water_units"
    elif rt_lower == "shelter":
        return "shelter_kits"

    return None


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def plan_operation(raw_query: str, repository=None) -> PlanningResult:
    """Convenience entry point for planning an operation.

    Args:
        raw_query: the coordinator's natural language query
        repository: optional DataRepository instance

    Returns:
        PlanningResult with recommendation, evidence, and supporting info
    """
    planner = PlannerOrchestrator(repository=repository)
    return planner.plan(raw_query)
