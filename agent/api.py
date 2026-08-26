"""
ReliefOS Operations Intelligence Workspace — Backend API

Flask API providing structured evidence-grounded responses for the
Operations Intelligence Workspace frontend. Phase A: no free-text
query parsing — locations are selected from known coordinates.

Endpoints:
    GET /api/locations          — list of known reference locations
    GET /api/assess?location=X  — full assessment for a named location
    GET /api/assess?lat=X&lon=Y — full assessment for explicit coordinates
    GET /api/flood-geojson      — raw flood polygon GeoJSON for map rendering
"""

import os
import json
import time
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS

from agent.config import KNOWN_LOCATIONS
from agent.assessment import run_relief_assessment, _resolve_coordinates
from agent.community_reports import get_reports_near, get_all_reports, submit_field_intelligence
from agent.tools.field_intelligence_tool import extract_field_report
from agent.tools.query_parser_tool import (
    parse_operational_query,
    check_capability_gaps,
    resolve_query_locations,
)
from agent.tools.allocation_tool import rank_locations, allocate_resources, recommend_destination
from agent.tools.routing_tool import get_route, check_osrm_health
from agent.overrides import apply_override, get_operational_status, get_active_override, get_all_overrides
from agent.data_loader import FLOOD_DATA


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
CORS(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")


def _cache_file_timestamp(query_type: str, cache_key: str) -> str | None:
    """Return the file modification timestamp of a cache file, or None."""
    cache_path = os.path.join(_CACHE_DIR, f"{query_type}_{cache_key.lower()}.json")
    if not os.path.exists(cache_path):
        return None
    try:
        mtime = os.path.getmtime(cache_path)
        dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _humanize_timestamp(iso_str: str | None) -> str | None:
    """Return an ISO timestamp string as-is (frontend handles humanization)."""
    return iso_str


def _location_cache_key(location: str | None, lat: float | None, lon: float | None) -> str:
    """Determine the cache key used by the tools for this location."""
    if location:
        return location.strip().lower()
    if lat is not None and lon is not None:
        return f"{lat:.4f}"
    return "unknown"


def _convert_resources_for_allocation(resources_list: list[dict]) -> dict:
    """
    Best-effort mapping from flexible resources_mentioned list to the
    rigid {boats, medical_teams, food_kg} dict that allocate_resources()
    expects. Maps by resource_type and unit keywords.
    """
    alloc = {"boats": 0, "medical_teams": 0, "food_kg": 0}
    for r in resources_list:
        qty = r.get("quantity_numeric")
        if qty is None or qty <= 0:
            continue
        rtype = r.get("resource_type", "other")
        unit = (r.get("unit") or "").lower()
        phrase = (r.get("raw_phrase") or "").lower()

        if rtype == "transport" or "boat" in unit or "boat" in phrase:
            alloc["boats"] += qty
        elif rtype == "medical" or "medical" in phrase or "team" in unit:
            alloc["medical_teams"] += qty
        elif rtype == "food" or "food" in phrase or "kg" in unit or "rice" in phrase:
            alloc["food_kg"] += qty

    return alloc


# ---------------------------------------------------------------------------
# Fixed, honest data gaps list
# ---------------------------------------------------------------------------

DATA_GAPS = [
    {"item": "River gauge data", "status": "not_connected",
     "detail": "No real-time river level sensors integrated yet."},
    {"item": "Route optimization", "status": "available",
     "detail": "Real road routing via OSRM (with haversine fallback when unavailable)."},
    {"item": "Sustainment / burn-rate calculation", "status": "not_implemented",
     "detail": "Supply consumption forecasting not yet built."},
    {"item": "Itemized inventory tracking", "status": "not_implemented",
     "detail": "Per-location resource inventory not yet tracked."},
]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/api/locations", methods=["GET"])
def api_locations():
    """
    Return the list of known reference locations for the frontend
    to populate a dropdown or map markers.
    """
    locations = []
    for name, (lon, lat) in KNOWN_LOCATIONS.items():
        locations.append({
            "id": name,
            "label": name.replace("_", " ").title(),
            "lat": lat,
            "lon": lon,
        })
    return jsonify({"locations": locations})


@app.route("/api/assess", methods=["GET"])
def api_assess():
    """
    Run a full ReliefOS assessment for a location.
    Accepts either ?location=<name> or ?lat=<lat>&lon=<lon>.
    """
    location = request.args.get("location")
    lat_str = request.args.get("lat")
    lon_str = request.args.get("lon")

    lat = float(lat_str) if lat_str else None
    lon = float(lon_str) if lon_str else None

    if not location and (lat is None or lon is None):
        return jsonify({
            "error": "Provide either ?location=<name> or ?lat=<lat>&lon=<lon>"
        }), 400

    # Run the existing assessment (deterministic, no LLM)
    # Capture per-agent timing trace
    agent_trace = []
    result = run_relief_assessment(location=location, lat=lat, lon=lon, agent_trace=agent_trace)

    # Resolve actual coordinates for field reports lookup
    res_lat, res_lon = _resolve_coordinates(location=location, lat=lat, lon=lon)

    # Enrich with field reports
    field_reports = []
    if res_lat is not None and res_lon is not None:
        reports = get_reports_near(res_lat, res_lon, radius_km=3.0)
        for r in reports:
            field_reports.append({
                "report_id": r.get("id", "unknown"),
                "people_count": r.get("people_count", 0),
                "adults": r.get("adults", 0),
                "children": r.get("children", 0),
                "elderly": r.get("elderly", 0),
                "needs": r.get("needs", []),
                "verified": r.get("verified", False),
                "submitted_at": r.get("timestamp", ""),
                "lat": r.get("lat"),
                "lon": r.get("lon"),
                "distance_km": r.get("distance_km"),
            })

    # Determine cache timestamps
    cache_key = _location_cache_key(location, lat, lon)

    exposure_ts = _cache_file_timestamp("buildings", cache_key)
    accessibility_ts = _cache_file_timestamp("accessibility", cache_key)

    # Build the structured response
    evidence = result.get("evidence", {})

    flood_evidence = evidence.get("flood", {})
    exposure_evidence = evidence.get("exposure", {})
    accessibility_evidence = evidence.get("accessibility", {})

    # Flood source metadata
    flood_source = "Local flood GeoJSON (Sentinel-1 SAR)"
    flood_last_updated = None
    # The flood data is loaded from a static file, not a cache — note this
    flood_geojson_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "sivasagar_flood.geojson"
    )
    if os.path.exists(flood_geojson_path):
        try:
            mtime = os.path.getmtime(flood_geojson_path)
            flood_last_updated = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except Exception:
            pass

    response = {
        "location": result["location"],
        "coordinates": result["coordinates"],
        "agent_trace": agent_trace,
        "priority": {
            "pdc_score": result["priority"]["pdc_score"],
            "category": result["priority"]["category"],
            "recommendation": result["priority"]["recommendation"],
        },
        "evidence": {
            "flood": {
                "status": "available" if flood_evidence.get("flooded") is not None else "unavailable",
                "source": flood_source,
                "flooded": flood_evidence.get("flooded", False),
                "exactly_contained": flood_evidence.get("exactly_contained", False),
                "near_flood_zone": flood_evidence.get("near_flood_zone", False),
                "nearest_flood_polygon_km2": flood_evidence.get("nearest_flood_polygon_km2", 0.0),
                "total_flood_polygons": flood_evidence.get("total_flood_polygons", 0),
                "last_updated": flood_last_updated,
            },
            "exposure": {
                "status": "available" if exposure_evidence.get("data_available") else "unavailable",
                "source": "OpenStreetMap Overpass (cached)",
                "total_buildings": exposure_evidence.get("total_buildings", 0),
                "exposed_count": exposure_evidence.get("exposed_count", 0),
                "exposure_ratio": exposure_evidence.get("exposure_ratio", 0.0),
                "last_updated": _humanize_timestamp(exposure_ts),
            },
            "accessibility": {
                "status": "available" if accessibility_evidence.get("data_available") else "unavailable",
                "source": "OpenStreetMap Overpass (cached)",
                "medical_facility_name": accessibility_evidence.get("medical_facility_name", "Unknown"),
                "medical_distance_km": accessibility_evidence.get("medical_distance_km", -1),
                "last_updated": _humanize_timestamp(accessibility_ts),
            },
            "field_reports": {
                "status": "available" if field_reports else "none",
                "source": "KoboToolbox",
                "reports": field_reports,
            },
        },
        "data_gaps": DATA_GAPS,
        "llm_synthesis": None,
    }

    # Integrate overrides into accessibility evidence
    accessibility = response["evidence"]["accessibility"]
    if accessibility.get("medical_facility_name") and accessibility["medical_facility_name"] != "Unknown":
        op_status = get_operational_status(
            "facility",
            accessibility["medical_facility_name"],
            "operational" if accessibility.get("medical_distance_km", -1) >= 0 else "unknown",
        )
        accessibility["operational_status"] = op_status

    return jsonify(response)


# ---------------------------------------------------------------------------
# Free-text query endpoint
# ---------------------------------------------------------------------------

@app.route("/api/query", methods=["POST"])
def api_query():
    """
    Parse a free-text coordinator query and produce a structured response.

    Pipeline:
    1. LLM parses query into structured intent (locations, resources, capabilities)
    2. Resolve locations against known coordinates (honest fallback for unknowns)
    3. Run existing assessment for each resolved location
    4. If resources mentioned + multiple locations, run ranking + allocation
    5. Check capability gaps
    6. Assemble unified response
    """
    payload = request.get_json(force=True, silent=True)
    if not payload or not payload.get("query"):
        return jsonify({"error": "Body must include 'query'"}), 400

    raw_query = payload["query"].strip()
    if not raw_query:
        return jsonify({"error": "Query cannot be empty"}), 400

    # Agent trace: capture per-step timing for the full query pipeline
    agent_trace = []

    # Step 1: Parse the query via LLM
    _t0 = time.time()
    parsed_intent = parse_operational_query(raw_query)
    _t1 = time.time()
    agent_trace.append({
        "agent_name": "query_parser_agent",
        "query_portion_handled": "Parsing free-text query into structured intent",
        "started_at": _t0,
        "completed_at": _t1,
        "duration_ms": round((_t1 - _t0) * 1000, 1),
        "tools_called": ["parse_operational_query"],
        "output_summary": f"Intent: {parsed_intent.get('intent', 'unknown')}, {len(parsed_intent.get('locations_mentioned', []))} location(s) found",
        "raw_output": {
            "intent": parsed_intent.get("intent"),
            "locations_mentioned": parsed_intent.get("locations_mentioned", []),
            "resources_mentioned": parsed_intent.get("resources_mentioned", []),
            "parse_confidence": parsed_intent.get("parse_confidence"),
        },
        "status": "complete",
    })

    # Step 2: Resolve locations against known locations (deterministic, no LLM)
    resolved_locations, unresolved_locations = resolve_query_locations(
        parsed_intent.get("locations_mentioned", []),
        KNOWN_LOCATIONS,
    )
    if resolved_locations:
        agent_trace.append({
            "agent_name": "location_resolver",
            "query_portion_handled": "Resolving location names to coordinates",
            "started_at": _t1,
            "completed_at": _t1,  # deterministic, instant
            "duration_ms": 0,
            "tools_called": ["resolve_query_locations"],
            "output_summary": f"Resolved {len(resolved_locations)} location(s), {len(unresolved_locations)} unresolved",
            "raw_output": {
                "resolved": [{"name": l["name"], "lat": l["lat"], "lon": l["lon"]} for l in resolved_locations],
                "unresolved": unresolved_locations,
            },
            "status": "complete",
        })

    # Step 3: Run assessment for each resolved location
    location_results = []
    for loc in resolved_locations:
        loc_trace = []
        assessment = run_relief_assessment(
            location=loc["name"],
            lat=loc["lat"],
            lon=loc["lon"],
            agent_trace=loc_trace,
        )
        # Prefix agent names with location for multi-location clarity
        for entry in loc_trace:
            entry["location_context"] = loc["name"]
        agent_trace.extend(loc_trace)
        location_results.append(assessment)

    # Step 4: Resource allocation (if quantified resources + multiple locations)
    resources_list = parsed_intent.get("resources_mentioned", [])
    has_quantified_resources = any(
        r.get("quantity_numeric") is not None and r["quantity_numeric"] > 0
        for r in resources_list
    )

    allocation_plan = None
    if has_quantified_resources and len(resolved_locations) >= 2:
        # Build ranked location data for allocation
        ranked = []
        for loc in resolved_locations:
            assessment = run_relief_assessment(
                location=loc["name"],
                lat=loc["lat"],
                lon=loc["lon"],
            )
            ranked.append({
                "location": loc["name"],
                "pdc_score": assessment["priority"]["pdc_score"],
                "category": assessment["priority"]["category"],
                "flood_status": assessment["evidence"]["flood"],
                "exposure": assessment["evidence"]["exposure"],
                "accessibility": assessment["evidence"]["accessibility"],
                "priority": assessment["priority"],
            })

        # Sort by PDC score descending
        ranked.sort(key=lambda r: r["pdc_score"], reverse=True)

        # Extract known resource types for allocation (best-effort mapping)
        alloc_resources = _convert_resources_for_allocation(resources_list)

        allocation_text = allocate_resources(ranked, alloc_resources)

        # Build structured allocation plan
        allocation_plan = {
            "text": allocation_text,
            "ranked_locations": [
                {
                    "location": r["location"],
                    "pdc_score": r["pdc_score"],
                    "category": r["category"],
                }
                for r in ranked
            ],
            "resources": alloc_resources,
        }

    # Step 5: Check capability gaps
    capability_gaps = check_capability_gaps(
        parsed_intent.get("requested_capabilities", {})
    )

    # Step 6: Assemble response
    clarification_needed = parsed_intent.get("clarification_needed", [])

    response = {
        "raw_query": raw_query,
        "parsed_intent": parsed_intent,
        "resolved_locations": location_results,
        "unresolved_locations": unresolved_locations,
        "allocation_plan": allocation_plan,
        "capability_gaps": capability_gaps,
        "clarification_needed": clarification_needed,
        "agent_trace": agent_trace,
    }

    return jsonify(response)


# ---------------------------------------------------------------------------
# Field Intelligence endpoint
# ---------------------------------------------------------------------------

@app.route("/api/field-intelligence", methods=["POST"])
def api_field_intelligence():
    """
    Accept a raw field observation text, extract structured fields via LLM,
    and store as a report. Always preserves the original raw text.
    """
    payload = request.get_json(force=True, silent=True)
    if not payload or not payload.get("raw_text"):
        return jsonify({"error": "Body must include 'raw_text'"}), 400

    raw_text = payload["raw_text"]

    # Extract structured fields via LLM
    extraction = extract_field_report(raw_text)

    # Store the report (no lat/lon — location is unresolved text)
    store_result = submit_field_intelligence(extraction)

    return jsonify({
        "extraction": extraction,
        "store_result": store_result,
    })


@app.route("/api/field-intelligence/history", methods=["GET"])
def api_field_intelligence_history():
    """Return all field intelligence reports."""
    all_reports = get_all_reports()
    fi_reports = [r for r in all_reports if r.get("source") == "field_intelligence_text"]
    return jsonify({"reports": fi_reports})


# ---------------------------------------------------------------------------
# Override endpoints
# ---------------------------------------------------------------------------

@app.route("/api/override", methods=["POST"])
def api_apply_override():
    """
    Apply a manual override to a facility or road status.
    Body: {target_type, target_id, new_status, reason}
    """
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "Invalid JSON body"}), 400

    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    new_status = payload.get("new_status")
    reason = payload.get("reason", "")

    if not all([target_type, target_id, new_status]):
        return jsonify({"error": "Required: target_type, target_id, new_status"}), 400

    if target_type not in ("facility", "road"):
        return jsonify({"error": "target_type must be 'facility' or 'road'"}), 400

    # Get current system status for the record
    # For now, use a simple heuristic — this could be enhanced later
    system_status = "operational"  # default assumption
    if target_type == "facility":
        # Try to get from accessibility evidence if available
        system_status = "operational"  # placeholder — real integration would query the tool

    record = apply_override(
        target_type=target_type,
        target_id=target_id,
        new_status=new_status,
        reason=reason,
        system_status=system_status,
    )

    return jsonify({"override": record})


@app.route("/api/override/status", methods=["GET"])
def api_override_status():
    """
    Get the current operational status for a target, including any active override.
    Query: ?target_type=...&target_id=...
    """
    target_type = request.args.get("target_type")
    target_id = request.args.get("target_id")

    if not target_type or not target_id:
        return jsonify({"error": "Required: target_type, target_id"}), 400

    # Get system status — default to operational if unknown
    system_status = "operational"

    op_status = get_operational_status(target_type, target_id, system_status)
    return jsonify(op_status)


@app.route("/api/overrides", methods=["GET"])
def api_list_overrides():
    """Return all active overrides."""
    overrides = get_all_overrides()
    return jsonify({"overrides": overrides})


@app.route("/api/route", methods=["GET"])
def api_route():
    """
    Get a real driving route between two points using OSRM.
    
    Query parameters:
        start_lat: Starting latitude
        start_lon: Starting longitude
        end_lat: Ending latitude
        end_lon: Ending longitude
    
    Returns route with distance, duration, geometry, and source information.
    """
    start_lat_str = request.args.get("start_lat")
    start_lon_str = request.args.get("start_lon")
    end_lat_str = request.args.get("end_lat")
    end_lon_str = request.args.get("end_lon")
    
    if not all([start_lat_str, start_lon_str, end_lat_str, end_lon_str]):
        return jsonify({
            "error": "Required: start_lat, start_lon, end_lat, end_lon"
        }), 400
    
    try:
        start_lat = float(start_lat_str)
        start_lon = float(start_lon_str)
        end_lat = float(end_lat_str)
        end_lon = float(end_lon_str)
    except ValueError:
        return jsonify({"error": "Invalid coordinate values"}), 400
    
    # Get the route
    route = get_route(
        start_lat=start_lat,
        start_lon=start_lon,
        end_lat=end_lat,
        end_lon=end_lon
    )
    
    # Add OSRM health status
    route["osrm_healthy"] = check_osrm_health()
    
    return jsonify(route)


@app.route("/api/routes", methods=["POST"])
def api_multiple_routes():
    """
    Get routes from one origin to multiple destinations.
    
    Body:
        {
            "origin": {"lat": float, "lon": float},
            "destinations": [{"lat": float, "lon": float, "id": str}, ...]
        }
    """
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "Invalid JSON body"}), 400
    
    origin = payload.get("origin")
    destinations = payload.get("destinations", [])
    
    if not origin or not destinations:
        return jsonify({
            "error": "Required: origin (lat, lon) and destinations list"
        }), 400
    
    # Get routes for all destinations
    from agent.tools.routing_tool import get_multiple_routes
    routes = get_multiple_routes(
        origin_lat=origin["lat"],
        origin_lon=origin["lon"],
        destinations=destinations
    )
    
    return jsonify({
        "origin": origin,
        "routes": routes,
        "osrm_healthy": check_osrm_health()
    })


@app.route("/api/recommend-destination", methods=["POST"])
def api_recommend_destination():
    """
    Recommend destination(s) for resource deployment with real routing.
    
    Body:
        {
            "origin": {"lat": float, "lon": float},
            "locations": [str, ...]  # location names to assess
        }
    """
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "Invalid JSON body"}), 400
    
    origin = payload.get("origin")
    location_names = payload.get("locations", [])
    
    if not origin or not location_names:
        return jsonify({
            "error": "Required: origin (lat, lon) and locations list"
        }), 400
    
    # Rank locations first
    ranked = rank_locations(location_names)
    
    # Get route-aware recommendations
    recommendations = recommend_destination(
        origin_lat=origin["lat"],
        origin_lon=origin["lon"],
        ranked_locations=ranked
    )
    
    return jsonify(recommendations)


@app.route("/api/flood-geojson", methods=["GET"])
def api_flood_geojson():
    """Return the raw flood polygon GeoJSON for map rendering."""
    return jsonify(FLOOD_DATA)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Starting ReliefOS API on http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
