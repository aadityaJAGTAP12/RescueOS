"""
ReliefOS Input Validation & Sanitization Helpers — Production Hardening

Provides robust, fail-fast validation for IDs, coordinates, pagination params,
status transitions, and sensitive field redaction.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping, Optional, Sequence, Tuple

# Regex pattern for alphanumeric IDs (allows hyphens and underscores)
ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")

# Latitude must be between -90 and 90; Longitude between -180 and 180
MIN_LAT, MAX_LAT = -90.0, 90.0
MIN_LNG, MAX_LNG = -180.0, 180.0

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "secret",
    "secret_key",
    "api_key",
    "authorization",
    "cookie",
    "database_url",
    "credentials",
    "private_key",
    "session",
}


class ValidationError(ValueError):
    """Raised when user input fails structural or semantic validation."""
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.field = field


def validate_id(value: Any, field_name: str = "id", allow_none: bool = False) -> Optional[str]:
    """Validate that value is a safe alphanumeric/hyphen/underscore identifier."""
    if value is None:
        if allow_none:
            return None
        raise ValidationError(f"Field '{field_name}' is required", field=field_name)

    val_str = str(value).strip()
    if not val_str:
        if allow_none:
            return None
        raise ValidationError(f"Field '{field_name}' cannot be empty", field=field_name)

    if not ID_PATTERN.match(val_str):
        raise ValidationError(
            f"Field '{field_name}' contains invalid characters. Only alphanumeric, hyphens, and underscores allowed.",
            field=field_name,
        )
    return val_str


def validate_coordinates(lat: Any, lng: Any) -> Tuple[float, float]:
    """Validate latitude and longitude ranges."""
    try:
        f_lat = float(lat)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid latitude value '{lat}'", field="lat")

    try:
        f_lng = float(lng)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid longitude value '{lng}'", field="lng")

    if not (MIN_LAT <= f_lat <= MAX_LAT):
        raise ValidationError(f"Latitude must be between {MIN_LAT} and {MAX_LAT}, got {f_lat}", field="lat")
    if not (MIN_LNG <= f_lng <= MAX_LNG):
        raise ValidationError(f"Longitude must be between {MIN_LNG} and {MAX_LNG}, got {f_lng}", field="lng")

    return f_lat, f_lng


def validate_pagination(
    limit: Any = 50,
    offset: Any = 0,
    max_limit: int = 200,
    default_limit: int = 50,
) -> Tuple[int, int]:
    """Validate limit and offset query parameters."""
    try:
        lim = int(limit) if limit is not None else default_limit
    except (TypeError, ValueError):
        lim = default_limit

    try:
        off = int(offset) if offset is not None else 0
    except (TypeError, ValueError):
        off = 0

    if lim <= 0:
        lim = default_limit
    elif lim > max_limit:
        lim = max_limit

    if off < 0:
        off = 0

    return lim, off


def validate_string(
    value: Any,
    field_name: str,
    min_length: int = 1,
    max_length: int = 1000,
    allow_none: bool = False,
) -> Optional[str]:
    """Validate string length and type."""
    if value is None:
        if allow_none:
            return None
        raise ValidationError(f"Field '{field_name}' is required", field=field_name)

    val_str = str(value).strip()
    if len(val_str) < min_length:
        raise ValidationError(f"Field '{field_name}' must be at least {min_length} characters", field=field_name)
    if len(val_str) > max_length:
        raise ValidationError(f"Field '{field_name}' must not exceed {max_length} characters", field=field_name)

    return val_str


def validate_status_transition(
    current_status: str,
    target_status: str,
    allowed_transitions: Mapping[str, Sequence[str]],
) -> None:
    """Validate that transition from current_status to target_status is permitted.

    Comparison is case-insensitive and tolerates mapping keys in either case
    (operational statuses are uppercase; the map may be authored uppercase).
    """
    curr = str(current_status).strip().lower()
    tgt = str(target_status).strip().lower()

    if curr == tgt:
        return

    allowed: list[str] = []
    for key, targets in allowed_transitions.items():
        if str(key).strip().lower() == curr:
            allowed = [str(s).strip().lower() for s in targets]
            break
    if tgt not in allowed:
        raise ValidationError(
            f"Invalid state transition from '{current_status}' to '{target_status}'. "
            f"Allowed transitions: {', '.join(allowed) if allowed else 'none'}"
        )


# ---------------------------------------------------------------------------
# Operational enums & payload validation
# ---------------------------------------------------------------------------

VALID_URGENCIES = ("critical", "high", "medium", "low")
VALID_NEED_STATUSES = ("OPEN", "UNDER_REVIEW", "RESPONDING", "PARTIALLY_RESOLVED", "RESOLVED", "CLOSED")
VALID_OFFER_STATUSES = ("OFFERED", "ACCEPTED", "DEPLOYED", "WITHDRAWN", "EXPIRED")
VALID_OPERATION_STATUSES = ("PLANNING", "ACTIVE", "PAUSED", "COMPLETED", "CANCELLED")

# Allowed need lifecycle transitions (deterministic, mirrors the DB check
# constraints and existing frontend expectations).
NEED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "OPEN": ("UNDER_REVIEW", "RESPONDING", "RESOLVED", "CLOSED"),
    "UNDER_REVIEW": ("OPEN", "RESPONDING", "RESOLVED", "CLOSED"),
    "RESPONDING": ("PARTIALLY_RESOLVED", "RESOLVED", "CLOSED", "OPEN"),
    "PARTIALLY_RESOLVED": ("RESPONDING", "RESOLVED", "CLOSED"),
    "RESOLVED": ("OPEN", "CLOSED"),
    "CLOSED": ("OPEN",),
}


def validate_urgency(value: Any) -> str:
    """Validate a need urgency enum value."""
    v = str(value or "").strip().lower()
    if v not in VALID_URGENCIES:
        raise ValidationError(
            f"urgency must be one of: {', '.join(VALID_URGENCIES)}", field="urgency"
        )
    return v


def validate_enum(value: Any, allowed: Sequence[str], field_name: str) -> str:
    """Validate a value against an explicit enum tuple."""
    v = str(value or "").strip()
    if v not in allowed:
        raise ValidationError(
            f"{field_name} must be one of: {', '.join(allowed)}", field=field_name
        )
    return v


def validate_need_status(value: Any, current_status: Optional[str] = None) -> str:
    """Validate a need status value (and optionally its transition)."""
    v = validate_enum(value, VALID_NEED_STATUSES, "status")
    if current_status is not None:
        validate_status_transition(current_status, v, NEED_TRANSITIONS)
    return v


def validate_offer_status(value: Any) -> str:
    return validate_enum(value, VALID_OFFER_STATUSES, "status")


def validate_operation_status(value: Any) -> str:
    return validate_enum(value, VALID_OPERATION_STATUSES, "status")


def validate_quantity(value: Any, field_name: str = "quantity") -> int:
    """Validate a non-negative integer quantity (bounded for sanity)."""
    try:
        q = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be an integer", field=field_name)
    if q < 0:
        raise ValidationError(f"{field_name} cannot be negative", field=field_name)
    if q > 1_000_000_000:
        raise ValidationError(f"{field_name} is unreasonably large", field=field_name)
    return q


def sanitize_text(value: Any, max_length: int = 2000) -> str:
    """Coerce input to a bounded single-line-safe string.

    Strips control characters (except tab/newline) and enforces a length cap,
    so oversized or control-char payloads are rejected cleanly instead of
    flowing into storage, logs, or LLM prompts.
    """
    if value is None:
        return ""
    s = str(value)
    s = "".join(ch for ch in s if ch in "\t\n\r" or not unicodedata.category(ch).startswith("C"))
    return s.strip()[:max_length]


def validate_need_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a need creation payload; returns the normalized subset."""
    normalized: dict[str, Any] = {}

    if "need_type" in payload:
        normalized["need_type"] = sanitize_text(payload["need_type"], 128) or "other"
    if "title" in payload:
        title = sanitize_text(payload["title"], 512)
        if not title:
            raise ValidationError("title is required", field="title")
        normalized["title"] = title
    if "description" in payload:
        normalized["description"] = sanitize_text(payload["description"], 4000)
    if "urgency" in payload and payload["urgency"] is not None:
        normalized["urgency"] = validate_urgency(payload["urgency"])
    if "district_id" in payload and payload["district_id"]:
        normalized["district_id"] = validate_id(payload["district_id"], "district_id")
    if "location_name" in payload and payload["location_name"]:
        normalized["location_name"] = sanitize_text(payload["location_name"], 512)
    if payload.get("lat") is not None and payload.get("lon") is not None:
        lat, lon = validate_coordinates(payload["lat"], payload["lon"])
        normalized["lat"], normalized["lon"] = lat, lon
    if "requested_resources" in payload and payload["requested_resources"] is not None:
        resources = payload["requested_resources"]
        if not isinstance(resources, list):
            raise ValidationError("requested_resources must be a list", field="requested_resources")
        cleaned = []
        for r in resources[:50]:
            if not isinstance(r, dict):
                raise ValidationError("requested_resources entries must be objects", field="requested_resources")
            cleaned.append({
                "resource_type": sanitize_text(r.get("resource_type") or r.get("type"), 128),
                "quantity": validate_quantity(r.get("quantity", 0)),
                "unit": sanitize_text(r.get("unit"), 64),
            })
        normalized["requested_resources"] = cleaned
    if "confidence" in payload and payload["confidence"] is not None:
        try:
            conf = float(payload["confidence"])
        except (TypeError, ValueError):
            raise ValidationError("confidence must be numeric", field="confidence")
        if not (0.0 <= conf <= 1.0):
            raise ValidationError("confidence must be between 0 and 1", field="confidence")
        normalized["confidence"] = conf
    return normalized


def validate_offer_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a resource-offer payload; returns the normalized subset."""
    normalized: dict[str, Any] = {}
    rtype = sanitize_text(payload.get("resource_type"), 128)
    if not rtype:
        raise ValidationError("resource_type is required", field="resource_type")
    normalized["resource_type"] = rtype
    normalized["quantity"] = validate_quantity(payload.get("quantity", 0), "quantity")
    normalized["unit"] = sanitize_text(payload.get("unit") or "units", 64)
    if payload.get("lat") is not None and payload.get("lon") is not None:
        lat, lon = validate_coordinates(payload["lat"], payload["lon"])
        normalized["lat"], normalized["lon"] = lat, lon
    if payload.get("district_id"):
        normalized["district_id"] = validate_id(payload["district_id"], "district_id")
    if payload.get("location_name"):
        normalized["location_name"] = sanitize_text(payload.get("location_name"), 512)
    normalized["notes"] = sanitize_text(payload.get("notes", ""), 2000)
    return normalized


SENSITIVE_VALUE_PATTERNS = re.compile(
    r"(postgres(?:ql)?://[^\s\"']+|"           # DB connection strings
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"      # PEM keys
    r"AKIA[0-9A-Z]{16}|"                          # AWS access keys
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})" # JWT-shaped tokens
, re.VERBOSE)


def sanitize_sensitive_data(data: Any) -> Any:
    """
    Recursively redact passwords, secrets, tokens, and authorization headers from dictionaries/lists.
    """
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS:
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_sensitive_data(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_sensitive_data(item) for item in data]
    elif isinstance(data, str):
        # Redact secret-shaped values that appear inside free text
        # (connection strings, PEM keys, AWS keys, JWTs) even under a
        # harmless-looking field name.
        return SENSITIVE_VALUE_PATTERNS.sub("[REDACTED]", data)
    return data
