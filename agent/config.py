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
