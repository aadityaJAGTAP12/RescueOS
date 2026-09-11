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

from dotenv import load_dotenv

# Automatically load environment variables from .env file at repo root
load_dotenv()

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
from agent.org_context import resolve_current_org, set_current_org_cookie
from agent.data_loader import FLOOD_DATA, get_flood_data, get_all_known_locations


# ---------------------------------------------------------------------------
# App setup & Production Middleware
# ---------------------------------------------------------------------------

from agent.middleware import register_observability_middleware, register_security_middleware
from agent.auth import (
    AuthService,
    require_auth,
    require_org_role,
    require_network_operator,
    resolve_request_principal,
    is_auth_enforced,
    UserRole,
)
from agent.audit import record_audit_log as _record_audit_log
from agent.validation.validators import (
    ValidationError,
    validate_id,
    validate_coordinates,
    validate_pagination,
    validate_urgency,
    validate_need_status,
    validate_offer_status,
    validate_operation_status,
    validate_need_payload,
    validate_offer_payload,
    sanitize_text,
)


def _api_error(e: Exception, status: int = 500):
    """Sanitized internal error response.

    Never leaks exception text, SQL, paths, or config in any environment:
    full detail stays on the server side via the logging handlers.
    """
    if hasattr(g, "request_id"):
        logger.warning(
            "[RequestID: %s] endpoint error (%s): %s",
            g.request_id, type(e).__name__, e,
        )
    return jsonify({"error": f"{type(e).__name__}: internal error"}), status


_AUTH_COOKIE_MAX_AGE = 86400


def _set_auth_cookie(resp, token: str):
    """Attach the session token cookie with production-appropriate flags."""
    secure = is_auth_enforced()
    resp.set_cookie(
        "reliefos_auth_token",
        token,
        max_age=_AUTH_COOKIE_MAX_AGE,
        samesite="Lax",
        httponly=True,
        secure=secure,
    )
    return resp


def _clear_auth_cookie(resp):
    secure = is_auth_enforced()
    resp.set_cookie(
        "reliefos_auth_token", "", max_age=0, samesite="Lax", httponly=True, secure=secure
    )
    return resp


from agent.audit import record_audit_log
from agent.data.repository import get_repository
from flask import g

import logging as _logging
logger = _logging.getLogger("reliefos.api")

app = Flask(__name__)

# CORS: allow-list only explicitly trusted origins. supports_credentials is
# required for the session/auth cookies; an unrestricted origin list with
# credentials would let any site ride an operator's session.
from agent.config import get_settings as _get_settings
_settings = _get_settings()
CORS(
    app,
    resources={r"/api/*": {"origins": _settings.cors_allowed_origins}},
    supports_credentials=True,
)

# Register security headers and observability request tracing
register_observability_middleware(app)
register_security_middleware(app)

# Initialize AuthService on the Flask app
app.auth_service = AuthService(repository=get_repository())



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
# Health, Auth & Observability Endpoints — Production Hardening
# ---------------------------------------------------------------------------

@app.route("/api/health/liveness", methods=["GET"])
def api_health_liveness():
    """Liveness probe: verifies process is running and accepting HTTP requests."""
    from agent.config import get_settings
    return jsonify({
        "status": "alive",
        "service": "reliefos-backend",
        "environment": get_settings().environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 200


@app.route("/api/health/readiness", methods=["GET"])
def api_health_readiness():
    """Readiness probe: verifies repository connectivity and basic operational health."""
    from agent.config import get_settings
    settings = get_settings()
    repo = get_repository()
    try:
        settlements_count = len(repo.list_settlements()) if hasattr(repo, "list_settlements") else 0
        return jsonify({
            "status": "ready",
            "database": "connected",
            "repository": type(repo).__name__,
            "settlements_count": settlements_count,
            "environment": settings.environment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 200
    except Exception as e:
        # Log detail server-side; never expose DB errors (connection strings,
        # host names) through the probe.
        logger.error("Readiness check failed: %s", e)
        return jsonify({
            "status": "unhealthy",
            "database": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 503


@app.route("/api/auth/register", methods=["POST"])
def api_auth_register():
    """Register a new user and assign initial organization membership."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    email = data.get("email", "").strip()
    full_name = data.get("full_name", "").strip()
    initial_org_id = data.get("initial_org_id")
    initial_role = data.get("initial_role", UserRole.ORG_OPERATOR.value)

    if not username or not password:
        return jsonify({"error": "Username and password are required", "code": "VALIDATION_ERROR"}), 400

    # Fail closed: in production, self-service org binding via registration
    # is disabled — memberships must be granted by a NETWORK_OPERATOR.
    if is_auth_enforced() and initial_org_id:
        return jsonify({"error": "Organization binding requires a network operator", "code": "FORBIDDEN"}), 403

    try:
        user, membership = app.auth_service.register_user(
            username=username,
            email=email,
            password=password,
            full_name=full_name,
            initial_org_id=initial_org_id,
            initial_role=initial_role,
        )
        token = app.auth_service.create_token_for_user(user)

        repo = get_repository()
        record_audit_log(
            repo,
            action="register_user",
            entity_type="user",
            entity_id=user.id,
            organization_id=initial_org_id,
            details={"username": username, "email": email, "role": initial_role if membership else None},
        )

        resp = jsonify({
            "token": token,
            "user": user.to_dict(),
            "membership": membership.to_dict() if membership else None,
        })
        _set_auth_cookie(resp, token)
        if initial_org_id:
            set_current_org_cookie(resp, initial_org_id)
        return resp, 201
    except ValueError as e:
        return jsonify({"error": str(e), "code": "REGISTRATION_FAILED"}), 400
    except Exception as e:
        return _api_error(e)


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    """Authenticate user with username/email and password."""
    data = request.get_json(silent=True) or {}
    username_or_email = data.get("username") or data.get("email") or ""
    password = data.get("password", "")

    if not username_or_email or not password:
        return jsonify({"error": "Username/email and password required", "code": "VALIDATION_ERROR"}), 400

    user = app.auth_service.authenticate(username_or_email, password)
    if not user:
        return jsonify({"error": "Invalid username or password", "code": "INVALID_CREDENTIALS"}), 401

    principal = app.auth_service.get_principal(user.id)
    token = app.auth_service.create_token_for_user(user)

    repo = get_repository()
    record_audit_log(
        repo,
        action="login_success",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        details={"username": user.username},
    )

    resp = jsonify({
        "token": token,
        "user": user.to_dict(),
        "memberships": [m.to_dict() for m in (principal.memberships if principal else [])],
        "is_network_operator": principal.is_network_operator if principal else False,
    })
    _set_auth_cookie(resp, token)
    if principal and principal.memberships:
        set_current_org_cookie(resp, principal.memberships[0].organization_id)
    return resp, 200


@app.route("/api/auth/me", methods=["GET"])
def api_auth_me():
    """Retrieve current authenticated user context and organization memberships."""
    principal = resolve_request_principal(request)
    if not principal:
        if is_auth_enforced():
            return jsonify({"error": "Authentication required", "code": "UNAUTHORIZED"}), 401
        return jsonify({
            "authenticated": False,
            "user": None,
            "memberships": [],
            "is_network_operator": False,
        }), 200

    return jsonify({
        "authenticated": True,
        "user": principal.user.to_dict(),
        "memberships": [m.to_dict() for m in principal.memberships],
        "is_network_operator": principal.is_network_operator,
    }), 200


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    """Log out current user and clear authentication cookies."""
    principal = resolve_request_principal(request)
    if principal:
        repo = get_repository()
        record_audit_log(
            repo,
            action="logout",
            entity_type="user",
            entity_id=principal.user_id,
            actor_id=principal.user_id,
        )

    resp = jsonify({"status": "logged_out"})
    _clear_auth_cookie(resp)
    return resp, 200


@app.route("/api/audit/logs", methods=["GET"])
@require_network_operator
def api_audit_logs():
    """List consequential action audit records with pagination and filtering."""
    from agent.validation import validate_pagination
    limit, offset = validate_pagination(
        request.args.get("limit", 50),
        request.args.get("offset", 0),
    )
    entity_type = request.args.get("entity_type")
    action = request.args.get("action")
    org_id = request.args.get("organization_id")
    actor_id = request.args.get("actor_id")

    repo = get_repository()
    logs = repo.list_audit_logs(
        entity_type=entity_type,
        action=action,
        organization_id=org_id,
        actor_id=actor_id,
        limit=limit,
        offset=offset,
    )
    return jsonify({
        "logs": [log.to_dict() for log in logs],
        "count": len(logs),
        "limit": limit,
        "offset": offset,
    })


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

    try:
        raw_text = payload["raw_text"]

        # Extract structured fields via LLM
        extraction = extract_field_report(raw_text)

        # Store the report (with coordinates if explicitly provided, else unresolved text)
        lat = payload.get("lat")
        lon = payload.get("lon")
        store_result = submit_field_intelligence(extraction, lat=float(lat) if lat is not None else None, lon=float(lon) if lon is not None else None)

        # Consequential: a new field report enters the shared operational state.
        if store_result.get("success") and store_result.get("report_id"):
            try:
                record_audit_log(
                    get_repository(),
                    action="submit_field_report",
                    entity_type="field_report",
                    entity_id=store_result["report_id"],
                    organization_id=None,
                    details={"source": "field_intelligence_text", "confidence": extraction.get("confidence", 0.7)},
                )
            except Exception:
                logger.warning("Field report audit logging failed", exc_info=True)

            try:
                from agent.agents.events import make_field_report_event
                get_repository().append_agent_event(make_field_report_event(
                    report_id=store_result["report_id"],
                    district=extraction.get("district"),
                    metadata={"raw_text": raw_text[:200], "confidence": extraction.get("confidence", 0.7)},
                ))
            except Exception:
                pass

        return jsonify({
            "extraction": extraction,
            "store_result": store_result,
        })
    except Exception as e:
        return _api_error(e)


@app.route("/api/field-intelligence/history", methods=["GET"])
@require_auth
def api_field_intelligence_history():
    """Return all field intelligence reports."""
    all_reports = get_all_reports()
    fi_reports = [r for r in all_reports if r.get("source") == "field_intelligence_text"]
    return jsonify({"reports": fi_reports})


# ---------------------------------------------------------------------------
# Override endpoints
# ---------------------------------------------------------------------------

@app.route("/api/override", methods=["POST"])
@require_network_operator
def api_apply_override():
    """
    Apply a manual override to a facility or road status.
    Body: {target_type, target_id, new_status, reason, actor?}
    """
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "Invalid JSON body"}), 400

    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    new_status = payload.get("new_status")
    reason = payload.get("reason", "")
    # Audit trail: honor the caller-supplied actor; fall back to the
    # codebase-wide default ("coordinator") when absent or empty.
    actor = (payload.get("actor") or "").strip() or "coordinator"

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
        actor=actor,
        system_status=system_status,
    )

    try:
        from agent.data.repository import get_repository
        record_audit_log(
            get_repository(),
            action="apply_override",
            entity_type="override",
            entity_id=record.get("id", f"{target_type}:{target_id}"),
            actor_id=actor,
            from_state=system_status,
            to_state=new_status,
            details={"target_type": target_type, "target_id": target_id, "reason": reason},
        )
    except Exception:
        pass

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
        return _api_error(e)


@app.route("/api/districts/<district_id>/flood-geojson", methods=["GET"])
def api_district_flood_geojson(district_id):
    """Return flood GeoJSON for a specific district (precision-reduced, gzip-negotiated, cached)."""
    flood_data = _flood_geojson_payload(district_id)
    return _flood_geojson_response(flood_data, scope=f"d:{district_id}")


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
        return _api_error(e)


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
        return _api_error(e)


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
        return _api_error(e)


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
        return _api_error(e)


@app.route("/api/districts/<district_id>/medical-facilities", methods=["GET"])
def api_district_medical_facilities(district_id):
    """Return real medical facilities for a district."""
    try:
        from agent.data.repository import get_repository
        facilities = get_repository().get_medical_facilities(district_id)
        return jsonify({"facilities": [f.to_dict() for f in facilities], "count": len(facilities)})
    except Exception as e:
        return _api_error(e)


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
        return _api_error(e)


@app.route("/api/needs", methods=["POST"])
@require_auth
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

        # Input validation (production hardening): normalize and bound the
        # client-supplied fields before they reach the domain layer.
        try:
            payload = {**payload, **validate_need_payload(payload)}
            if payload.get("district_id"):
                validate_id(payload["district_id"], "district_id")
        except ValidationError as ve:
            return jsonify({"error": str(ve), "code": "VALIDATION_ERROR"}), 400

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
        from agent.data.models import ActivityEvent, Notification
        from agent.agents.events import make_need_created_event, make_need_status_changed_event
        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="need",
            entity_id=need_id,
            event_type="need_created",
            actor=payload.get("reporter_id", "anonymous"),
            detail=f"Need created: {need.title}",
        ))

        # Emit machine-facing AgentEvent outbox record
        repo.append_agent_event(make_need_created_event(
            need_id=need_id,
            district=need.district_id,
            priority="critical" if need.urgency == "critical" else "urgent",
            metadata={"title": need.title, "need_type": need.need_type, "urgency": need.urgency},
        ))

        # Audit: need creation is a consequential operational action.
        record_audit_log(
            repo,
            action="create_need",
            entity_type="need",
            entity_id=need_id,
            details={"title": need.title, "urgency": need.urgency, "district_id": need.district_id},
        )

        # Emit notification for critical needs
        if need.urgency == "critical":
            repo.create_notification(Notification(
                id=f"notif_{str(uuid.uuid4())[:8]}",
                recipient_id="network",
                notification_type="urgent_need",
                title="Critical Need Reported",
                message=f"Critical need '{need.title}' reported in {need.district_id or 'network'}.",
                entity_type="need",
                entity_id=need_id,
                metadata={"district_id": need.district_id, "urgency": "critical"},
            ))

        return jsonify({"need": result.to_dict()}), 201
    except Exception as e:
        return _api_error(e)


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
        return _api_error(e)


@app.route("/api/needs/<need_id>", methods=["PATCH"])
@require_auth
def api_update_need(need_id):
    """Update a need (status, description, etc.)."""
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import ActivityEvent
        from agent.agents.events import make_need_status_changed_event
        repo = get_repository()
        need = repo.get_need(need_id)
        if not need:
            return jsonify({"error": "Need not found"}), 404

        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400

        # Input validation (production hardening)
        try:
            if "status" in payload:
                payload["status"] = validate_need_status(payload["status"], current_status=need.status)
            if "urgency" in payload:
                payload["urgency"] = validate_urgency(payload["urgency"])
            if "title" in payload:
                payload["title"] = sanitize_text(payload["title"], 512)
            if "description" in payload:
                payload["description"] = sanitize_text(payload["description"], 4000)
            if "requested_resources" in payload:
                payload = {**payload, **validate_need_payload({"requested_resources": payload["requested_resources"]})}
        except ValidationError as ve:
            return jsonify({"error": str(ve), "code": "VALIDATION_ERROR"}), 400

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
            # Emit machine-facing AgentEvent outbox record
            repo.append_agent_event(make_need_status_changed_event(
                need_id=need_id,
                old_status=old_status,
                new_status=new_status,
                district=need.district_id,
            ))
            record_audit_log(
                repo,
                action="update_need_status",
                entity_type="need",
                entity_id=need_id,
                organization_id=None,
                from_state=old_status,
                to_state=new_status,
                details={"title": need.title},
            )
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
        return _api_error(e)


# ---------------------------------------------------------------------------
# Coordination proposal endpoints
# ---------------------------------------------------------------------------

@app.route("/api/proposals", methods=["GET"])


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
        return _api_error(e)


@app.route("/api/offers", methods=["POST"])
@require_org_role(UserRole.ORG_OPERATOR)
def api_create_offer():
    """Publish a new resource offer.

    The offering organization is derived server-side via the identity seam
    (resolve_current_org) — a client-supplied organization_id in the body is
    NEVER honored for this privileged action.
    """
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import ResourceOffer, ActivityEvent, Organization
        repo = get_repository()

        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400

        # Input validation (production hardening)
        try:
            payload = {**payload, **validate_offer_payload(payload)}
        except ValidationError as ve:
            return jsonify({"error": str(ve), "code": "VALIDATION_ERROR"}), 400

        organization_id = resolve_current_org(request)
        if not repo.get_organization(organization_id):
            repo.create_organization(Organization(
                id=organization_id,
                name="ReliefOS Coordination Cell",
                organization_type="coordinator",
                description="Default local organization for ReliefOS workspace actions.",
            ))

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

        # Record activity
        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="resource_offer",
            entity_id=offer_id,
            event_type="resource_offered",
            actor=organization_id,
            detail=f"Resource offer published: {offer.quantity} {offer.resource_type}",
        ))

        # Emit machine-facing AgentEvent
        from agent.agents.events import make_offer_created_event, make_offer_status_changed_event
        repo.append_agent_event(make_offer_created_event(
            offer_id=offer_id,
            org_id=organization_id,
            district=offer.district_id,
            metadata={"resource_type": offer.resource_type, "quantity": offer.quantity},
        ))

        # Audit Log
        record_audit_log(
            repo,
            action="publish_offer",
            entity_type="offer",
            entity_id=offer_id,
            organization_id=organization_id,
            to_state="OFFERED",
            details={"resource_type": offer.resource_type, "quantity": offer.quantity, "district_id": offer.district_id},
        )

        return jsonify({"offer": result.to_dict()}), 201
    except Exception as e:
        return _api_error(e)


@app.route("/api/offers/<offer_id>", methods=["PATCH"])
@require_org_role(UserRole.ORG_OPERATOR)
def api_update_offer(offer_id):
    """Update a resource offer."""
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import ActivityEvent
        from agent.agents.events import make_offer_status_changed_event
        from datetime import datetime, timezone
        repo = get_repository()
        offer = repo.get_resource_offer(offer_id)
        if not offer:
            return jsonify({"error": "Offer not found"}), 404

        # Cross-org integrity: an authenticated user may only modify offers
        # belonging to their own resolved org context (network operators
        # excepted). 403 in enforced mode; dev/test keeps legacy behavior.
        session_org = resolve_current_org(request)
        principal = resolve_request_principal(request)
        if offer.organization_id != session_org and not (
            principal and principal.is_network_operator
        ):
            if is_auth_enforced():
                logger.warning(
                    "[RequestID: %s] authz denied: offer=%s belongs to %s, session org=%s",
                    getattr(g, "request_id", "-"), offer_id, offer.organization_id, session_org,
                )
                return jsonify({"error": "Not authorized to modify this offer", "code": "FORBIDDEN"}), 403

        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400

        # Input validation (production hardening)
        try:
            if "status" in payload:
                payload["status"] = validate_offer_status(payload["status"])
            if "quantity" in payload:
                payload["quantity"] = validate_quantity(payload["quantity"])
            if "notes" in payload:
                payload["notes"] = sanitize_text(payload["notes"], 2000)
        except ValidationError as ve:
            return jsonify({"error": str(ve), "code": "VALIDATION_ERROR"}), 400

        old_status = offer.status
        if "status" in payload:
            offer.status = payload["status"]
            repo.append_activity_event(ActivityEvent(
                id=f"evt_{str(uuid.uuid4())[:8]}",
                entity_type="resource_offer",
                entity_id=offer_id,
                event_type="status_changed",
                actor=payload.get("actor", offer.organization_id),
                detail=f"Offer status changed: {old_status} → {offer.status}",
            ))
            repo.append_agent_event(make_offer_status_changed_event(
                offer_id=offer_id,
                old_status=old_status,
                new_status=offer.status,
                org_id=offer.organization_id,
                district=offer.district_id,
            ))
        if "quantity" in payload:
            offer.quantity = payload["quantity"]
        if "notes" in payload:
            offer.notes = payload["notes"]

        offer.updated_at = datetime.now(timezone.utc)
        repo.update_resource_offer(offer)

        # Audit log
        record_audit_log(
            repo,
            action="update_offer",
            entity_type="offer",
            entity_id=offer_id,
            organization_id=offer.organization_id,
            from_state=old_status,
            to_state=offer.status,
            details={"updated_fields": list(payload.keys())},
        )

        return jsonify({"offer": offer.to_dict()})
    except Exception as e:
        return _api_error(e)


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
        return _api_error(e)


@app.route("/api/operations", methods=["POST"])
@require_auth
def api_create_operation():
    """Create a new operation."""
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import Operation, ActivityEvent
        from agent.agents.events import make_operation_created_event, make_operation_status_changed_event
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

        repo.append_agent_event(make_operation_created_event(
            operation_id=op_id,
            district=op.district_id,
            org_id=op.lead_organization_id,
            metadata={"name": op.name, "operation_type": op.operation_type},
        ))

        return jsonify({"operation": result.to_dict()}), 201
    except Exception as e:
        return _api_error(e)


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
        return _api_error(e)


@app.route("/api/operations/<op_id>", methods=["PATCH"])
@require_auth
def api_update_operation(op_id):
    """Update an operation."""
    try:
        import uuid
        from agent.data.repository import get_repository
        from agent.data.models import ActivityEvent
        from agent.agents.events import make_operation_status_changed_event
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
            repo.append_agent_event(make_operation_status_changed_event(
                operation_id=op_id,
                old_status=old_status,
                new_status=new_status,
                district=op.district_id,
                org_id=op.lead_organization_id,
            ))
            record_audit_log(
                repo,
                action="update_operation_status",
                entity_type="operation",
                entity_id=op_id,
                organization_id=op.lead_organization_id,
                from_state=old_status,
                to_state=new_status,
                details={"name": op.name},
            )
        if "name" in payload:
            op.name = payload["name"]
        if "description" in payload:
            op.description = payload["description"]

        op.updated_at = datetime.now(timezone.utc)
        repo.update_operation(op)
        return jsonify({"operation": op.to_dict()})
    except Exception as e:
        return _api_error(e)


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
        return _api_error(e)


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
        return _api_error(e)


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
        return _api_error(e)


# ---------------------------------------------------------------------------
# Organization session context (identity seam)
#
# IDENTITY / CONTEXT ONLY — NOT AUTHENTICATION. There is no password and no
# credential: anyone may select any organization. See agent/org_context.py
# for the full trust-boundary documentation. The org id is NEVER taken from
# the URL path, query string, or request body for org-scoped actions — all
# org-scoped handlers below derive it via resolve_current_org(request).
# ---------------------------------------------------------------------------

@app.route("/api/session/org", methods=["GET"])
def api_get_session_org():
    """Return the currently resolved org context + registered orgs (for the picker)."""
    try:
        from agent.data.repository import get_repository
        org_id = resolve_current_org(request)
        repo = get_repository()
        orgs = repo.list_organizations(active_only=True)
        return jsonify({
            "org_id": org_id,
            "registered": any(o.id == org_id for o in orgs),
            "organizations": [o.to_dict() for o in orgs],
        })
    except Exception as e:
        return _api_error(e)


@app.route("/api/session/org", methods=["POST"])
def api_set_session_org():
    """
    Select the organization context for this browser (identity seam).

    Body: {"org_id": "..."} — must be a registered organization (create one
    first via POST /api/organizations). Sets the plain reliefos_org_id cookie.
    This is a UI preference, NOT a login — see agent/org_context.py.
    """
    try:
        from agent.data.repository import get_repository
        payload = request.get_json(force=True, silent=True)
        if not payload or not payload.get("org_id"):
            return jsonify({"error": "org_id required"}), 400
        org_id = str(payload["org_id"]).strip()
        try:
            validate_id(org_id, "org_id")
        except ValidationError as ve:
            return jsonify({"error": str(ve), "code": "VALIDATION_ERROR"}), 400
        repo = get_repository()
        org = repo.get_organization(org_id)
        if not org:
            return jsonify({"error": f"Organization not found: {org_id}"}), 404

        # Fail closed: with authentication enforced, a user may only select
        # an organization they hold a membership in (or any org if they are a
        # NETWORK_OPERATOR). The cookie is a preference, not a credential.
        principal = resolve_request_principal(request)
        if is_auth_enforced():
            # Unauthenticated org selection must fail closed — otherwise an
            # anonymous caller could steer org-scoped traffic at any org.
            if not principal:
                return jsonify({"error": "Authentication required", "code": "UNAUTHORIZED"}), 401
            if not (
                principal.is_network_operator or principal.get_role_for_org(org_id)
            ):
                return jsonify({"error": "Not a member of this organization", "code": "FORBIDDEN"}), 403
        elif principal and not (
            principal.is_network_operator or principal.get_role_for_org(org_id)
        ):
            return jsonify({"error": "Not a member of this organization", "code": "FORBIDDEN"}), 403

        resp = jsonify({"org_id": org_id, "name": org.name})
        return set_current_org_cookie(resp, org_id)
    except Exception as e:
        return _api_error(e)


# ---------------------------------------------------------------------------
# Organization Workspace endpoints (Phase 7E — now session-scoped via the
# identity seam; the org is resolved server-side per request, never taken
# from the URL. Old /api/orgs/<org_id>/... routes were removed: they trusted
# a client-supplied org id for privileged private-state access.)
# ---------------------------------------------------------------------------

@app.route("/api/my-org/summary", methods=["GET"])
@require_org_role(UserRole.ORG_VIEWER)
def api_org_summary():
    """Get organization workspace summary (private + public state) for the session org."""
    try:
        from agent.org_workspace import get_org_summary
        result = get_org_summary(resolve_current_org(request))
        return jsonify(result)
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/resources", methods=["GET"])
@require_org_role(UserRole.ORG_VIEWER)
def api_org_list_resources():
    """List private resources for the session organization."""
    try:
        from agent.org_workspace import list_resources
        resources = list_resources(resolve_current_org(request))
        return jsonify({"resources": resources})
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/resources", methods=["POST"])
@require_org_role(UserRole.ORG_OPERATOR)
def api_org_add_resource():
    """Add a private resource to the session organization's inventory."""
    try:
        from agent.org_workspace import add_resource
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        resource = add_resource(resolve_current_org(request), payload)
        return jsonify({"resource": resource}), 201
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/resources/<resource_id>", methods=["PATCH"])
@require_org_role(UserRole.ORG_OPERATOR)
def api_org_update_resource(resource_id):
    """Update a private resource of the session organization."""
    try:
        from agent.org_workspace import update_resource
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        result = update_resource(resolve_current_org(request), resource_id, payload)
        if not result:
            return jsonify({"error": "Resource not found"}), 404
        return jsonify({"resource": result})
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/resources/<resource_id>", methods=["DELETE"])
@require_org_role(UserRole.ORG_OPERATOR)
def api_org_delete_resource(resource_id):
    """Delete a private resource of the session organization."""
    try:
        from agent.org_workspace import delete_resource
        deleted = delete_resource(resolve_current_org(request), resource_id)
        if not deleted:
            return jsonify({"error": "Resource not found"}), 404
        return jsonify({"message": "Resource deleted"})
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/teams", methods=["GET"])
@require_org_role(UserRole.ORG_VIEWER)
def api_org_list_teams():
    """List private teams for the session organization."""
    try:
        from agent.org_workspace import list_teams
        teams = list_teams(resolve_current_org(request))
        return jsonify({"teams": teams})
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/teams", methods=["POST"])
@require_org_role(UserRole.ORG_OPERATOR)
def api_org_add_team():
    """Add a private team to the session organization."""
    try:
        from agent.org_workspace import add_team
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        team = add_team(resolve_current_org(request), payload)
        return jsonify({"team": team}), 201
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/teams/<team_id>", methods=["PATCH"])
@require_org_role(UserRole.ORG_OPERATOR)
def api_org_update_team(team_id):
    """Update a private team of the session organization."""
    try:
        from agent.org_workspace import update_team
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        result = update_team(resolve_current_org(request), team_id, payload)
        if not result:
            return jsonify({"error": "Team not found"}), 404
        return jsonify({"team": result})
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/missions", methods=["GET"])
@require_org_role(UserRole.ORG_VIEWER)
def api_org_list_missions():
    """List private missions for the session organization."""
    try:
        from agent.org_workspace import list_missions
        missions = list_missions(resolve_current_org(request))
        return jsonify({"missions": missions})
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/missions", methods=["POST"])
@require_org_role(UserRole.ORG_OPERATOR)
def api_org_add_mission():
    """Add a private mission to the session organization."""
    try:
        from agent.org_workspace import add_mission
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        org_id = resolve_current_org(request)
        mission = add_mission(org_id, payload)
        record_audit_log(
            get_repository(),
            action="create_mission",
            entity_type="mission",
            entity_id=mission.get("id", ""),
            organization_id=org_id,
            to_state="ACTIVE",
            details={"name": mission.get("name", "")},
        )
        return jsonify({"mission": mission}), 201
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/missions/<mission_id>", methods=["PATCH"])
@require_org_role(UserRole.ORG_OPERATOR)
def api_org_update_mission(mission_id):
    """Update a private mission of the session organization."""
    try:
        from agent.org_workspace import update_mission
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400
        org_id = resolve_current_org(request)
        result = update_mission(org_id, mission_id, payload)
        if not result:
            return jsonify({"error": "Mission not found"}), 404
        record_audit_log(
            get_repository(),
            action="update_mission",
            entity_type="mission",
            entity_id=mission_id,
            organization_id=org_id,
            to_state=result.get("status"),
            details={"updated_fields": list(payload.keys())},
        )
        return jsonify({"mission": result})
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/agent/analyze-need", methods=["POST"])
@require_org_role(UserRole.ORG_VIEWER)
def api_org_agent_analyze_need():
    """
    NGO Main Agent analyzes a network Need using the session org's private
    organizational context.

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
        org_id = resolve_current_org(request)

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
        return _api_error(e)


@app.route("/api/my-org/agent/situation", methods=["GET"])
@require_org_role(UserRole.ORG_VIEWER)
def api_org_agent_situation():
    """
    NGO Main Agent situation summary for the session organization.

    Returns private + network summary with attention items.
    """
    try:
        from agent.agents.ngo_main_agent import get_org_situation
        from agent.org_workspace import list_resources, list_teams, list_missions
        from agent.data.repository import get_repository

        org_id = resolve_current_org(request)

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
        return _api_error(e)


@app.route("/api/my-org/publish-offer", methods=["POST"])
@require_org_role(UserRole.ORG_OPERATOR)
def api_org_publish_offer():
    """
    Publish a resource offer from the session org's private inventory to the
    shared network.

    This is the critical privacy boundary: the user explicitly chooses
    what to publish. Private inventory is NOT automatically exposed.
    The publishing organization is derived server-side from the session
    context — a client-supplied org id is never honored here.
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
        org_id = resolve_current_org(request)

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

        # Emit machine-facing AgentEvent
        from agent.agents.events import make_offer_created_event
        repo.append_agent_event(make_offer_created_event(
            offer_id=offer_id,
            org_id=org_id,
            district=offer.district_id,
            metadata={"resource_type": offer.resource_type, "quantity": offer.quantity},
        ))

        # Audit: publishing an offer is a consequential human action.
        record_audit_log(
            repo,
            action="publish_offer",
            entity_type="offer",
            entity_id=offer_id,
            organization_id=org_id,
            to_state="OFFERED",
            details={"resource_type": offer.resource_type, "quantity": offer.quantity},
        )

        return jsonify({"offer": result.to_dict(), "message": "Offer published to network"}), 201
    except Exception as e:
        return _api_error(e)


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
        return _api_error(e)


# ---------------------------------------------------------------------------
# Notifications endpoints
# ---------------------------------------------------------------------------

@app.route("/api/notifications", methods=["GET"])
def api_list_notifications():
    """List notifications for the caller's own org context or the network view.

    Authorization model: notifications are delivered to an organization (or
    'network'). A caller may read the queue for its own resolved org context
    (the identity seam), or the network broadcast queue. Requesting another
    organization's queue requires NETWORK_OPERATOR privileges — a client-\
    supplied recipient_id can never be used to read a different org's
    notifications.
    """
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        requested = (request.args.get("recipient_id") or "").strip()
        own_org = resolve_current_org(request)
        recipient_id = requested or own_org

        if requested and requested != own_org:
            principal = resolve_request_principal(request)
            is_operator = bool(principal and principal.is_network_operator)
            if requested == "network" and is_operator:
                recipient_id = requested
            elif is_auth_enforced():
                logger.warning(
                    "[RequestID: %s] authz denied: notifications recipient_id=%s requested (own org=%s)",
                    getattr(g, "request_id", "-"), requested, own_org,
                )
                return jsonify({"error": "Not authorized to read this recipient's notifications", "code": "FORBIDDEN"}), 403
            # Dev/test mode keeps the historical behavior so existing
            # integration fixtures continue to work unchanged.

        unread_only = request.args.get("unread_only", "false").lower() == "true"
        limit = int(request.args.get("limit", 50))
        notifs = repo.list_notifications(
            recipient_id=recipient_id,
            unread_only=unread_only,
            limit=limit,
        )
        return jsonify({"notifications": [n.to_dict() for n in notifs]})
    except Exception as e:
        return _api_error(e)


@app.route("/api/notifications/<notif_id>/read", methods=["POST"])
def api_mark_notification_read(notif_id):
    """Mark a notification as read (consequential — audited)."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        notification = repo.get_notification(notif_id)
        if not notification:
            return jsonify({"error": "Notification not found"}), 404

        own_org = resolve_current_org(request)
        recipient = notification.recipient_id
        principal = resolve_request_principal(request)
        allowed = recipient == "network" or recipient == own_org or bool(
            principal and principal.is_network_operator
        )
        if not allowed:
            if is_auth_enforced():
                logger.warning(
                    "[RequestID: %s] authz denied: mark-read notif=%s recipient=%s own_org=%s",
                    getattr(g, "request_id", "-"), notif_id, recipient, own_org,
                )
                return jsonify({"error": "Not authorized to modify this notification", "code": "FORBIDDEN"}), 403
            # Dev/test fallback preserves legacy behavior.

        if not notification.read:
            repo.mark_notification_read(notif_id)
            record_audit_log(
                repo,
                action="mark_notification_read",
                entity_type="notification",
                entity_id=notif_id,
                organization_id=own_org or None,
                from_state="UNREAD",
                to_state="READ",
                details={"recipient_id": recipient, "notification_type": notification.notification_type},
            )
        return jsonify({"success": True})
    except Exception as e:
        return _api_error(e)


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
        return _api_error(e)


@app.route("/api/matches/<need_id>/<offer_id>/confirm", methods=["POST"])
@require_auth
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
        from agent.agents.events import make_operation_created_event, make_need_status_changed_event
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

        # Emit machine-facing AgentEvents
        repo.append_agent_event(make_operation_created_event(
            operation_id=op_id,
            district=op.district_id,
            org_id=offer.organization_id,
            metadata={"name": op.name, "collaboration": True},
        ))
        repo.append_agent_event(make_need_status_changed_event(
            need_id=need_id,
            old_status="OPEN",
            new_status="RESPONDING",
            district=need.district_id,
        ))

        # Audit: consequential human action (match confirmation creates a
        # committed Operation between two organizations).
        record_audit_log(
            repo,
            action="confirm_match",
            entity_type="operation",
            entity_id=op_id,
            organization_id=offer.organization_id,
            from_state=need.status,
            to_state="RESPONDING",
            details={"need_id": need_id, "offer_id": offer_id},
        )

        return jsonify({
            "operation": result.to_dict(),
            "message": "Collaboration confirmed and Operation created",
        }), 201
    except Exception as e:
        return _api_error(e)


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
        return _api_error(e)


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
        return _api_error(e)


# ---------------------------------------------------------------------------
# Coordination endpoints (Phase 7H)
# ---------------------------------------------------------------------------

@app.route("/api/network/coordination/propose", methods=["POST"])
@require_network_operator
def api_coordination_propose():
    """
    Create a coordination proposal for a Need.
    
    Body: {"need": {...}, "organization_id": "...", "organization_name": "..."}
    
    This does NOT publish anything — it creates a proposal for review.
    """
    try:
        import uuid
        from agent.coordination.proposal import create_proposal, get_public_view
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
        from agent.data.models import ActivityEvent, Notification
        from agent.agents.events import (
            make_coordination_proposal_created_event,
            make_proposal_received_event,
            make_coordination_proposal_updated_event,
        )
        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="coordination",
            entity_id=proposal["id"],
            event_type="coordination_proposed",
            actor="network_agent",
            detail=f"Coordination proposal created for Need {need.get('id', '')} → {org_name}",
        ))

        # Emit machine-facing AgentEvent
        repo.append_agent_event(make_coordination_proposal_created_event(
            proposal_id=proposal["id"],
            org_id=org_id,
            need_id=need.get("id", ""),
        ))
        
        # Emit notification for target NGO
        repo.create_notification(Notification(
            id=f"notif_{str(uuid.uuid4())[:8]}",
            recipient_id=org_id,
            notification_type="coordination_proposed",
            title="New Coordination Proposal",
            message=f"Coordination proposal {proposal['id']} created for Need {need.get('id', '')}.",
            entity_type="coordination",
            entity_id=proposal["id"],
            metadata={"need_id": need.get("id", ""), "organization_id": org_id},
        ))
        
        # Return the sanitized public projection — never the raw proposal dict
        # (which carries org_evaluation/private_factors slots for the lifecycle).
        record_audit_log(
            repo,
            action="create_coordination_proposal",
            entity_type="proposal",
            entity_id=proposal["id"],
            organization_id=org_id,
            to_state=proposal.get("status", "PROPOSED"),
            details={"need_id": need.get("id", ""), "candidates": len(candidates)},
        )
        return jsonify({"proposal": get_public_view(proposal), "candidates": candidates}), 201
    except Exception as e:
        return _api_error(e)


@app.route("/api/proposals", methods=["GET"])
def api_list_proposals_legacy():
    """Legacy alias: list coordination proposals (public projection)."""
    return api_list_proposals()


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
        return _api_error(e)


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
        return _api_error(e)


@app.route("/api/network/coordination/proposals/<proposal_id>/send-to-org", methods=["POST"])
@require_network_operator
def api_send_proposal_to_org(proposal_id):
    """Send proposal to NGO for evaluation.

    Privacy boundary: returns the sanitized PUBLIC projection only. The raw
    proposal dict may carry org_evaluation/private_factors recorded by the
    targeted NGO — those must never appear in a network response.
    """
    try:
        import uuid
        from agent.coordination.proposal import send_to_org, get_public_view
        from agent.data.repository import get_repository
        from agent.data.models import ActivityEvent, Notification
        from agent.agents.events import make_proposal_received_event

        proposal = send_to_org(proposal_id)
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404

        repo = get_repository()
        # Activity Event
        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="coordination",
            entity_id=proposal["id"],
            event_type="proposal_sent_to_org",
            actor="network_coordinator",
            detail=f"Proposal {proposal['id']} sent to {proposal.get('organization_name', proposal.get('organization_id'))} for review",
        ))

        # Emit machine-facing AgentEvent targeting the NGO Main Agent
        repo.append_agent_event(make_proposal_received_event(
            proposal_id=proposal["id"],
            org_id=proposal["organization_id"],
            need_id=proposal.get("need_id"),
        ))

        # Targeted Notification to target NGO
        repo.create_notification(Notification(
            id=f"notif_{str(uuid.uuid4())[:8]}",
            recipient_id=proposal["organization_id"],
            notification_type="coordination_proposal_received",
            title="Proposal Review Requested",
            message=f"Coordination proposal {proposal['id']} for Need {proposal.get('need_id', '')} requires evaluation.",
            entity_type="coordination",
            entity_id=proposal["id"],
            metadata={"need_id": proposal.get("need_id"), "proposal_id": proposal["id"]},
        ))

        record_audit_log(
            repo,
            action="send_proposal_to_org",
            entity_type="proposal",
            entity_id=proposal["id"],
            organization_id=proposal.get("organization_id"),
            from_state=proposal.get("status", "PROPOSED"),
            to_state="SENT",
            details={"need_id": proposal.get("need_id")},
        )
        return jsonify({"proposal": get_public_view(proposal)})
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/agent/evaluate-coordination", methods=["POST"])
@require_org_role(UserRole.ORG_OPERATOR)
def api_org_evaluate_coordination():
    """
    NGO Main Agent privately evaluates a coordination proposal for the
    session organization.

    Body: {"proposal_id": "..."}

    Returns evaluation (private factors are stored but NOT exposed in response).
    """
    try:
        import uuid
        from agent.coordination.proposal import get_proposal, record_org_evaluation
        from agent.coordination.ngo_evaluation import evaluate_coordination
        from agent.agents.events import make_coordination_proposal_updated_event

        payload = request.get_json(force=True, silent=True)
        if not payload or not payload.get("proposal_id"):
            return jsonify({"error": "proposal_id required"}), 400

        org_id = resolve_current_org(request)

        proposal = get_proposal(payload["proposal_id"])
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404

        # Privacy/integrity boundary: only the TARGETED organization may
        # evaluate. Otherwise org B could write an evaluation onto a proposal
        # targeting org A (and 404 rather than 403 to avoid revealing
        # existence). The session seam decides the org — a client-supplied
        # org_id in the body is never honored.
        if proposal.get("organization_id") != org_id:
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
        
        # Record activity & notification
        from agent.data.repository import get_repository
        from agent.data.models import ActivityEvent, Notification
        repo = get_repository()
        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="coordination",
            entity_id=proposal["id"],
            event_type="organization_evaluation_completed",
            actor=org_id,
            detail=f"Organization {org_id} evaluated proposal: {evaluation.get('decision', '')}",
        ))

        # Emit machine-facing AgentEvent
        repo.append_agent_event(make_coordination_proposal_updated_event(
            proposal_id=proposal["id"],
            org_id=org_id,
            need_id=proposal.get("need_id"),
            metadata={"decision": public_eval.get("decision")},
        ))
        
        # Notification for org coordinators that recommendation is ready for human approval
        repo.create_notification(Notification(
            id=f"notif_{str(uuid.uuid4())[:8]}",
            recipient_id=org_id,
            notification_type="coordination_recommendation_ready",
            title="Coordination Recommendation Ready",
            message=f"Proposal {proposal['id']} evaluated ({public_eval.get('decision', 'REVIEW')}). Awaiting human approval to publish.",
            entity_type="coordination",
            entity_id=proposal["id"],
            metadata={"proposal_id": proposal["id"], "decision": public_eval.get("decision")},
        ))

        record_audit_log(
            repo,
            action="evaluate_coordination",
            entity_type="proposal",
            entity_id=proposal["id"],
            organization_id=org_id,
            to_state=str(public_eval.get("decision", "")),
            details={"decision": public_eval.get("decision")},
        )
        return jsonify({"evaluation": public_eval, "proposal_id": proposal["id"]})
    except Exception as e:
        return _api_error(e)


@app.route("/api/my-org/agent/approve-publication", methods=["POST"])
@require_org_role(UserRole.ORG_ADMIN)
def api_org_approve_publication():
    """
    Human-approved publication of proposed response for the session org.

    Body: {"proposal_id": "..."}

    Creates a public Resource Offer from the approved proposal.
    """
    try:
        import uuid
        from agent.coordination.proposal import get_proposal, approve_publication, link_offer
        from agent.coordination.publication import create_public_offer_from_proposal
        from agent.data.repository import get_repository
        from agent.data.models import ActivityEvent, Notification
        from agent.agents.events import make_coordination_proposal_updated_event

        payload = request.get_json(force=True, silent=True)
        if not payload or not payload.get("proposal_id"):
            return jsonify({"error": "proposal_id required"}), 400

        org_id = resolve_current_org(request)

        proposal = get_proposal(payload["proposal_id"])
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404

        # Privacy/integrity boundary: only the TARGETED organization may
        # approve publication. Otherwise org B could approve org A's proposal
        # and publish an offer under B's id derived from A's private
        # evaluation. The session seam decides the org — a client-supplied
        # org_id in the body is never honored.
        if proposal.get("organization_id") != org_id:
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
            offer_id = result["offer"]["id"]
            link_offer(proposal["id"], offer_id)
            
            # Proposal confirmed activity event
            repo.append_activity_event(ActivityEvent(
                id=f"evt_{str(uuid.uuid4())[:8]}",
                entity_type="coordination",
                entity_id=proposal["id"],
                event_type="proposal_confirmed",
                actor=org_id,
                detail=f"Proposal {proposal['id']} confirmed; offer {offer_id} published to network",
            ))

            # Emit machine-facing AgentEvent
            repo.append_agent_event(make_coordination_proposal_updated_event(
                proposal_id=proposal["id"],
                org_id=org_id,
                need_id=proposal.get("need_id"),
                metadata={"action": "approved", "offer_id": offer_id},
            ))
            
            # Broadcast Notification to Network
            repo.create_notification(Notification(
                id=f"notif_{str(uuid.uuid4())[:8]}",
                recipient_id="network",
                notification_type="coordination_offer_published",
                title="Resource Offer Published",
                message=f"Organization {org_id} approved and published offer {offer_id} for Need {proposal.get('need_id', '')}.",
                entity_type="coordination",
                entity_id=proposal["id"],
                metadata={"proposal_id": proposal["id"], "offer_id": offer_id},
            ))

            # Audit Log
            record_audit_log(
                repo,
                action="approve_proposal",
                entity_type="proposal",
                entity_id=proposal["id"],
                organization_id=org_id,
                from_state=proposal.get("status", "EVALUATED"),
                to_state="CONFIRMED",
                details={"offer_id": offer_id, "need_id": proposal.get("need_id")},
            )
        
        return jsonify(result)
    except Exception as e:
        return _api_error(e)


@app.route("/api/network/coordination/proposals/<proposal_id>/decline", methods=["POST"])
@require_network_operator
def api_decline_proposal(proposal_id):
    """Decline a coordination proposal.

    Privacy boundary: returns the sanitized PUBLIC projection only.
    """
    try:
        import uuid
        from agent.coordination.proposal import decline_proposal, get_public_view
        from agent.data.repository import get_repository
        from agent.data.models import ActivityEvent, Notification
        from agent.agents.events import make_coordination_proposal_updated_event

        proposal = decline_proposal(proposal_id)
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404

        repo = get_repository()
        repo.append_activity_event(ActivityEvent(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            entity_type="coordination",
            entity_id=proposal["id"],
            event_type="proposal_declined",
            actor="coordinator",
            detail=f"Proposal {proposal['id']} was declined",
        ))

        # Emit machine-facing AgentEvent
        repo.append_agent_event(make_coordination_proposal_updated_event(
            proposal_id=proposal["id"],
            org_id=proposal.get("organization_id"),
            need_id=proposal.get("need_id"),
            metadata={"action": "declined"},
        ))

        # Audit Log
        record_audit_log(
            repo,
            action="decline_proposal",
            entity_type="proposal",
            entity_id=proposal["id"],
            organization_id=proposal.get("organization_id"),
            from_state="PROPOSED",
            to_state="DECLINED",
            details={"need_id": proposal.get("need_id")},
        )

        repo.create_notification(Notification(
            id=f"notif_{str(uuid.uuid4())[:8]}",
            recipient_id="network",
            notification_type="coordination_proposal_declined",
            title="Proposal Declined",
            message=f"Coordination proposal {proposal['id']} was declined.",
            entity_type="coordination",
            entity_id=proposal["id"],
            metadata={"proposal_id": proposal["id"]},
        ))

        return jsonify({"proposal": get_public_view(proposal)})
    except Exception as e:
        return _api_error(e)


# ---------------------------------------------------------------------------
# Agent Events & Dispatch endpoints (Phase 2A)
# ---------------------------------------------------------------------------

@app.route("/api/agent/events", methods=["GET"])
@require_auth
def api_list_agent_events():
    """List agent events from the persistent outbox."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        status = request.args.get("status")
        entity_type = request.args.get("entity_type")
        limit = int(request.args.get("limit", 50))
        events = repo.list_agent_events(status=status, entity_type=entity_type, limit=limit)
        return jsonify({"events": [e.to_dict() for e in events]})
    except Exception as e:
        return _api_error(e)


@app.route("/api/agent/events/<event_id>", methods=["GET"])
@require_auth
def api_get_agent_event(event_id):
    """Get a specific agent event by ID."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        event = repo.get_agent_event(event_id)
        if not event:
            return jsonify({"error": "Event not found"}), 404
        return jsonify({"event": event.to_dict()})
    except Exception as e:
        return _api_error(e)


@app.route("/api/agent/events/process", methods=["POST"])
@require_auth
def api_process_agent_events():
    """Trigger processing of pending events from the outbox."""
    try:
        from agent.data.repository import get_repository
        from agent.agents.event_router import EventDispatcher
        repo = get_repository()
        payload = request.get_json(force=True, silent=True) or {}
        event_id = payload.get("event_id")
        limit = int(payload.get("limit", 10))
        dispatcher = EventDispatcher()
        if event_id:
            event = repo.get_agent_event(event_id)
            if event:
                res = dispatcher.dispatch_event(event, repo=repo)
                return jsonify({"processed_count": 1, "results": [res]})
            return jsonify({"processed_count": 0, "results": []})
        results = dispatcher.process_pending_events(repo=repo, limit=limit)
        return jsonify({"processed_count": len(results), "results": results})
    except Exception as e:
        return _api_error(e)


@app.route("/api/agent/events/<event_id>/replay", methods=["POST"])
@require_auth
def api_replay_agent_event(event_id):
    """Replay an event in read-only advisory mode for observability."""
    try:
        from agent.data.repository import get_repository
        from agent.agents.event_router import EventDispatcher
        repo = get_repository()
        dispatcher = EventDispatcher()
        result = dispatcher.replay_event(event_id, repo=repo)
        return jsonify(result)
    except Exception as e:
        return _api_error(e)


# ---------------------------------------------------------------------------
# Proactive Intelligence endpoints (Phase 2B)
# ---------------------------------------------------------------------------

@app.route("/api/agent/proactive/scans", methods=["GET"])
@require_auth
def api_list_proactive_scans():
    """List proactive inspection scans."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        status = request.args.get("status")
        trigger = request.args.get("trigger")
        limit = int(request.args.get("limit", 50))
        scans = repo.list_proactive_scans(status=status, trigger=trigger, limit=limit)
        return jsonify({"scans": [s.to_dict() for s in scans]})
    except Exception as e:
        return _api_error(e)


@app.route("/api/agent/proactive/scans/<scan_id>", methods=["GET"])
@require_auth
def api_get_proactive_scan(scan_id):
    """Get a specific proactive scan by ID."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        scan = repo.get_proactive_scan(scan_id)
        if not scan:
            return jsonify({"error": "Proactive scan not found"}), 404
        return jsonify({"scan": scan.to_dict()})
    except Exception as e:
        return _api_error(e)


@app.route("/api/agent/proactive/findings", methods=["GET"])
@require_auth
def api_list_proactive_findings():
    """List stateful proactive findings."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        status = request.args.get("status")
        domain = request.args.get("domain")
        severity = request.args.get("severity")
        scan_id = request.args.get("scan_id")
        limit = int(request.args.get("limit", 100))
        findings = repo.list_proactive_findings(
            status=status, domain=domain, severity=severity, scan_id=scan_id, limit=limit
        )
        return jsonify({"findings": [f.to_dict() for f in findings]})
    except Exception as e:
        return _api_error(e)


@app.route("/api/agent/proactive/findings/<finding_id>", methods=["GET"])
@require_auth
def api_get_proactive_finding(finding_id):
    """Get a specific proactive finding by ID."""
    try:
        from agent.data.repository import get_repository
        repo = get_repository()
        finding = repo.get_proactive_finding(finding_id)
        if not finding:
            return jsonify({"error": "Proactive finding not found"}), 404
        return jsonify({"finding": finding.to_dict()})
    except Exception as e:
        return _api_error(e)


@app.route("/api/agent/proactive/trigger", methods=["POST"])
@require_auth
def api_trigger_proactive_scan():
    """Trigger an immediate proactive scan cycle."""
    try:
        from agent.data.repository import get_repository
        from agent.proactive.runtime import ProactiveRuntime
        repo = get_repository()
        payload = request.get_json(force=True, silent=True) or {}
        scope = payload.get("scope")
        runtime = ProactiveRuntime(repo=repo)
        scan = runtime.run_once(scope=scope, repo=repo, trigger="manual_api")
        return jsonify({"scan": scan.to_dict()})
    except Exception as e:
        return _api_error(e)


@app.route("/api/agent/proactive/status", methods=["GET"])
@require_auth
def api_get_proactive_status():
    """Get status of proactive scheduler and runtime."""
    try:
        from agent.proactive.scheduler import get_proactive_scheduler
        from agent.proactive.detectors.registry import list_detectors
        scheduler = get_proactive_scheduler()
        detectors = list_detectors()
        return jsonify({
            "scheduler": scheduler.get_status(),
            "registered_detectors": [
                {
                    "detector_id": d.detector_id,
                    "domain": d.domain,
                    "description": d.description,
                    "relevant_specialists": d.relevant_specialists,
                }
                for d in detectors
            ],
        })
    except Exception as e:
        return _api_error(e)


@app.route("/api/agent/proactive/scheduler/start", methods=["POST"])
@require_network_operator
def api_start_proactive_scheduler():
    """Start the background proactive scheduler."""
    try:
        from agent.proactive.scheduler import get_proactive_scheduler
        payload = request.get_json(force=True, silent=True) or {}
        interval = payload.get("interval_seconds")
        scheduler = get_proactive_scheduler()
        scheduler.start(interval_seconds=interval)
        return jsonify({"status": "started", "scheduler": scheduler.get_status()})
    except Exception as e:
        return _api_error(e)


@app.route("/api/agent/proactive/scheduler/stop", methods=["POST"])
@require_network_operator
def api_stop_proactive_scheduler():
    """Stop the background proactive scheduler."""
    try:
        from agent.proactive.scheduler import get_proactive_scheduler
        scheduler = get_proactive_scheduler()
        scheduler.stop()
        return jsonify({"status": "stopped", "scheduler": scheduler.get_status()})
    except Exception as e:
        return _api_error(e)



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
        return _api_error(e)


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
        return _api_error(e)


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
        return _api_error(e)


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
        return _api_error(e)


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
        return _api_error(e)


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
        return _api_error(e)


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
        return _api_error(e)


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

def _log_startup_banner():
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        # Mask credentials for clean logging
        masked_url = db_url
        if "@" in db_url and "://" in db_url:
            proto, rest = db_url.split("://", 1)
            creds, host = rest.split("@", 1)
            user = creds.split(":", 1)[0]
            masked_url = f"{proto}://{user}:***@{host}"
        print(f"[DATABASE] Connected via DATABASE_URL: {masked_url}")
    else:
        print("=" * 72)
        print("[WARNING] DATABASE_URL is not set!")
        print("ReliefOS is running with InMemoryRepository fallback.")
        print("Most multi-district data (Jorhat, Golaghat, Charaideo flood extents,")
        print("persistent coordination proposals, etc.) will NOT be available.")
        print("To connect to PostgreSQL, configure DATABASE_URL in .env or run start_backend.bat:")
        print("  DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos")
        print("=" * 72)


if __name__ == "__main__":
    _log_startup_banner()
    print("Starting ReliefOS API on http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
