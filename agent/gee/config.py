"""
Flood Pipeline Configuration

Defines all configurable parameters for the Sentinel-1 flood-mapping
pipeline. Defaults reproduce the confirmed Sivasagar methodology.

SCIENTIFIC CAVEATS (preserved from original Sivasagar analysis):
- Original AOI was a manual rectangle, not administrative boundary.
- -3 dB threshold was not ground-truth optimized.
- Binary flood mask, not flood depth.
- Connected-component and area filtering can remove genuine small
  inundation.
- Result is approximate/reconstructed.
- Visual validation against MODIS/Worldview and point-level checks were
  used for Sivasagar.

The original Sivasagar parameters were not exhaustively optimized
against ground truth and may need re-tuning for other terrain/noise
conditions.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FloodPipelineConfig:
    """
    Configuration for Sentinel-1 SAR flood-mapping pipeline.

    All parameters are overridable per-district and per-window.
    Default values reproduce the original Sivasagar methodology.
    """

    # --- Collection filtering ---
    collection: str = "COPERNICUS/S1_GRD"
    polarization: str = "VH"
    instrument_mode: str = "IW"
    orbit_pass: str = "DESCENDING"

    # --- Temporal windows ---
    pre_start: str = ""     # e.g. "2026-06-25"
    pre_end: str = ""       # e.g. "2026-07-05"
    event_start: str = ""   # e.g. "2026-08-08"
    event_end: str = ""     # e.g. "2026-08-13"

    # --- Speckle reduction ---
    speckle_radius_m: float = 50.0

    # --- Change detection ---
    threshold_db: float = -3.0

    # --- Connected component cleanup ---
    connected_pixel_neighborhood: int = 100
    min_connected_pixels: int = 60

    # --- Vectorization ---
    vector_scale: float = 10.0
    vector_geometry_type: str = "polygon"
    vector_max_pixels: float = 1e9

    # --- Area filter ---
    area_threshold_m2: float = 5000.0

    # --- Metadata ---
    district_id: str = ""
    methodology_version: str = "1.0"
    provenance: str = "REAL"
    confidence: float = 0.8

    # --- Export ---
    export_prefix: str = "reliefos_flood"

    def get_metadata(self) -> dict:
        """Generate the full metadata dict for this configuration."""
        return {
            "district_id": self.district_id,
            "pre_start": self.pre_start,
            "pre_end": self.pre_end,
            "event_start": self.event_start,
            "event_end": self.event_end,
            "source": "Sentinel-1 SAR",
            "collection": self.collection,
            "polarization": self.polarization,
            "orbit": self.orbit_pass,
            "instrument": self.instrument_mode,
            "threshold_db": self.threshold_db,
            "speckle_radius_m": self.speckle_radius_m,
            "min_connected_pixels": self.min_connected_pixels,
            "connected_pixel_neighborhood": self.connected_pixel_neighborhood,
            "vector_scale": self.vector_scale,
            "area_threshold_m2": self.area_threshold_m2,
            "methodology_version": self.methodology_version,
            "provenance": self.provenance,
            "confidence": self.confidence,
        }

    def generate_filename(self) -> str:
        """
        Generate export filename from district + event period.

        Example: sivasagar_flood_2026-07-19_2026-07-22.geojson
        """
        district = self.district_id or "unknown"
        start = self.event_start or "unknown-start"
        end = self.event_end or "unknown-end"
        return f"{district}_flood_{start}_{end}.geojson"


# ---------------------------------------------------------------------------
# Default config — general purpose defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = FloodPipelineConfig()


# ---------------------------------------------------------------------------
# Sivasagar regression config — reproduces original methodology exactly
# ---------------------------------------------------------------------------

SIVASAGAR_REGRESSION_CONFIG = FloodPipelineConfig(
    # Original AOI was a rectangle [94.55, 26.85, 95.05, 27.15]
    # But for the generalized pipeline we use the district geometry.
    # The regression config here only specifies the processing parameters.
    district_id="sivasagar",
    pre_start="2026-06-25",
    pre_end="2026-07-05",
    event_start="2026-08-08",
    event_end="2026-08-13",
    threshold_db=-3.0,
    speckle_radius_m=50.0,
    connected_pixel_neighborhood=100,
    min_connected_pixels=60,
    vector_scale=10.0,
    area_threshold_m2=5000.0,
)


# ---------------------------------------------------------------------------
# Per-district date window examples (optional overrides)
# ---------------------------------------------------------------------------

# These are illustrative date windows for future use.
# The pipeline does NOT hardcode them; callers supply them.
DISTRICT_EXAMPLE_WINDOWS = {
    "sivasagar": {
        "pre": ("2026-06-25", "2026-07-05"),
        "event": ("2026-08-08", "2026-08-13"),
    },
    "jorhat": {
        # July 2026 flood period — validate against actual S1 acquisitions
        "pre": ("2026-06-25", "2026-07-05"),
        "event": ("2026-07-18", "2026-07-25"),
    },
    "charaideo": {
        "pre": ("2026-06-25", "2026-07-05"),
        "event": ("2026-08-08", "2026-08-13"),
    },
    "golaghat": {
        "pre": ("2026-06-25", "2026-07-05"),
        "event": ("2026-08-08", "2026-08-13"),
    },
}
