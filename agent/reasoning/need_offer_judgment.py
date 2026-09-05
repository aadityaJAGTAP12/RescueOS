"""Bounded, NGO-side interpretation of deterministic Need/resource facts."""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError

logger = logging.getLogger(__name__)
_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9_])\d+(?:\.\d+)?(?![A-Za-z0-9_])")
_ALLOWED_CONFIDENCE = {"likely_sufficient", "unclear", "likely_insufficient"}


def _numbers(value) -> set[str]:
    return {match.group(0) for match in _NUMBER_PATTERN.finditer(str(value))}


def _allowed_numbers(facts: dict) -> set[str]:
    allowed = set()
    for key in ("available_quantity", "requested_quantity"):
        value = facts.get(key)
        if value is not None:
            allowed.update(_numbers(value))
    return allowed


def _parse_response(response) -> tuple[str, str]:
    raw = response if isinstance(response, dict) else None
    if raw is None:
        text = str(response)
        try:
            raw = json.loads(text)
        except (TypeError, ValueError):
            return text.strip(), "unclear"

    note = str(raw.get("note", raw.get("interpretation", ""))).strip()
    confidence = str(raw.get("confidence", "unclear")).strip().lower()
    return note, confidence if confidence in _ALLOWED_CONFIDENCE else "unclear"


def _default_llm(prompt: str):
    # Reuse the configured Strands/Ollama integration without importing it at module load.
    from agent.agents.coordinator_agent import _coordinator_agent
    return _coordinator_agent(prompt)


def judge_need_offer(
    facts: dict,
    title: str = "",
    description: str = "",
    llm=None,
    timeout_seconds: float = 2.0,
) -> dict:
    """Return advisory interpretation while preserving deterministic facts unchanged."""
    factual = dict(facts)
    unavailable = {
        "note": "AI interpretation unavailable - review manually",
        "confidence": "unclear",
        "available": False,
    }

    prompt = (
        "Assess only whether this category-level Need/resource match is likely to address "
        "the real need. Return JSON with exactly note and confidence. confidence must be "
        "one of likely_sufficient, unclear, likely_insufficient. Do not include quantities, "
        "units, statuses, decisions, or numeric estimates. The deterministic facts are "
        "authoritative and the result is advisory only.\n\n"
        f"Need title: {title}\nNeed description: {description}\n"
        f"Deterministic facts: {json.dumps(factual, sort_keys=True)}"
    )

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit((llm or _default_llm), prompt)
    try:
        response = future.result(timeout=timeout_seconds)
    except (TimeoutError, Exception) as exc:
        logger.warning("Need/resource AI interpretation unavailable: %s", exc)
        executor.shutdown(wait=False, cancel_futures=True)
        return {"facts": factual, "interpretation": unavailable}
    else:
        executor.shutdown(wait=False, cancel_futures=True)

    raw_text = json.dumps(response, sort_keys=True) if isinstance(response, dict) else str(response)
    if _numbers(raw_text) - _allowed_numbers(factual):
        logger.warning("Discarding need/resource AI interpretation containing an ungrounded number")
        return {
            "facts": factual,
            "interpretation": {
                **unavailable,
                "validation_warning": "AI output discarded because it contained an ungrounded number",
            },
        }

    note, confidence = _parse_response(response)

    return {
        "facts": factual,
        "interpretation": {
            "note": note or "No interpretive note returned - review manually",
            "confidence": confidence,
            "available": True,
        },
    }
