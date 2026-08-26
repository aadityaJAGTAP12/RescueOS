"""
Query Parser Tool — LLM-assisted extraction of structured intent from
free-text coordinator queries.

Uses the LLM (via Strands) to parse natural language into structured fields.
The LLM is for INTERPRETATION/PARSING ONLY — it does NOT answer the query
or compute any results. The deterministic backend handles all computation.

Key design principles:
- LLM extracts what's ASKED, not what's TRUE
- Never invent numbers, locations, or resources not mentioned
- Null/empty for anything not stated — no guessing
- Raw query always preserved verbatim
- Resources captured as free-text phrases, not forced into rigid units
"""

import json
import re
from agent.config import model
from agent.verification import verify_all_numbers


# ------------------------------------------------------------------
# System prompt for query parsing
# ------------------------------------------------------------------

QUERY_PARSE_SYSTEM_PROMPT = """You are a disaster-response query parser. Your ONLY job is to extract structured intent from a coordinator's free-text query. You do NOT answer the query — you only extract WHAT is being asked.

CRITICAL RULES:
1. Extract ONLY what is ACTUALLY PRESENT in the query. Never invent, assume, or guess.
2. If a field is not mentioned, use null / empty list / false — do NOT guess.
3. For locations: store the FREE-TEXT as written (e.g. "the 3 marooned villages"). Do NOT attempt to resolve to coordinates.
4. For resources: extract each distinct resource/need mention as its OWN entry. Capture the user's EXACT wording.
5. quantity_numeric must be a number that LITERALLY appears as a digit in the raw text — never compute, multiply, convert, or infer a number that isn't directly stated as digits. "5000 people for 7 days" does NOT produce quantity_numeric=35000. If no explicit digit appears, set quantity_numeric to null.
6. Preserve the user's own unit/phrasing (families, bottles, kg, boats, etc.) — do not force conversion.
7. For capabilities: only mark true what is actually requested.
8. Return ONLY valid JSON — no markdown, no explanation, no comments, no arithmetic expressions.

RESPOND WITH ONLY THIS JSON SCHEMA:
{
  "intent": "assessment" | "allocation" | "general",
  "locations_mentioned": ["free-text location references exactly as written"],
  "resources_mentioned": [
    {
      "raw_phrase": "exactly what the user said",
      "resource_type": "food" | "water" | "medical" | "transport" | "shelter" | "other",
      "quantity_text": "the quantity as stated in whatever unit",
      "quantity_numeric": null,
      "unit": "whatever unit was stated — free text"
    }
  ],
  "prioritization_criteria": [],
  "requested_capabilities": {
    "priority_ranking": false,
    "resource_allocation": false,
    "route_optimization": false,
    "river_gauge_data": false,
    "sustainment_calculation": false
  },
  "parse_confidence": "high" | "medium" | "low"
}

RESOURCE EXTRACTION EXAMPLES:
- "400 families need food" -> {raw_phrase: "400 families", resource_type: "food", quantity_text: "400 families", quantity_numeric: 400, unit: "families"}
- "200 water bottles" -> {raw_phrase: "200 water bottles", resource_type: "water", quantity_text: "200 bottles", quantity_numeric: 200, unit: "bottles"}
- "5000 kg of rice" -> {raw_phrase: "5000 kg of rice", resource_type: "food", quantity_text: "5000 kg", quantity_numeric: 5000, unit: "kg"}
- "2 boats and 1 medical team" -> TWO entries: one for "2 boats" (transport, 2, "boats") and one for "1 medical team" (medical, 1, "medical team")
- "enough food for two weeks" -> {raw_phrase: "enough food for two weeks", resource_type: "food", quantity_text: "enough for two weeks", quantity_numeric: null, unit: "weeks"}
- "we need more water" -> {raw_phrase: "more water", resource_type: "water", quantity_text: "more", quantity_numeric: null, unit: null}

INTENT GUIDANCE:
- "assessment": asking about status, priority, flood level, exposure, conditions of a location
- "allocation": asking to distribute, allocate, or assign resources across locations
- "general": informational question not tied to a specific action

CAPABILITY GUIDANCE:
- "priority_ranking": true if asking to rank, prioritize, or compare urgency of locations
- "resource_allocation": true if asking to distribute, assign, or plan resource deployment
- "route_optimization": true if asking for optimal routes, travel paths, or logistics routing
- "river_gauge_data": true if asking for river levels, gauge readings, water depth
- "sustainment_calculation": true if asking for burn rate, supply duration, consumption forecasting
"""


# ------------------------------------------------------------------
# Main parsing function
# ------------------------------------------------------------------

def parse_operational_query(raw_query: str) -> dict:
    """
    Uses the LLM to parse a free-text coordinator query into structured
    intent. Does NOT attempt to answer the query — only extracts
    what's being asked for, so the deterministic backend can then compute
    a real, evidence-grounded answer.

    Args:
        raw_query: the coordinator's free-text query

    Returns:
        {
            "raw_query": str,
            "intent": "assessment" | "allocation" | "general",
            "locations_mentioned": [str],
            "resources_mentioned": [
                {
                    "raw_phrase": str,
                    "resource_type": str,
                    "quantity_text": str,
                    "quantity_numeric": int | None,
                    "unit": str | None,
                    "flagged_as_possible_fabrication": bool,
                    "verification_note": str | None,
                }
            ],
            "prioritization_criteria": [str],
            "requested_capabilities": {...},
            "clarification_needed": [...],
            "parse_confidence": "high" | "medium" | "low"
        }
    """
    if not raw_query or not raw_query.strip():
        return _empty_parse(raw_query or "")

    try:
        from strands import Agent
        parse_agent = Agent(
            model=model,
            system_prompt=QUERY_PARSE_SYSTEM_PROMPT,
        )
        prompt = (
            f"Parse this coordinator query into structured intent:\n\n"
            f"\"{raw_query.strip()}\""
        )
        response = parse_agent(prompt)
        response_text = str(response)

        # Parse LLM response as JSON
        parsed = _parse_llm_json(response_text)

        # If parser failed, retry once (Strands Agent can emit empty {}
        # followed by the real JSON on some runs)
        if not parsed:
            response = parse_agent(prompt)
            response_text = str(response)
            parsed = _parse_llm_json(response_text)

        # Validate and normalize
        parsed = _validate_parse(parsed)

    except Exception as e:
        # LLM unavailable — return low-confidence parse with minimal extraction
        parsed = _empty_parse(raw_query)
        parsed["parse_confidence"] = "low"
        parsed["_error"] = f"LLM parse failed: {type(e).__name__}: {e}"

    # Always preserve raw query
    parsed["raw_query"] = raw_query.strip()

    # Deterministic guardrail: verify no fabricated numbers
    parsed["resources_mentioned"] = verify_no_fabricated_numbers(
        parsed["resources_mentioned"], raw_query
    )

    # Determine if clarification is needed
    parsed["clarification_needed"] = _extract_clarifications(
        parsed["resources_mentioned"], raw_query
    )

    return parsed


# ------------------------------------------------------------------
# Deterministic guardrail: fabrication detection
# ------------------------------------------------------------------

def verify_no_fabricated_numbers(
    resources_mentioned: list[dict], raw_query: str
) -> list[dict]:
    """
    For each extracted resource, checks whether quantity_numeric actually
    appears as a literal number in raw_query. If it doesn't appear, this
    is likely a computed/invented value — flag it rather than silently
    trusting it.
    """
    return verify_all_numbers(
        resources_mentioned, raw_query, number_field="quantity_numeric"
    )


# ------------------------------------------------------------------
# Clarification detection
# ------------------------------------------------------------------

def _extract_clarifications(
    resources_mentioned: list[dict], raw_query: str
) -> list[dict]:
    """
    If the query's intent implies allocation but no explicit numeric
    resource quantity is available, flag that clarification is needed.
    """
    clarifications = []

    # Check if any resource has quantity_numeric=None (unquantified)
    for resource in resources_mentioned:
        if resource.get("quantity_numeric") is None:
            phrase = resource.get("raw_phrase", "this resource")
            rtype = resource.get("resource_type", "resource")
            clarifications.append({
                "field": f"{rtype} quantity",
                "reason": (
                    f"You mentioned \"{phrase}\" but did not specify a "
                    f"numeric quantity. Please provide a specific amount "
                    f"(e.g., in kg, units, or families) so an allocation "
                    f"can be calculated."
                ),
            })

    return clarifications


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _empty_parse(raw_query: str) -> dict:
    """Return a minimal, honest parse when input is empty or LLM fails."""
    return {
        "raw_query": raw_query.strip() if raw_query else "",
        "intent": "general",
        "locations_mentioned": [],
        "resources_mentioned": [],
        "prioritization_criteria": [],
        "requested_capabilities": {
            "priority_ranking": False,
            "resource_allocation": False,
            "route_optimization": False,
            "river_gauge_data": False,
            "sustainment_calculation": False,
        },
        "clarification_needed": [],
        "parse_confidence": "low",
    }


def _parse_llm_json(response_text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks,
    trailing commas, inline comments, arithmetic expressions, and other
    common llama3.2 output quirks."""
    text = response_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    # Try direct parse first (most common case — raw clean JSON)
    try:
        return json.loads(text)
    except Exception:
        pass

    # Find and extract the LAST complete JSON object in the text.
    # Strands sometimes emits "{}\n{...actual JSON...}" — an empty object
    # followed by the real response.
    positions = []
    idx = 0
    while True:
        pos = text.find("}", idx)
        if pos == -1:
            break
        positions.append(pos)
        idx = pos + 1

    for end_pos in reversed(positions):
        depth = 0
        start_pos = end_pos
        for i in range(end_pos, -1, -1):
            if text[i] == "}":
                depth += 1
            elif text[i] == "{":
                depth -= 1
            if depth == 0:
                start_pos = i
                break

        candidate = text[start_pos:end_pos + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

        # Try cleaning: strip comments, trailing commas
        cleaned = candidate
        cleaned = re.sub(r'(?<!")#.*$', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            return json.loads(cleaned)
        except Exception:
            pass

    return {}


def _validate_parse(parsed: dict) -> dict:
    """Validate and normalize parsed fields against the new schema."""
    result = {}

    # Intent
    intent = parsed.get("intent", "general")
    if intent in ("assessment", "allocation", "general"):
        result["intent"] = intent
    else:
        result["intent"] = "general"

    # Locations mentioned — list of free-text strings
    locs = parsed.get("locations_mentioned", [])
    if isinstance(locs, list):
        result["locations_mentioned"] = [str(l) for l in locs if l]
    else:
        result["locations_mentioned"] = []

    # Resources mentioned — flexible list of dicts
    res = parsed.get("resources_mentioned", [])
    if isinstance(res, list):
        result["resources_mentioned"] = []
        for item in res:
            if not isinstance(item, dict):
                continue
            entry = {
                "raw_phrase": str(item.get("raw_phrase", "")),
                "resource_type": _validate_resource_type(item.get("resource_type", "other")),
                "quantity_text": str(item.get("quantity_text", "")) if item.get("quantity_text") else None,
                "quantity_numeric": _safe_int(item.get("quantity_numeric")),
                "unit": str(item.get("unit", "")) if item.get("unit") else None,
            }
            if entry["raw_phrase"]:  # only add entries with actual content
                result["resources_mentioned"].append(entry)
    else:
        result["resources_mentioned"] = []

    # Prioritization criteria
    criteria = parsed.get("prioritization_criteria", [])
    if isinstance(criteria, list):
        result["prioritization_criteria"] = [str(c) for c in criteria if c]
    else:
        result["prioritization_criteria"] = []

    # Requested capabilities
    caps = parsed.get("requested_capabilities", {})
    if isinstance(caps, dict):
        result["requested_capabilities"] = {
            "priority_ranking": bool(caps.get("priority_ranking", False)),
            "resource_allocation": bool(caps.get("resource_allocation", False)),
            "route_optimization": bool(caps.get("route_optimization", False)),
            "river_gauge_data": bool(caps.get("river_gauge_data", False)),
            "sustainment_calculation": bool(caps.get("sustainment_calculation", False)),
        }
    else:
        result["requested_capabilities"] = {
            "priority_ranking": False, "resource_allocation": False,
            "route_optimization": False, "river_gauge_data": False,
            "sustainment_calculation": False,
        }

    # Parse confidence
    conf = parsed.get("parse_confidence", "low")
    if conf in ("high", "medium", "low"):
        result["parse_confidence"] = conf
    else:
        result["parse_confidence"] = "low"

    return result


def _validate_resource_type(value) -> str:
    """Validate resource_type against allowed values."""
    valid = {"food", "water", "medical", "transport", "shelter", "other"}
    if isinstance(value, str) and value.lower() in valid:
        return value.lower()
    return "other"


def _safe_int(value) -> int | None:
    """Safely convert a value to int, returning None for null/non-numeric."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


# ------------------------------------------------------------------
# Capability gate — deterministic, no LLM
# ------------------------------------------------------------------

SUPPORTED_CAPABILITIES = {
    "priority_ranking": True,
    "resource_allocation": True,
    "route_optimization": False,
    "river_gauge_data": False,
    "sustainment_calculation": False,
}


def check_capability_gaps(requested_capabilities: dict) -> list[dict]:
    """
    Compare requested capabilities against what's actually supported.
    Returns a list of capability status entries for each REQUESTED capability.
    """
    gaps = []
    for cap, requested in requested_capabilities.items():
        if not requested:
            continue
        supported = SUPPORTED_CAPABILITIES.get(cap, False)
        gaps.append({
            "capability": cap,
            "status": "supported" if supported else "not_available",
            "reason": (
                "This capability is implemented and ready."
                if supported
                else _capability_reason(cap)
            ),
        })
    return gaps


def _capability_reason(cap: str) -> str:
    """Return an honest, human-readable reason for unsupported capabilities."""
    reasons = {
        "route_optimization": "Road accessibility routing not yet implemented. Roads are mapped but optimal routing is not computed.",
        "river_gauge_data": "No real-time river level sensors integrated. Flood data comes from Sentinel-1 SAR satellite imagery (static polygons), not live gauge readings.",
        "sustainment_calculation": "Supply consumption forecasting not yet built. Resource allocation is point-in-time, not time-series.",
    }
    return reasons.get(cap, "This capability is not yet implemented.")


# ------------------------------------------------------------------
# Location resolution — known locations only, honest fallback
# ------------------------------------------------------------------

def resolve_query_locations(
    locations_mentioned: list[str],
    known_locations: dict,
) -> tuple[list[dict], list[str]]:
    """
    Resolve free-text location mentions against known locations.

    Uses case-insensitive substring matching: if a known location name
    (with underscores replaced by spaces) appears as a substring of the
    mentioned text, or vice versa, it's considered a match.

    DOES NOT guess coordinates for unrecognized locations.
    DOES NOT geocode via external services.

    Args:
        locations_mentioned: free-text location strings from the query parser
        known_locations: dict of {name: (lon, lat)} from KNOWN_LOCATIONS

    Returns:
        (resolved, unresolved) where:
        - resolved: list of {name, lat, lon, matched_text}
        - unresolved: list of original free-text strings that couldn't be matched
    """
    resolved = []
    unresolved = []

    known_lookup = {}
    for name, (lon, lat) in known_locations.items():
        normalized = name.replace("_", " ").strip().lower()
        known_lookup[normalized] = (name, lat, lon)

    for text in locations_mentioned:
        if not text or not text.strip():
            continue
        text_lower = text.strip().lower()
        matched = False

        # 1) Try exact match
        exact_key = text_lower.replace(" ", "_").replace("-", "_")
        if exact_key in known_locations:
            lon_val, lat_val = known_locations[exact_key]
            resolved.append({
                "name": exact_key,
                "lat": lat_val,
                "lon": lon_val,
                "matched_text": text.strip(),
            })
            matched = True

        # 2) Substring match — prefer the LONGEST known name
        if not matched:
            best_match = None
            best_match_len = 0

            for norm_name, (orig_name, lat, lon) in known_lookup.items():
                if norm_name in text_lower or text_lower in norm_name:
                    if len(norm_name) > best_match_len:
                        best_match = (orig_name, lat, lon)
                        best_match_len = len(norm_name)

            if best_match:
                orig_name, lat, lon = best_match
                resolved.append({
                    "name": orig_name,
                    "lat": lat,
                    "lon": lon,
                    "matched_text": text.strip(),
                })
                matched = True

        if not matched:
            unresolved.append(text.strip())

    return resolved, unresolved
