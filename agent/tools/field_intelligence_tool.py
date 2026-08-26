"""
Field Intelligence Text Intake — LLM-assisted extraction from raw field observations.

A field coordinator types a messy, natural-language observation. This module
uses the LLM (via Strands) to extract structured fields, but ALWAYS keeps
the raw text alongside the extraction.

Key design principles:
- LLM is for EXTRACTION only, not the source of truth for structured data
- Original source data is ALWAYS preserved alongside any AI-derived interpretation
- Extraction confidence is honestly reported, not overconfident
- No automatic geocoding (out of scope — flag as unresolved)
"""

import json
from datetime import datetime, timezone

from agent.config import model
from agent.verification import verify_numbers_against_source, verify_entity_mentioned


# ---------------------------------------------------------------------------
# Controlled vocabulary for needs (matches community_reports.py)
# ---------------------------------------------------------------------------

VALID_NEEDS = [
    "medical", "food", "water", "sanitary_supplies",
    "infant_care", "shelter", "transport", "other"
]

# Controlled vocabulary for road/facility statuses
VALID_ROAD_STATUSES = ["blocked", "damaged", "clear", "unknown"]
VALID_FACILITY_STATUSES = ["submerged", "damaged", "operational", "unknown"]


# ---------------------------------------------------------------------------
# System prompt for extraction
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You are a disaster-response data extraction system.
Your ONLY job is to extract structured fields from messy, natural-language field
observations submitted by field coordinators.

CRITICAL RULES:
1. Only extract what is ACTUALLY STATED or STRONGLY IMPLIED in the text.
   Never invent, assume, or guess details not present in the text.
2. Use null / empty list / "unknown" for anything not mentioned — do NOT guess.
3. For location: store the text exactly as mentioned (e.g. "near the temple",
   "north side of town"). Do NOT attempt to resolve to coordinates.
4. For needs: map to the controlled vocabulary only if the text clearly indicates
   that need. Use "other" if the need doesn't fit any category.
5. For road/facility statuses: only extract if explicitly mentioned.
6. Set extraction_confidence based on text clarity:
   - "high": clear, detailed, unambiguous text
   - "medium": mostly clear but some ambiguity or missing details
   - "low": very short, vague, ambiguous, or unclear text
7. NEVER hallucinate people counts, facility names, or road names not in the text.
8. Return ONLY valid JSON matching the schema below — no markdown, no explanation.

RESPOND WITH ONLY THIS JSON SCHEMA:
{
  "location_description": "string — the location as described in the text, or null",
  "location_resolved": false,
  "people_count": null,
  "needs": [],
  "road_status_mentions": [],
  "facility_status_mentions": [],
  "extraction_confidence": "low",
  "note": "any additional context from the text not captured above, or null"
}

VALID NEEDS: medical, food, water, sanitary_supplies, infant_care, shelter, transport, other
ROAD STATUS OPTIONS: blocked, damaged, clear, unknown
FACILITY STATUS OPTIONS: submerged, damaged, operational, unknown
"""


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_field_report(raw_text: str) -> dict:
    """
    Uses the LLM to extract structured fields from a messy field observation.

    Returns a dict with the extraction AND the original text preserved.
    The LLM is used for interpretation/extraction only — the raw text is
    always the authoritative source.

    Args:
        raw_text: the raw, natural-language field observation

    Returns:
        Full extraction dict including raw_text, extraction_confidence,
        and all extracted fields.
    """
    if not raw_text or not raw_text.strip():
        return _empty_extraction(raw_text)

    # Call the LLM for extraction
    try:
        from strands import Agent
        extraction_agent = Agent(
            model=model,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
        )
        prompt = (
            f"Extract structured fields from this field observation:\n\n"
            f"\"{raw_text.strip()}\""
        )
        response = extraction_agent(prompt)
        response_text = str(response)

        # Parse the LLM response — try to extract JSON
        extraction = _parse_llm_json(response_text)

        # Validate and normalize the extraction
        extraction = _validate_extraction(extraction)

    except Exception as e:
        # LLM unavailable — return a low-confidence extraction with just the raw text
        extraction = _empty_extraction(raw_text)
        extraction["extraction_confidence"] = "low"
        extraction["note"] = f"LLM extraction failed: {type(e).__name__}: {e}"

    # ALWAYS preserve the raw text — this is the authoritative source
    extraction["raw_text"] = raw_text.strip()
    extraction["extracted_at"] = datetime.now(timezone.utc).isoformat()

    # --- Deterministic verification guardrails ---
    _verify_extraction(extraction, raw_text)

    return extraction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_extraction(raw_text: str) -> dict:
    """Return a minimal, honest extraction when input is empty or LLM fails."""
    return {
        "location_description": None,
        "location_resolved": False,
        "people_count": None,
        "needs": [],
        "road_status_mentions": [],
        "facility_status_mentions": [],
        "extraction_confidence": "low",
        "note": None,
        "raw_text": raw_text.strip() if raw_text else "",
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


def _parse_llm_json(response_text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = response_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object in the text
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        # If all parsing fails, return empty
        return {}


def _validate_extraction(extraction: dict) -> dict:
    """Validate and normalize extraction fields against controlled vocabularies."""
    result = {}

    # Location — store as text, never resolve
    result["location_description"] = extraction.get("location_description")
    result["location_resolved"] = False  # Always false in this iteration

    # People count — must be int or null
    pc = extraction.get("people_count")
    if isinstance(pc, (int, float)) and pc >= 0:
        result["people_count"] = int(pc)
    else:
        result["people_count"] = None

    # Needs — validate against controlled vocabulary
    needs = extraction.get("needs", [])
    if isinstance(needs, list):
        result["needs"] = [n for n in needs if n in VALID_NEEDS]
    else:
        result["needs"] = []

    # Road status mentions
    roads = extraction.get("road_status_mentions", [])
    if isinstance(roads, list):
        result["road_status_mentions"] = []
        for r in roads:
            if isinstance(r, dict) and "road_description" in r:
                result["road_status_mentions"].append({
                    "road_description": str(r["road_description"]),
                    "status": r.get("status", "unknown") if r.get("status") in VALID_ROAD_STATUSES else "unknown",
                })
    else:
        result["road_status_mentions"] = []

    # Facility status mentions
    facilities = extraction.get("facility_status_mentions", [])
    if isinstance(facilities, list):
        result["facility_status_mentions"] = []
        for f in facilities:
            if isinstance(f, dict) and "facility_description" in f:
                result["facility_status_mentions"].append({
                    "facility_description": str(f["facility_description"]),
                    "status": f.get("status", "unknown") if f.get("status") in VALID_FACILITY_STATUSES else "unknown",
                })
    else:
        result["facility_status_mentions"] = []

    # Confidence
    conf = extraction.get("extraction_confidence", "low")
    if conf in ("high", "medium", "low"):
        result["extraction_confidence"] = conf
    else:
        result["extraction_confidence"] = "low"

    # Note
    result["note"] = extraction.get("note")

    return result


def _verify_extraction(extraction: dict, raw_text: str) -> None:
    """
    Apply deterministic verification guardrails to an extraction.
    Mutates the extraction dict in place, adding verification fields.
    """
    # 1) Verify people_count against source text
    pc = extraction.get("people_count")
    if pc is not None:
        result = verify_numbers_against_source(pc, raw_text)
        extraction["people_count_verified"] = result["verified"]
        extraction["people_count_note"] = result["note"]
    else:
        extraction["people_count_verified"] = True
        extraction["people_count_note"] = None

    # 2) Verify facility descriptions against source text
    facilities = extraction.get("facility_status_mentions", [])
    for f in facilities:
        if not isinstance(f, dict):
            continue
        desc = f.get("facility_description", "")
        if desc:
            result = verify_entity_mentioned(desc, raw_text)
            f["entity_verified"] = result["verified"]
            f["entity_verification_note"] = result["note"]
        else:
            f["entity_verified"] = True
            f["entity_verification_note"] = None

    # 3) Verify road descriptions against source text
    roads = extraction.get("road_status_mentions", [])
    for r in roads:
        if not isinstance(r, dict):
            continue
        desc = r.get("road_description", "")
        if desc:
            result = verify_entity_mentioned(desc, raw_text)
            r["entity_verified"] = result["verified"]
            r["entity_verification_note"] = result["note"]
        else:
            r["entity_verified"] = True
            r["entity_verification_note"] = None
