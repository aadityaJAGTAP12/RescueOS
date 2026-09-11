"""
Configuration module: model setup, constants, and known locations.

This file is designed to be the ONLY place that changes when we migrate
from Ollama to AWS Bedrock in the future. All model-provider-specific code
is isolated here.
"""

from strands.models.ollama import OllamaModel

# ---------------------------------------------------------------------------
# Model setup
# Currently using Ollama llama3.2, but this will be replaced with
# AWS Bedrock credentials and initialization when we migrate.
# ---------------------------------------------------------------------------

model = OllamaModel(host="http://localhost:11434", model_id="llama3.2")

# ---------------------------------------------------------------------------
# Known reference locations (lon, lat) for Sivasagar region
# These are fixed coordinates for testing and demo purposes.
# ---------------------------------------------------------------------------

KNOWN_LOCATIONS = {
    "sivasagar": (94.6393, 26.9701),  # town center
    "sivasagar_flood_zone": (94.6698, 26.9894),  # confirmed flooded point
    "sivasagar_settlement_flood": (94.6285, 27.0249),  # settlement area
}

# ---------------------------------------------------------------------------
# Overpass API configuration
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

OVERPASS_HEADERS = {
    "User-Agent": "RescueOS-DisasterResponse/1.0",
    "Accept": "application/json",
}

# ---------------------------------------------------------------------------
# Cache directory for Overpass API responses
# Avoids hammering the public API during development/testing
# ---------------------------------------------------------------------------

CACHE_DIR = "data/cache"

# ---------------------------------------------------------------------------
# Typed Application Configuration — Production Hardening
# ---------------------------------------------------------------------------

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Settings:
    environment: str = field(default_factory=lambda: os.environ.get("ENVIRONMENT", "development").lower())
    database_url: Optional[str] = field(default_factory=lambda: os.environ.get("DATABASE_URL"))
    secret_key: str = field(default_factory=lambda: os.environ.get("RELIEFOS_SECRET_KEY", "reliefos-default-secret-key-change-in-prod"))
    auth_enforced: bool = field(default_factory=lambda: os.environ.get("AUTH_ENFORCED", "").lower() in ("true", "1", "yes"))
    cors_allowed_origins: List[str] = field(default_factory=lambda: [
        origin.strip() for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if origin.strip()
    ])
    proactive_scheduler_enabled: bool = field(default_factory=lambda: os.environ.get("PROACTIVE_SCHEDULER_ENABLED", "true").lower() in ("true", "1", "yes"))
    # Optional by default: the proactive scheduler enriches coordination but
    # the platform remains operable without it. Set
    # PROACTIVE_SCHEDULER_REQUIRED=true to make a scheduler failure fatal.
    proactive_scheduler_required: bool = field(default_factory=lambda: os.environ.get("PROACTIVE_SCHEDULER_REQUIRED", "false").lower() in ("true", "1", "yes"))
    proactive_scan_interval_seconds: int = field(default_factory=lambda: int(os.environ.get("PROACTIVE_SCAN_INTERVAL_SECONDS", "60")))
    stale_event_recovery_interval_seconds: int = field(default_factory=lambda: int(os.environ.get("STALE_EVENT_RECOVERY_INTERVAL_SECONDS", "120")))
    stale_event_threshold_seconds: int = field(default_factory=lambda: int(os.environ.get("STALE_EVENT_THRESHOLD_SECONDS", "300")))
    event_worker_enabled: bool = field(default_factory=lambda: os.environ.get("EVENT_WORKER_ENABLED", "true").lower() in ("true", "1", "yes"))
    # Mandatory by default: without the outbox worker AgentEvents never
    # dispatch and coordination stalls. Set EVENT_WORKER_REQUIRED=false to
    # explicitly accept a degraded (warn-only) startup.
    event_worker_required: bool = field(default_factory=lambda: os.environ.get("EVENT_WORKER_REQUIRED", "true").lower() in ("true", "1", "yes"))
    event_worker_poll_seconds: int = field(default_factory=lambda: int(os.environ.get("EVENT_WORKER_POLL_SECONDS", "5")))
    event_worker_batch_size: int = field(default_factory=lambda: int(os.environ.get("EVENT_WORKER_BATCH_SIZE", "10")))
    session_duration_seconds: int = field(default_factory=lambda: int(os.environ.get("SESSION_DURATION_SECONDS", "86400")))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO").upper())

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def validate_production_readiness(self) -> List[str]:
        """
        Validate critical security and durability constraints for production.
        Returns a list of error messages (empty if fully compliant).
        """
        errors = []
        if self.is_production:
            if not self.database_url or "postgresql" not in self.database_url.lower():
                errors.append("Production requires a durable PostgreSQL DATABASE_URL. In-memory storage is prohibited.")
            if self.secret_key == "reliefos-default-secret-key-change-in-prod" or len(self.secret_key) < 32:
                errors.append("Production requires a secure RELIEFOS_SECRET_KEY with at least 32 random characters.")
            if not self.auth_enforced:
                errors.append("Production requires AUTH_ENFORCED=true to protect multi-tenant organizational data.")
            if not self.cors_allowed_origins:
                errors.append("Production requires CORS_ALLOWED_ORIGINS to be set to trusted origins.")
        return errors


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Return the cached application configuration settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance

