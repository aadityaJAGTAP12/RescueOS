"""
Shared deterministic verification utilities for LLM extraction guardrails.

These functions verify that LLM-extracted values are grounded in the
original source text. They do NOT restrict flexible phrasing — they
only catch fabrication (values not present in the input).

Design principle: input phrasing should stay flexible (any wording,
any unit, any way of describing a need). Guardrails ONLY catch
fabrication, not flexible-but-honest extraction.
"""

import re
from difflib import SequenceMatcher


def verify_numbers_against_source(
    extracted_value: int | float | None,
    source_text: str,
) -> dict:
    """
    Check whether a numeric value the LLM extracted actually appears
    as a literal number in the source text.

    Returns:
        {
            "value": the original value,
            "verified": True if the number literally appears, False otherwise,
            "note": explanation string (None if verified)
        }
    """
    if extracted_value is None:
        return {"value": None, "verified": True, "note": None}

    # Check if the number appears as digits in the source text
    source_numbers = set(re.findall(r'\d+', source_text))
    str_val = str(int(extracted_value)) if isinstance(extracted_value, float) and extracted_value == int(extracted_value) else str(extracted_value)

    if str_val in source_numbers:
        return {"value": extracted_value, "verified": True, "note": None}

    return {
        "value": extracted_value,
        "verified": False,
        "note": (
            f"Value {extracted_value} does not literally appear in the "
            f"source text. May be computed/inferred rather than stated."
        ),
    }


def verify_entity_mentioned(
    entity_text: str,
    source_text: str,
    threshold: float = 0.6,
) -> dict:
    """
    Check whether a named entity (facility name, road name, location
    description) the LLM extracted actually appears (or closely matches)
    something in the source text.

    Uses substring matching first, then fuzzy matching as fallback.

    Returns:
        {
            "entity": the original entity text,
            "verified": True if found or closely matched,
            "best_match": the closest match found (or None),
            "match_type": "exact" | "substring" | "fuzzy" | "none",
            "note": explanation string (None if verified)
        }
    """
    if not entity_text:
        return {"entity": entity_text, "verified": True, "best_match": None, "match_type": "none", "note": None}

    source_lower = source_text.lower()
    entity_lower = entity_text.lower().strip()

    # 1) Exact match
    if entity_lower in source_lower:
        return {"entity": entity_text, "verified": True, "best_match": entity_text, "match_type": "exact", "note": None}

    # 2) Check if source contains the entity (substring)
    #    Handle common LLM variations: extra spaces, punctuation
    entity_clean = re.sub(r'[^\w\s]', '', entity_lower).strip()
    source_clean = re.sub(r'[^\w\s]', '', source_lower)
    if entity_clean and entity_clean in source_clean:
        return {"entity": entity_text, "verified": True, "best_match": entity_text, "match_type": "substring", "note": None}

    # 3) Fuzzy match — check if any word sequence in the source closely matches
    source_words = source_clean.split()
    entity_words = entity_clean.split()

    if len(entity_words) >= 2:
        # Check sliding windows of the source for fuzzy matches
        entity_len = len(entity_words)
        best_ratio = 0
        best_match = None
        for i in range(len(source_words) - entity_len + 1):
            window = ' '.join(source_words[i:i + entity_len])
            ratio = SequenceMatcher(None, entity_clean, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = ' '.join(source_words[i:i + entity_len])

        if best_ratio >= threshold:
            return {
                "entity": entity_text,
                "verified": True,
                "best_match": best_match,
                "match_type": "fuzzy",
                "note": None,
            }

    return {
        "entity": entity_text,
        "verified": False,
        "best_match": best_match if best_ratio >= 0.3 else None,
        "match_type": "none",
        "note": (
            f"Entity \"{entity_text}\" does not appear to be mentioned "
            f"in the source text. May be fabricated."
        ),
    }


def verify_all_numbers(
    items: list[dict],
    source_text: str,
    number_field: str = "quantity_numeric",
) -> list[dict]:
    """
    Apply verify_numbers_against_source to a list of extracted items.
    Adds 'verified' and 'verification_note' fields to each item.

    Returns the modified list (mutates in place).
    """
    for item in items:
        if not isinstance(item, dict):
            continue
        val = item.get(number_field)
        result = verify_numbers_against_source(val, source_text)
        item["flagged_as_possible_fabrication"] = not result["verified"]
        item["verification_note"] = result["note"]
    return items


def verify_all_entities(
    items: list[dict],
    source_text: str,
    entity_field: str,
    threshold: float = 0.6,
) -> list[dict]:
    """
    Apply verify_entity_mentioned to a list of extracted items.
    Adds 'entity_verified' and 'entity_verification_note' fields.

    Returns the modified list (mutates in place).
    """
    for item in items:
        if not isinstance(item, dict):
            continue
        entity = item.get(entity_field)
        if not entity:
            item["entity_verified"] = True
            item["entity_verification_note"] = None
            continue
        result = verify_entity_mentioned(entity, source_text, threshold)
        item["entity_verified"] = result["verified"]
        item["entity_verification_note"] = result["note"]
    return items
