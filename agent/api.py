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
import gzip
import hashlib
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
from agent.data_loader import FLOOD_DATA, get_flood_data, get_all_known_locations


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

    Phase 4: Uses repository-backed locations when available.
    Falls back to legacy KNOWN_LOCATIONS.
    """
    locations = []
    try:
        from agent.data.repository import get_repository
        settlements = get_repository().list_settlements()
        if settlements:
            return jsonify({"locations": [s.to_dict() for s in settlements]})
    except Exception:
        pass
    # Phase 4: Use repository-backed locations
    all_locs = get_all_known_locations()
    for name, (lon, lat) in all_locs.items():
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
    """
    Return the raw flood polygon GeoJSON for map rendering.

    Phase 4: Uses repository-backed flood data when available.
    Falls back to legacy FLOOD_DATA.

    Payload hygiene (publish-offer stall fix, 2026-09-06):
    - Coordinates are rounded to 6 decimal places (~11 cm) — visually
      identical at map-display zoom levels, far fewer bytes.
    - Response is gzipped when the client sends Accept-Encoding: gzip
      (browsers do; Flask test clients don't, keeping tests on plain JSON).
    - Result is cached per (district, flood-snapshot version) so repeated
      requests skip the expensive DB read + re-serialize + gzip work.
    """
    district_id = request.args.get("district")
    flood_data = _flood_geojson_payload(district_id)
    return _flood_geojson_response(flood_data, scope=("all" if not district_id else f"d:{district_id}"))


def _flood_geojson_round_coords(obj):
    """Round all coordinate pairs to 6 decimals (~11 cm precision)."""
    if isinstance(obj, (list, tuple)) and len(obj) == 2 and all(isinstance(v, (int, float)) for v in obj):
        return [round(float(obj[0]), 6), round(float(obj[1]), 6)]
    if isinstance(obj, list):
        return [_flood_geojson_round_coords(item) for item in obj]
    return obj


def _flood_geojson_reduce_precision(flood_data):
    """Round feature geometry coordinates without touching properties/contract."""
    if not isinstance(flood_data, dict):
        return flood_data
    features = flood_data.get("features")
    if not isinstance(features, list):
        return flood_data
    reduced = []
    for f in features:
        if isinstance(f, dict) and isinstance(f.get("geometry"), dict) and "coordinates" in f["geometry"]:
            geometry = dict(f["geometry"])
            geometry["coordinates"] = _flood_geojson_round_coords(geometry["coordinates"])
            reduced.append({**f, "geometry": geometry})
        else:
            reduced.append(f)
    return {**flood_data, "features": reduced}


# Cache: {(scope, version_key): {"plain": bytes, "gzip": bytes}} — final
# response bytes per encoding, so warm requests serve instantly with zero
# re-serialization. version_key = max(created_at) of the in-scope
# flood_snapshots, so any re-import/new snapshot invalidates automatically.
_flood_geojson_cache = {}
_flood_geojson_cache_max = 16


def _flood_geojson_version(repo, district_id):
    try:
        from sqlalchemy import select as _select, func as _func
        from agent.data.schema import flood_snapshots as _fs
        stmt = _select(_func.max(_fs.c.created_at))
        if district_id:
            stmt = stmt.where(_fs.c.district_id == district_id)
        row = repo._execute_fetchone(stmt)
        return str(row[0]) if row and row[0] else "none"
    except Exception:
        return f"uncached-{time.time()}"


def _flood_geojson_payload(district_id):
    """Build (and cache) response bytes for a district scope.

    Returns (plain_bytes, gzip_bytes_or_None). The dict is serialized and
    compressed exactly once per (scope, snapshot-version); every subsequent
    request serves the cached bytes directly.
    """
    from agent.data.repository import get_repository
    scope = "all" if not district_id else f"d:{district_id}"
    try:
        repo = get_repository()
        version = _flood_geojson_version(repo, district_id)
    except Exception:
        version = f"uncached-{time.time()}"
        repo = None
    cache_key = (scope, version)
    cached = _flood_geojson_cache.get(cache_key)
    if cached is not None:
        return cached["plain"], cached["gzip"]

    flood_data = _flood_geojson_reduce_precision(get_flood_data(district_id))
    plain = json.dumps(flood_data).encode("utf-8")
    # Level 1: on this GeoJSON it's within ~15% of level 9's ratio but ~5x
    # faster, keeping the one-time cold build close to the old uncompressed
    # serve time.
    gz = gzip.compress(plain, compresslevel=1, mtime=0)
    entry = {"plain": plain, "gzip": gz}
    try:
        if len(_flood_geojson_cache) >= _flood_geojson_cache_max:
            _flood_geojson_cache.clear()
        _flood_geojson_cache[cache_key] = entry
    except Exception:
        pass
    return plain, gz


def _flood_geojson_response(flood_data, scope):
    """Serve cached bytes; gzip only when the client advertises gzip support."""
    plain, gz = flood_data
    accepts = request.headers.get("Accept-Encoding", "")
    if gz is not None and "gzip" in accepts.lower():
        return app.response_class(
            gz, status=200, mimetype="application/json",
            headers={"Content-Encoding": "gzip"},
        )
    return app.response_class(plain, status=200, mimetype="application/json")


# ---------------------------------------------------------------------------
# Districts endpoint
# ---------------------------------------------------------------------------

@app.route("/api/districts", methods=["GET"])
def api_districts():
    """Return list of all districts with their geometries."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        districts = repo.list_districts()
        return jsonify({
            "districts": [d.to_dict() for d in districts]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/districts/<district_id>/flood-geojson", methods=["GET"])
def api_district_flood_geojson(district_id):
    """Return flood GeoJSON for a specific district (precision-reduced, gzip-negotiated, cached)."""
    flood_data = _flood_geojson_payload(district_id)
    return _flood_geojson_response(flood_data, scope=f"d:{district_id}")
    return jsonify(flood_data)


@app.route("/api/districts/<district_id>/settlements", methods=["GET"])
def api_district_settlements(district_id):
    """Return settlements for a specific district."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        settlements = repo.list_settlements(district_id=district_id)
        return jsonify({
            "settlements": [s.to_dict() for s in settlements]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/districts/<district_id>/roads", methods=["GET"])
def api_district_roads(district_id):
    """Return roads for a specific district as JSON."""
    try:
        from agent.data.repository import get_repository
        from agent.overrides import get_all_overrides
        repo = get_repository()
        roads = repo.get_roads(district_id)

        # Load active overrides for enrichment
        all_overrides = get_all_overrides()
        override_map = {}
        for o in all_overrides:
            if o.get("active", True) and o.get("target_type") == "road":
                override_map[o["target_id"]] = o

        road_dicts = []
        for r in roads:
            # Determine bridge status from field or tags
            is_bridge = r.is_bridge or (r.tags or {}).get("bridge") == "yes"
            d = {
                "id": r.id,
                "name": r.name or "Unnamed road",
                "highway_type": r.highway_type,
                "district_id": r.district_id,
                "is_bridge": is_bridge,
                "flood_affected": r.flood_affected,
                "provenance": r.provenance.value,
                "tags": r.tags,
                "geometry_coords": r.geometry_coords,
            }
            # Determine operational status: authoritative + override
            override = override_map.get(r.name) or override_map.get(r.id)
            if override:
                d["operational_status"] = override["override_status"]
                d["override"] = {
                    "status": override["override_status"],
                    "reason": override.get("reason", ""),
                    "actor": override.get("actor", ""),
                    "timestamp": override.get("timestamp", ""),
                }
            elif r.flood_affected:
                d["operational_status"] = "uncertain"
                d["override"] = None
            else:
                d["operational_status"] = "open"
                d["override"] = None

            road_dicts.append(d)

        return jsonify({"roads": road_dicts, "count": len(road_dicts)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/districts/<district_id>/roads/geojson", methods=["GET"])
def api_district_roads_geojson(district_id):
    """Return roads for a specific district as GeoJSON FeatureCollection."""
    try:
        from agent.data.repository import get_repository
        from agent.overrides import get_all_overrides
        repo = get_repository()
        roads = repo.get_roads(district_id)

        # Load active overrides
        all_overrides = get_all_overrides()
        override_map = {}
        for o in all_overrides:
            if o.get("active", True) and o.get("target_type") == "road":
                override_map[o["target_id"]] = o

        features = []
        for r in roads:
            if not r.geometry_coords or len(r.geometry_coords) < 2:
                continue

            is_bridge = r.is_bridge or (r.tags or {}).get("bridge") == "yes"

            # Determine status and color
            override = override_map.get(r.name) or override_map.get(r.id)
            if override:
                op_status = override["override_status"]
                is_blocked = op_status in ("blocked", "submerged", "damaged")
            elif r.flood_affected:
                op_status = "uncertain"
                is_blocked = False
            else:
                op_status = "open"
                is_blocked = False

            color = "#dc2626" if is_blocked else ("#d97706" if op_status == "uncertain" else "#16a34a")

            feature = {
                "type": "Feature",
                "properties": {
                    "id": r.id,
                    "name": r.name or "Unnamed road",
                    "highway_type": r.highway_type,
                    "is_bridge": is_bridge,
                    "flood_affected": r.flood_affected,
                    "operational_status": op_status,
                    "color": color,
                    "override": {
                        "status": override["override_status"],
                        "reason": override.get("reason", ""),
                        "actor": override.get("actor", ""),
                        "timestamp": override.get("timestamp", ""),
                    } if override else None,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": r.geometry_coords,
                },
            }
            features.append(feature)

        return jsonify({
            "type": "FeatureCollection",
            "features": features,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/districts/<district_id>/bridges", methods=["GET"])
def api_district_bridges(district_id):
    """Return bridges (roads where is_bridge=True) for a specific district."""
    try:
        from agent.data.repository import get_repository
        from agent.overrides import get_all_overrides
        repo = get_repository()
        roads = repo.get_roads(district_id)

        # Filter to bridges only — check both is_bridge field and tags.bridge
        bridges = [r for r in roads if r.is_bridge or (r.tags or {}).get("bridge") == "yes"]

        # Load active overrides
        all_overrides = get_all_overrides()
        override_map = {}
        for o in all_overrides:
            if o.get("active", True) and o.get("target_type") == "road":
                override_map[o["target_id"]] = o

        bridge_dicts = []
        for r in bridges:
            is_bridge = r.is_bridge or (r.tags or {}).get("bridge") == "yes"
            d = {
                "id": r.id,
                "name": r.name or "Unnamed bridge",
                "highway_type": r.highway_type,
                "district_id": r.district_id,
                "is_bridge": is_bridge,
                "flood_affected": r.flood_affected,
                "provenance": r.provenance.value,
                "tags": r.tags,
                "geometry_coords": r.geometry_coords,
            }
            override = override_map.get(r.name) or override_map.get(r.id)
            if override:
                d["operational_status"] = override["override_status"]
                d["override"] = {
                    "status": override["override_status"],
                    "reason": override.get("reason", ""),
                    "actor": override.get("actor", ""),
                    "timestamp": override.get("timestamp", ""),
                }
            elif r.flood_affected:
                d["operational_status"] = "uncertain"
                d["override"] = None
            else:
                d["operational_status"] = "open"
                d["override"] = None

            bridge_dicts.append(d)

        return jsonify({"bridges": bridge_dicts, "count": len(bridge_dicts)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/districts/<district_id>/medical-facilities", methods=["GET"])
def api_district_medical_facilities(district_id):
    """Return real medical facilities for a district."""
    try:
        from agent.data.repository import get_repository
        facilities = get_repository().get_medical_facilities(district_id)
        return jsonify({"facilities": [f.to_dict() for f in facilities], "count": len(facilities)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Needs endpoints
# ---------------------------------------------------------------------------

@app.route("/api/needs", methods=["GET"])
def api_list_needs():
    """List shared needs with optional filters."""
    try:
        from agent.data.repository import get_repository
        from agent.data.models import Need
        repo = get_repository()
        district_id = request.args.get("district_id")
        status = request.args.get("status")
        urgency = request.args.get("urgency")
        needs = repo.list_needs(district_id=district_id, status=status, urgency=urgency)
        return jsonify({"needs": [n.to_dict() for n in needs]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/needs", methods=["POST"])
def api_create_need():
    """Create a new shared need."""
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import Need, ActivityEvent
        from datetime import datetime, timezone

        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400

        repo = get_repository()
        need_id = f"need_{str(uuid.uuid4())[:8]}"
        need = Need(
            id=need_id,
            need_type=payload.get("need_type", "other"),
            title=payload.get("title", ""),
            description=payload.get("description", ""),
            district_id=payload.get("district_id"),
            lat=payload.get("lat"),
            lon=payload.get("lon"),
            location_name=payload.get("location_name"),
            urgency=payload.get("urgency", "medium"),
            status="OPEN",
            requested_resources=payload.get("requested_resources", []),
            reporter_id=payload.get("reporter_id", "anonymous"),
            reporter_type=payload.get("reporter_type", "coordinator"),
            confidence=payload.get("confidence", 0.5),
        )
        result = repo.create_need(need)

        # Record activity
        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="need",
            entity_id=need_id,
            event_type="need_created",
            actor=payload.get("reporter_id", "anonymous"),
            detail=f"Need created: {need.title}",
        ))

        return jsonify({"need": result.to_dict()}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/needs/<need_id>", methods=["GET"])
def api_get_need(need_id):
    """Get a specific need by ID."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        need = repo.get_need(need_id)
        if not need:
            return jsonify({"error": "Need not found"}), 404
        return jsonify({"need": need.to_dict()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/needs/<need_id>", methods=["PATCH"])
def api_update_need(need_id):
    """Update a need (status, description, etc.)."""
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import ActivityEvent
        repo = get_repository()
        need = repo.get_need(need_id)
        if not need:
            return jsonify({"error": "Need not found"}), 404

        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400

        # Update fields
        if "status" in payload:
            old_status = need.status
            new_status = payload["status"]
            need.status = new_status
            # Use specific event types for lifecycle transitions
            if new_status == "RESOLVED" or new_status == "CLOSED":
                event_type = "need_resolved"
            elif old_status in ("RESOLVED", "CLOSED") and new_status == "OPEN":
                event_type = "need_reopened"
            elif new_status == "RESPONDING" and old_status == "OPEN":
                event_type = "need_accepted"
            else:
                event_type = "need_updated"
            repo.append_activity_event(ActivityEvent(
                id=f"evt_{str(uuid.uuid4())[:8]}",
                entity_type="need",
                entity_id=need_id,
                event_type=event_type,
                actor=payload.get("actor", "coordinator"),
                detail=f"Need status: {old_status} → {need.status}",
            ))
        if "title" in payload:
            need.title = payload["title"]
        if "description" in payload:
            need.description = payload["description"]
        if "urgency" in payload:
            need.urgency = payload["urgency"]
        if "requested_resources" in payload:
            need.requested_resources = payload["requested_resources"]

        need.updated_at = datetime.now(timezone.utc)
        repo.update_need(need)
        return jsonify({"need": need.to_dict()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Resource Offers endpoints
# ---------------------------------------------------------------------------

@app.route("/api/offers", methods=["GET"])
def api_list_offers():
    """List resource offers with optional filters."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        org_id = request.args.get("organization_id")
        district_id = request.args.get("district_id")
        status = request.args.get("status")
        resource_type = request.args.get("resource_type")
        offers = repo.list_resource_offers(
            organization_id=org_id,
            district_id=district_id,
            status=status,
            resource_type=resource_type,
        )
        return jsonify({"offers": [o.to_dict() for o in offers]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/offers", methods=["POST"])
def api_create_offer():
    """Publish a new resource offer."""
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import ResourceOffer, ActivityEvent, Organization
        repo = get_repository()

        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400

        organization_id = payload.get("organization_id") or "org_reliefos_default"
        if not payload.get("organization_id") and not repo.get_organization(organization_id):
            repo.create_organization(Organization(
                id=organization_id,
                name="ReliefOS Coordination Cell",
                organization_type="coordinator",
                description="Default local organization for ReliefOS workspace actions.",
            ))
        if not repo.get_organization(organization_id):
            return jsonify({"error": f"Organization not found: {organization_id}"}), 400

        offer_id = f"offer_{str(uuid.uuid4())[:8]}"
        offer = ResourceOffer(
            id=offer_id,
            organization_id=organization_id,
            resource_type=payload.get("resource_type", "other"),
            quantity=payload.get("quantity", 0),
            unit=payload.get("unit", "units"),
            lat=payload.get("lat"),
            lon=payload.get("lon"),
            location_name=payload.get("location_name"),
            district_id=payload.get("district_id"),
            status="OFFERED",
            notes=payload.get("notes", ""),
        )
        result = repo.create_resource_offer(offer)

        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="resource_offer",
            entity_id=offer_id,
            event_type="resource_offered",
            actor=organization_id,
            detail=f"Resource offer published: {offer.quantity} {offer.resource_type}",
        ))

        return jsonify({"offer": result.to_dict()}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/offers/<offer_id>", methods=["PATCH"])
def api_update_offer(offer_id):
    """Update a resource offer."""
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import ActivityEvent
        from datetime import datetime, timezone
        repo = get_repository()
        offer = repo.get_resource_offer(offer_id)
        if not offer:
            return jsonify({"error": "Offer not found"}), 404

        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400

        if "status" in payload:
            old_status = offer.status
            offer.status = payload["status"]
            repo.append_activity_event(ActivityEvent(
                id=f"evt_{str(uuid.uuid4())[:8]}",
                entity_type="resource_offer",
                entity_id=offer_id,
                event_type="status_changed",
                actor=payload.get("actor", offer.organization_id),
                detail=f"Offer status changed: {old_status} → {offer.status}",
            ))
        if "quantity" in payload:
            offer.quantity = payload["quantity"]
        if "notes" in payload:
            offer.notes = payload["notes"]

        offer.updated_at = datetime.now(timezone.utc)
        repo.update_resource_offer(offer)
        return jsonify({"offer": offer.to_dict()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Operations endpoints
# ---------------------------------------------------------------------------

@app.route("/api/operations", methods=["GET"])
def api_list_operations():
    """List operations with optional filters."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        district_id = request.args.get("district_id")
        status = request.args.get("status")
        lead_org = request.args.get("lead_organization_id")
        ops = repo.list_operations(
            district_id=district_id,
            status=status,
            lead_organization_id=lead_org,
        )
        return jsonify({"operations": [o.to_dict() for o in ops]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/operations", methods=["POST"])
def api_create_operation():
    """Create a new operation."""
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import Operation, ActivityEvent
        repo = get_repository()

        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400

        op_id = f"op_{str(uuid.uuid4())[:8]}"
        op = Operation(
            id=op_id,
            name=payload.get("name", ""),
            operation_type=payload.get("operation_type", "other"),
            description=payload.get("description", ""),
            need_id=payload.get("need_id"),
            lead_organization_id=payload.get("lead_organization_id"),
            district_id=payload.get("district_id"),
            lat=payload.get("lat"),
            lon=payload.get("lon"),
            location_name=payload.get("location_name"),
            status="PLANNING",
        )
        result = repo.create_operation(op)

        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="operation",
            entity_id=op_id,
            event_type="operation_created",
            actor=payload.get("lead_organization_id", "coordinator"),
            detail=f"Operation created: {op.name}",
        ))

        return jsonify({"operation": result.to_dict()}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/operations/<op_id>", methods=["GET"])
def api_get_operation(op_id):
    """Get a specific operation by ID."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        op = repo.get_operation(op_id)
        if not op:
            return jsonify({"error": "Operation not found"}), 404
        participants = repo.list_operation_participants(op_id)
        result = op.to_dict()
        result["participants"] = participants
        return jsonify({"operation": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/operations/<op_id>", methods=["PATCH"])
def api_update_operation(op_id):
    """Update an operation."""
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import ActivityEvent
        from datetime import datetime, timezone
        repo = get_repository()
        op = repo.get_operation(op_id)
        if not op:
            return jsonify({"error": "Operation not found"}), 404

        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400

        if "status" in payload:
            old_status = op.status
            new_status = payload["status"]
            op.status = new_status
            if new_status == "COMPLETED":
                event_type = "operation_resolved"
            elif old_status == "PLANNING" and new_status == "ACTIVE":
                event_type = "operation_activated"
            elif new_status == "CANCELLED":
                event_type = "operation_cancelled"
            else:
                event_type = "operation_updated"
            repo.append_activity_event(ActivityEvent(
                id=f"evt_{str(uuid.uuid4())[:8]}",
                entity_type="operation",
                entity_id=op_id,
                event_type=event_type,
                actor=payload.get("actor", "coordinator"),
                detail=f"Operation {op.name}: {old_status} → {new_status}",
            ))
        if "name" in payload:
            op.name = payload["name"]
        if "description" in payload:
            op.description = payload["description"]

        op.updated_at = datetime.now(timezone.utc)
        repo.update_operation(op)
        return jsonify({"operation": op.to_dict()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Organizations endpoints
# ---------------------------------------------------------------------------

@app.route("/api/organizations", methods=["GET"])
def api_list_organizations():
    """List network organizations."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        orgs = repo.list_organizations(active_only=True)
        return jsonify({"organizations": [o.to_dict() for o in orgs]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/organizations", methods=["POST"])
def api_create_organization():
    """Register a new organization."""
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import Organization
        repo = get_repository()

        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400

        org_id = payload.get("id", f"org_{str(uuid.uuid4())[:8]}")
        org = Organization(
            id=org_id,
            name=payload.get("name", ""),
            organization_type=payload.get("organization_type", "ngo"),
            description=payload.get("description", ""),
            published_capabilities=payload.get("published_capabilities", []),
            public_contact=payload.get("public_contact", {}),
        )
        result = repo.create_organization(org)
        return jsonify({"organization": result.to_dict()}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/organizations/<org_id>", methods=["GET"])
def api_get_organization(org_id):
    """Get a specific organization profile."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        org = repo.get_organization(org_id)
        if not org:
            return jsonify({"error": "Organization not found"}), 404
        return jsonify({"organization": org.to_dict()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Organization Workspace endpoints (Phase 7E)
# ---------------------------------------------------------------------------

@app.route("/api/orgs/<org_id>/summary", methods=["GET"])
def api_org_summary(org_id):
    """Get organization workspace summary (private + public state)."""
    try:
        from agent.org_workspace import get_org_summary
        result = get_org_summary(org_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/resources", methods=["GET"])
def api_org_list_resources(org_id):
    """List private resources for an organization."""
    try:
        from agent.org_workspace import list_resources
        resources = list_resources(org_id)
        return jsonify({"resources": resources})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/resources", methods=["POST"])
def api_org_add_resource(org_id):
    """Add a private resource to organization inventory."""
    try:
        from agent.org_workspace import add_resource
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        resource = add_resource(org_id, payload)
        return jsonify({"resource": resource}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/resources/<resource_id>", methods=["PATCH"])
def api_org_update_resource(org_id, resource_id):
    """Update a private resource."""
    try:
        from agent.org_workspace import update_resource
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        result = update_resource(org_id, resource_id, payload)
        if not result:
            return jsonify({"error": "Resource not found"}), 404
        return jsonify({"resource": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/resources/<resource_id>", methods=["DELETE"])
def api_org_delete_resource(org_id, resource_id):
    """Delete a private resource."""
    try:
        from agent.org_workspace import delete_resource
        deleted = delete_resource(org_id, resource_id)
        if not deleted:
            return jsonify({"error": "Resource not found"}), 404
        return jsonify({"message": "Resource deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/teams", methods=["GET"])
def api_org_list_teams(org_id):
    """List private teams for an organization."""
    try:
        from agent.org_workspace import list_teams
        teams = list_teams(org_id)
        return jsonify({"teams": teams})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/teams", methods=["POST"])
def api_org_add_team(org_id):
    """Add a private team."""
    try:
        from agent.org_workspace import add_team
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        team = add_team(org_id, payload)
        return jsonify({"team": team}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/teams/<team_id>", methods=["PATCH"])
def api_org_update_team(org_id, team_id):
    """Update a private team."""
    try:
        from agent.org_workspace import update_team
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        result = update_team(org_id, team_id, payload)
        if not result:
            return jsonify({"error": "Team not found"}), 404
        return jsonify({"team": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/missions", methods=["GET"])
def api_org_list_missions(org_id):
    """List private missions for an organization."""
    try:
        from agent.org_workspace import list_missions
        missions = list_missions(org_id)
        return jsonify({"missions": missions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/missions", methods=["POST"])
def api_org_add_mission(org_id):
    """Add a private mission."""
    try:
        from agent.org_workspace import add_mission
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        mission = add_mission(org_id, payload)
        return jsonify({"mission": mission}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/missions/<mission_id>", methods=["PATCH"])
def api_org_update_mission(org_id, mission_id):
    """Update a private mission."""
    try:
        from agent.org_workspace import update_mission
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        result = update_mission(org_id, mission_id, payload)
        if not result:
            return jsonify({"error": "Mission not found"}), 404
        return jsonify({"mission": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/agent/analyze-need", methods=["POST"])
def api_org_agent_analyze_need(org_id):
    """
    NGO Main Agent analyzes a network Need using private organizational context.
    
    Body: {"need": {...}} — the full need dict from the network.
    
    Returns recommendation, evidence, proposed publication.
    This endpoint performs NO writes — human must approve any publication.
    """
    try:
        from agent.agents.ngo_main_agent import analyze_need_for_org
        from agent.org_workspace import list_resources, list_teams, list_missions
        from agent.data.repository import get_repository
        
        payload = request.get_json(force=True, silent=True)
        if not payload or not payload.get("need"):
            return jsonify({"error": "Body must include 'need'"}), 400
        
        need = payload["need"]
        
        # Load private context
        resources = list_resources(org_id)
        teams = list_teams(org_id)
        missions = list_missions(org_id)
        
        # Load shared context
        repo = get_repository()
        network_needs = [n.to_dict() for n in repo.list_needs(status="OPEN")]
        network_ops = [o.to_dict() for o in repo.list_operations()]
        
        try:
            from agent.overrides import get_all_overrides
            overrides = get_all_overrides()
        except Exception:
            overrides = []
        
        result = analyze_need_for_org(
            org_id=org_id,
            need=need,
            private_resources=resources,
            private_teams=teams,
            private_missions=missions,
            network_needs=network_needs,
            network_operations=network_ops,
            network_overrides=overrides,
        )
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/agent/situation", methods=["GET"])
def api_org_agent_situation(org_id):
    """
    NGO Main Agent situation summary.
    
    Returns private + network summary with attention items.
    """
    try:
        from agent.agents.ngo_main_agent import get_org_situation
        from agent.org_workspace import list_resources, list_teams, list_missions
        from agent.data.repository import get_repository
        
        # Load private context
        resources = list_resources(org_id)
        teams = list_teams(org_id)
        missions = list_missions(org_id)
        
        # Load shared context
        repo = get_repository()
        network_needs = [n.to_dict() for n in repo.list_needs(status="OPEN")]
        network_ops = [o.to_dict() for o in repo.list_operations()]
        network_offers = [o.to_dict() for o in repo.list_resource_offers()]
        
        try:
            from agent.overrides import get_all_overrides
            overrides = get_all_overrides()
        except Exception:
            overrides = []
        
        result = get_org_situation(
            org_id=org_id,
            private_resources=resources,
            private_teams=teams,
            private_missions=missions,
            network_needs=network_needs,
            network_operations=network_ops,
            network_offers=network_offers,
            network_overrides=overrides,
        )
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/publish-offer", methods=["POST"])
def api_org_publish_offer(org_id):
    """
    Publish a resource offer from private inventory to the shared network.
    
    This is the critical privacy boundary: the user explicitly chooses
    what to publish. Private inventory is NOT automatically exposed.
    """
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import ResourceOffer, ActivityEvent, Organization
        from agent.org_workspace import update_resource
        
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        
        repo = get_repository()

        if not repo.get_organization(org_id):
            repo.create_organization(Organization(
                id=org_id,
                name=payload.get("organization_name") or org_id,
                organization_type=payload.get("organization_type", "ngo"),
                description=payload.get("organization_description", ""),
            ))

        # Create the public Resource Offer
        offer_id = f"offer_{str(uuid.uuid4())[:8]}"
        offer = ResourceOffer(
            id=offer_id,
            organization_id=org_id,
            resource_type=payload.get("resource_type", "other"),
            quantity=payload.get("quantity", 0),
            unit=payload.get("unit", "units"),
            lat=payload.get("lat"),
            lon=payload.get("lon"),
            location_name=payload.get("location_name"),
            district_id=payload.get("district_id"),
            status="OFFERED",
            notes=payload.get("notes", ""),
        )
        result = repo.create_resource_offer(offer)
        
        # Update private resource status if linked
        private_resource_id = payload.get("private_resource_id")
        if private_resource_id:
            update_resource(org_id, private_resource_id, {"status": "committed"})
        
        # Record activity
        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="resource_offer",
            entity_id=offer_id,
            event_type="resource_offered",
            actor=org_id,
            detail=f"Published offer: {offer.quantity} {offer.resource_type} from {org_id}",
        ))
        
        return jsonify({"offer": result.to_dict(), "message": "Offer published to network"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Activity Events endpoints
# ---------------------------------------------------------------------------

@app.route("/api/activity", methods=["GET"])
def api_list_activity():
    """List recent activity events."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        entity_type = request.args.get("entity_type")
        entity_id = request.args.get("entity_id")
        limit = int(request.args.get("limit", 50))
        events = repo.list_activity_events(
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )
        return jsonify({"events": [e.to_dict() for e in events]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Notifications endpoints
# ---------------------------------------------------------------------------

@app.route("/api/notifications", methods=["GET"])
def api_list_notifications():
    """List notifications for a user."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        recipient_id = request.args.get("recipient_id", "default_user")
        unread_only = request.args.get("unread_only", "false").lower() == "true"
        limit = int(request.args.get("limit", 50))
        notifs = repo.list_notifications(
            recipient_id=recipient_id,
            unread_only=unread_only,
            limit=limit,
        )
        return jsonify({"notifications": [n.to_dict() for n in notifs]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/notifications/<notif_id>/read", methods=["POST"])
def api_mark_notification_read(notif_id):
    """Mark a notification as read."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        repo.mark_notification_read(notif_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Matching endpoints (Need ↔ Offer collaboration)
# ---------------------------------------------------------------------------

@app.route("/api/needs/<need_id>/matches", methods=["GET"])
def api_need_matches(need_id):
    """
    Get deterministic candidate offers that match a given need.

    This does NOT create an operation — it produces proposed matches
    that require human confirmation.
    """
    try:
        from agent.data.repository import get_repository
        from agent.matching import find_matches_for_need

        repo = get_repository()
        need = repo.get_need(need_id)
        if not need:
            return jsonify({"error": "Need not found"}), 404

        # Get all active offers
        offers = repo.list_resource_offers(status="OFFERED")

        # Find matches
        candidates = find_matches_for_need(need, offers)

        # Enrich with full need/offer data for the frontend
        enriched = []
        for c in candidates:
            offer = repo.get_resource_offer(c.offer_id)
            offer_data = offer.to_dict() if offer else {}
            enriched.append({
                "need_id": c.need_id,
                "offer_id": c.offer_id,
                "compatibility": c.compatibility,
                "score": c.score,
                "match_type": c.match_type,
                "reasons": c.reasons,
                "unmet_quantity": c.unmet_quantity,
                "requested_quantity": c.requested_quantity,
                "available_quantity": c.available_quantity,
                "allocatable_quantity": c.allocatable_quantity,
                "offer": offer_data,
            })

        return jsonify({
            "need": need.to_dict(),
            "matches": enriched,
            "total_offers_checked": len(offers),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/matches/<need_id>/<offer_id>/confirm", methods=["POST"])
def api_confirm_match(need_id, offer_id):
    """
    Human confirms a proposed match → creates an Operation.

    This is the critical step: the human reviews the match and explicitly
    commits to the collaboration. Only then is an Operation created.
    """
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import Operation, ActivityEvent
        from datetime import datetime, timezone

        repo = get_repository()

        # Validate need exists
        need = repo.get_need(need_id)
        if not need:
            return jsonify({"error": "Need not found"}), 404

        # Validate offer exists
        offer = repo.get_resource_offer(offer_id)
        if not offer:
            return jsonify({"error": "Offer not found"}), 404

        # Check for existing operation for this need+offer pair (idempotent)
        existing_ops = repo.list_operations()
        for op in existing_ops:
            if op.need_id == need_id:
                op_meta = op.metadata or {}
                if op_meta.get("offer_id") == offer_id:
                    return jsonify({
                        "operation": op.to_dict(),
                        "message": "Collaboration already confirmed",
                    }), 200

        # Check offer is still available
        if offer.status != "OFFERED":
            return jsonify({"error": f"Offer is no longer available (status: {offer.status})"}), 409

        # Create the operation
        op_id = f"op_{str(uuid.uuid4())[:8]}"
        op_name = f"Collaboration: {need.title or need.need_type} + {offer.resource_type}"

        op = Operation(
            id=op_id,
            name=op_name,
            operation_type="collaboration",
            description=f"Collaboration between need '{need.title or need.need_type}' "
                        f"and offer of {offer.quantity} {offer.resource_type} "
                        f"from {offer.organization_id}",
            need_id=need_id,
            lead_organization_id=offer.organization_id,
            district_id=need.district_id or offer.district_id,
            lat=need.lat or offer.lat,
            lon=need.lon or offer.lon,
            location_name=need.location_name or offer.location_name,
            status="PLANNING",
            metadata={
                "offer_id": offer_id,
                "need_type": need.need_type,
                "resource_type": offer.resource_type,
                "quantity_committed": min(
                    offer.quantity,
                    _extract_offer_quantity(need, offer),
                ),
                "organization_id": offer.organization_id,
            },
        )
        result = repo.create_operation(op)

        # Update offer status to ACCEPTED
        offer.status = "ACCEPTED"
        repo.update_resource_offer(offer)

        # Update need status
        need.status = "RESPONDING"
        need.updated_at = datetime.now(timezone.utc)
        repo.update_need(need)

        # Record activity events
        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="operation",
            entity_id=op_id,
            event_type="match_confirmed",
            actor="coordinator",
            detail=f"Collaboration confirmed: {op.name}",
        ))
        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="operation",
            entity_id=op_id,
            event_type="operation_created",
            actor=offer.organization_id,
            detail=f"Operation created: {op.name}",
        ))

        return jsonify({
            "operation": result.to_dict(),
            "message": "Collaboration confirmed and Operation created",
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _extract_offer_quantity(need, offer) -> int:
    """Extract requested quantity from the need for capacity calculation."""
    if not need.requested_resources:
        return 0
    for r in need.requested_resources:
        rtype = r.get("type", r.get("resource_type", "")).lower()
        if (need.need_type.lower() in rtype or rtype in need.need_type.lower()):
            qty = r.get("quantity", 0)
            if isinstance(qty, (int, float)):
                return int(qty)
    return 0


# ---------------------------------------------------------------------------
# Planner endpoint (reuse existing planner.py)
# ---------------------------------------------------------------------------

@app.route("/api/planner", methods=["POST"])
def api_planner():
    """Run the operational planner on a natural language query."""
    try:
        from agent.planner import plan_operation

        payload = request.get_json(force=True, silent=True)
        if not payload or not payload.get("query"):
            return jsonify({"error": "Body must include 'query'"}), 400

        raw_query = payload["query"].strip()
        if not raw_query:
            return jsonify({"error": "Query cannot be empty"}), 400

        result = plan_operation(raw_query)

        return jsonify({
            "recommendation": result.recommendation,
            "why": result.why,
            "evidence": result.evidence,
            "constraints": result.constraints,
            "uncertainty": result.uncertainty,
            "data_gaps": result.data_gaps,
            "tools_used": result.tools_used,
            "ranked_locations": result.ranked_locations,
            "allocation_plan": result.allocation_plan,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# AI Coordinator endpoint (Phase 7B v1)
# ---------------------------------------------------------------------------

@app.route("/api/ai-coordinator/analysis", methods=["GET"])
def api_ai_coordinator_analysis():
    """
    Read-only AI Coordinator analysis endpoint.

    Returns structured findings based on current operational state:
    - Coordination gaps (uncovered needs)
    - Duplicate responses (multiple orgs on same need)
    - Consequence alerts (overrides affecting active operations)

    This endpoint performs NO writes.
    """
    try:
        from agent.ai_coordinator import run_coordinator_analysis
        result = run_coordinator_analysis()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Coordination endpoints (Phase 7H)
# ---------------------------------------------------------------------------

@app.route("/api/network/coordination/propose", methods=["POST"])
def api_coordination_propose():
    """
    Create a coordination proposal for a Need.
    
    Body: {"need": {...}, "organization_id": "...", "organization_name": "..."}
    
    This does NOT publish anything — it creates a proposal for review.
    """
    try:
        from agent.coordination.proposal import create_proposal
        from agent.coordination.candidate_selection import select_candidates
        from agent.data.repository import get_repository
        
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        
        need = payload.get("need", {})
        org_id = payload.get("organization_id")
        org_name = payload.get("organization_name", org_id)
        
        if not org_id:
            return jsonify({"error": "organization_id required"}), 400
        
        # Find candidates (uses public info only)
        repo = get_repository()
        candidates = select_candidates(need, repo)
        
        # Create proposal
        proposal = create_proposal(
            need_id=need.get("id", ""),
            organization_id=org_id,
            organization_name=org_name,
            proposal_type=need.get("need_type", "other"),
            summary=f"Coordination proposal for {need.get('title', need.get('need_type', ''))}",
            public_evidence=[{"type": "candidate_selection", "detail": f"{len(candidates)} candidate(s) identified"}],
            network_findings=[{"type": "need_analysis", "detail": f"Need requires {need.get('need_type', '')} support"}],
        )
        
        # Record activity
        from agent.data.models import ActivityEvent
        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="coordination",
            entity_id=proposal["id"],
            event_type="coordination_proposed",
            actor="network_agent",
            detail=f"Coordination proposal created for Need {need.get('id', '')} → {org_name}",
        ))
        
        return jsonify({"proposal": proposal, "candidates": candidates}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/network/coordination/proposals", methods=["GET"])
def api_list_proposals():
    """List coordination proposals."""
    try:
        from agent.coordination.proposal import list_proposals, get_public_view
        need_id = request.args.get("need_id")
        org_id = request.args.get("organization_id")
        status = request.args.get("status")
        proposals = list_proposals(need_id=need_id, organization_id=org_id, status=status)
        # Return public view only
        return jsonify({"proposals": [get_public_view(p) for p in proposals]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/network/coordination/proposals/<proposal_id>", methods=["GET"])
def api_get_proposal(proposal_id):
    """Get a specific proposal."""
    try:
        from agent.coordination.proposal import get_proposal, get_public_view
        proposal = get_proposal(proposal_id)
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404
        return jsonify({"proposal": get_public_view(proposal)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/network/coordination/proposals/<proposal_id>/send-to-org", methods=["POST"])
def api_send_proposal_to_org(proposal_id):
    """Send proposal to NGO for evaluation."""
    try:
        from agent.coordination.proposal import send_to_org
        proposal = send_to_org(proposal_id)
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404
        return jsonify({"proposal": proposal})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/agent/evaluate-coordination", methods=["POST"])
def api_org_evaluate_coordination(org_id):
    """
    NGO Main Agent privately evaluates a coordination proposal.
    
    Body: {"proposal_id": "..."}
    
    Returns evaluation (private factors are stored but NOT exposed in response).
    """
    try:
        from agent.coordination.proposal import get_proposal, record_org_evaluation
        from agent.coordination.ngo_evaluation import evaluate_coordination
        
        payload = request.get_json(force=True, silent=True)
        if not payload or not payload.get("proposal_id"):
            return jsonify({"error": "proposal_id required"}), 400
        
        proposal = get_proposal(payload["proposal_id"])
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404
        
        # Evaluate using private state
        evaluation = evaluate_coordination(proposal, org_id)
        
        # Record evaluation (private_factors stored but not exposed)
        record_org_evaluation(
            proposal["id"],
            evaluation=evaluation,
            private_factors=evaluation.get("private_factors", []),
        )
        
        # Return PUBLIC parts only
        from agent.coordination.publication import extract_public_fields
        public_eval = extract_public_fields(evaluation)
        
        # Record activity
        from agent.data.repository import get_repository
        from agent.data.models import ActivityEvent
        repo = get_repository()
        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="coordination",
            entity_id=proposal["id"],
            event_type="organization_evaluation_completed",
            actor=org_id,
            detail=f"Organization {org_id} evaluated proposal: {evaluation.get('decision', '')}",
        ))
        
        return jsonify({"evaluation": public_eval, "proposal_id": proposal["id"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/orgs/<org_id>/agent/approve-publication", methods=["POST"])
def api_org_approve_publication(org_id):
    """
    Human-approved publication of proposed response.
    
    Body: {"proposal_id": "..."}
    
    Creates a public Resource Offer from the approved proposal.
    """
    try:
        from agent.coordination.proposal import get_proposal, approve_publication, link_offer
        from agent.coordination.publication import create_public_offer_from_proposal
        from agent.data.repository import get_repository
        
        payload = request.get_json(force=True, silent=True)
        if not payload or not payload.get("proposal_id"):
            return jsonify({"error": "proposal_id required"}), 400
        
        proposal = get_proposal(payload["proposal_id"])
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404
        
        if not proposal.get("org_evaluation"):
            return jsonify({"error": "No evaluation recorded for this proposal"}), 400
        
        # Approve
        approve_publication(proposal["id"], approved_by="human")
        
        # Create public offer
        repo = get_repository()
        result = create_public_offer_from_proposal(
            proposal=proposal,
            org_evaluation=proposal["org_evaluation"],
            org_id=org_id,
            repo=repo,
        )
        
        if result.get("offer"):
            link_offer(proposal["id"], result["offer"]["id"])
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/network/coordination/proposals/<proposal_id>/decline", methods=["POST"])
def api_decline_proposal(proposal_id):
    """Decline a coordination proposal."""
    try:
        from agent.coordination.proposal import decline_proposal
        proposal = decline_proposal(proposal_id)
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404
        return jsonify({"proposal": proposal})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Network Main Agent endpoints (Phase 7G)
# ---------------------------------------------------------------------------

@app.route("/api/network/agent/analyze", methods=["GET"])
def api_network_agent_analyze():
    """
    Run full Network Main Agent analysis.
    
    Returns structured findings, evidence, uncertainty, and recommended actions.
    This endpoint performs NO writes.
    """
    try:
        from agent.agents.network_main_agent import run_network_analysis
        result = run_network_analysis()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/network/agent/analyze-need", methods=["POST"])
def api_network_agent_analyze_need():
    """
    Analyze a specific need in network context.
    
    Body: {"need": {...}} — the full need dict.
    
    Returns evidence, access, coordination, and recommendations.
    This endpoint performs NO writes.
    """
    try:
        from agent.agents.network_main_agent import analyze_need_in_network
        payload = request.get_json(force=True, silent=True)
        if not payload or not payload.get("need"):
            return jsonify({"error": "Body must include 'need'"}), 400
        result = analyze_need_in_network(payload["need"])
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/network/agent/situation", methods=["GET"])
def api_network_agent_situation():
    """
    Get network situation summary from the Network Main Agent.
    
    This endpoint performs NO writes.
    """
    try:
        from agent.agents.network_main_agent import run_network_analysis
        result = run_network_analysis()
        # Return just the summary and priority items
        return jsonify({
            "generated_at": result.get("generated_at"),
            "summary": result.get("summary"),
            "situation": result.get("situation"),
            "priority_needs": result.get("priority_needs"),
            "risks": result.get("risks"),
            "severity_summary": result.get("severity_summary"),
            "recommended_actions": result.get("recommended_actions"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Delta Engine endpoint (Phase 7D)
# ---------------------------------------------------------------------------

@app.route("/api/delta", methods=["GET"])
def api_delta():
    """
    Compute and return the current delta — what changed in the operational state.
    
    Query parameters:
        hours: lookback period in hours (default 24)
    
    This endpoint performs NO writes.
    """
    try:
        from agent.delta import compute_delta
        hours = float(request.args.get('hours', 24.0))
        from agent.data.repository import get_repository
        result = compute_delta(get_repository(), lookback_hours=hours)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/evidence/<entity_type>/<entity_id>", methods=["GET"])
def api_evidence(entity_type, entity_id):
    """
    Synthesize evidence for a specific operational entity.
    
    Returns evidence items, uncertainty, data gaps, and confidence.
    
    This endpoint performs NO writes.
    """
    try:
        from agent.delta import synthesize_evidence
        result = synthesize_evidence(entity_type, entity_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Flood History snapshots endpoint
# ---------------------------------------------------------------------------

@app.route("/api/flood-snapshots", methods=["GET"])
def api_flood_snapshots():
    """
    List all available flood snapshots for the temporal flood history.

    Returns metadata (no geometry) for each snapshot:
      id, district_id, observed_at, source, confidence, polygon_count
    """
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        district_id = request.args.get("district")
        snapshots = repo.list_flood_snapshots(district_id=district_id)
        return jsonify({
            "snapshots": [
                {
                    "id": s.id,
                    "district_id": s.district_id,
                    "observed_at": s.observed_at.isoformat() if hasattr(s.observed_at, 'isoformat') else str(s.observed_at),
                    "source": s.source,
                    "confidence": s.confidence,
                    "polygon_count": s.polygon_count,
                    "provenance": s.provenance.value if hasattr(s, 'provenance') else "REAL",
                }
                for s in snapshots
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/flood-snapshots/<snapshot_id>/geojson", methods=["GET"])
def api_flood_snapshot_geojson(snapshot_id):
    """Return the GeoJSON geometry for a specific flood snapshot."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        snapshot = repo.get_flood_snapshot(snapshot_id)
        if not snapshot:
            return jsonify({"error": "Snapshot not found"}), 404
        if snapshot.geometry_geojson:
            return jsonify(snapshot.geometry_geojson)
        return jsonify({"type": "FeatureCollection", "features": []})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Incidents endpoint (empty state — no incident dataset exists)
# ---------------------------------------------------------------------------

@app.route("/api/incidents", methods=["GET"])
def api_list_incidents():
    """
    Return incidents list.

    No incident dataset currently exists in the database.
    Returns an explicit empty state rather than silently returning nothing.
    """
    return jsonify({
        "incidents": [],
        "message": "No active incidents recorded. Incidents will appear here when field teams or the AI coordinator log operational incidents.",
        "status": "empty",
    })


# ---------------------------------------------------------------------------
# Register building routes
# ---------------------------------------------------------------------------

from agent.api_buildings import register_building_routes
register_building_routes(app)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Starting ReliefOS API on http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
