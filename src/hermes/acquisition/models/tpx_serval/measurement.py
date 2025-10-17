# src/hermes/acquisition/models/measurement.py
"""
Measurement configuration models for HERMES (Serval integration)

Manual references:
- Serval 3.3.0 (V3.3, Oct 2023): §4.6 "/measurement requests"
  * §4.6.2: PUT endpoints for measurement + config (table of endpoints/examples)
  * §4.6.3: "Measurement config JSON structure" + Tables 4.11–4.13
    - Top-level MeasurementConfig → Table 4.11
    - Corrections details        → Table 4.12
    - TimeOfFlight details       → Table 4.13
  These sections show the shape of /measurement/config and related blocks. :contentReference[oaicite:0]{index=0}

- Serval 2.1.5 (V1.22, May 2021): The 2.x manual largely documents start/stop and preview/image
  usage; it does NOT provide a full /measurement/config JSON schema as in v3.3. The v3.3 schema is
  a superset; to remain compatible, v3-only fields are optional in our models. :contentReference[oaicite:1]{index=1}

Versioning notes:
- This file models the v3.3 schema. All v3.3-only fields are optional; older Serval will omit them.
- Controllers (not models) should detect server capabilities (e.g., via /dashboard) before calling
  v3-only endpoints like PUT /measurement/config. :contentReference[oaicite:2]{index=2}

Use `model_dump(by_alias=True)` to emit exact Serval JSON keys.
"""

from __future__ import annotations
from typing import Optional, List, Literal, Union
from pydantic import Field, field_validator

# explicit imports (all __init__.py files remain blank)
from .common import (
    HermesBaseModel,
    HermesImmutableModel,
    Mode,  # "count" | "tot" | "toa" | "tof" | "count_fb" — listed among channel modes in manuals. :contentReference[oaicite:3]{index=3}
)

# ──────────────────────────────────────────────────────────────────────────────
# Corrections block (Table 4.12 in v3.3) — v3-only (not fully specified in 2.1.5)
# ──────────────────────────────────────────────────────────────────────────────
# In the v3.3 manual, the example under §4.6.3 shows:
#   "Corrections": { "Multiply": [1.5, 2.0, ...], "Gapfill": {...} }
# Earlier drafts/examples sometimes used file references; to be pragmatic:
# - Accept either a simple list of floats (as per v3.3 example) OR an array of objects
#   with {Path, Scale} for future flexibility. (Object form is not mandated by v3.3 text,
#   but is harmless and ergonomic if your pipelines want indirection.) :contentReference[oaicite:4]{index=4}

class CorrectionEntry(HermesBaseModel):
    # Optional/ergonomic object form (not required by v3.3; accepted by our model for flexibility)
    path: Optional[str] = Field(None, alias="Path", description="[Optional] Path or key to correction data.")
    scale: float = Field(1.0, alias="Scale", description="Multiplicative factor.")


class Gapfill(HermesBaseModel):
    """
    Gap-fill configuration.
    v3.3 Table 4.12 shows 'Gapfill' nested under 'Corrections'.

    Strategy wording in the PDF example appears uppercase ("NEIGHBOUR"),
    while earlier docs/use sometimes say "nearest". We accept a small set to
    stay compatible across versions while keeping validation useful. :contentReference[oaicite:5]{index=5}
    """
    distance: int = Field(
        0, alias="Distance", ge=0,
        description="Pixel distance threshold (0 disables). [v3.3 Table 4.12]"
    )
    strategy: Literal["none", "nearest", "NEIGHBOUR", "NEIGHBOR", "linear"] = Field(
        "none", alias="Strategy",
        description="Gap-fill algorithm. [v3.3 Table 4.12]"
    )


class Corrections(HermesBaseModel):
    """
    Corrections container (v3.3 Table 4.12). v2.1.5 did not specify this structure.
    We keep it optional in MeasurementConfig for backward compatibility. :contentReference[oaicite:6]{index=6}
    """
    # Either a flat list of numeric multipliers (per v3.3 example) OR a list of objects:
    multiply: Optional[List[Union[float, CorrectionEntry]]] = Field(
        default_factory=list, alias="Multiply",
        description="Correction multipliers (v3.3 example shows float list)."
    )
    gapfill: Gapfill = Field(
        default_factory=Gapfill, alias="Gapfill",
        description="Gap-fill config (v3.3 Table 4.12)."
    )

# ──────────────────────────────────────────────────────────────────────────────
# Time-of-Flight block (Table 4.13 in v3.3)
# ──────────────────────────────────────────────────────────────────────────────
# Note: v3.3 Table 4.13 defines 'TimeOfFlight' with TdcReference/Min/Max. The PDF text is
# partially OCR'd in the snippet; across versions the intended structure is a reference selector
# plus numeric window. We keep a conservative, commonly used shape:
#   - TdcReference: "internal" | "external"
#   - Min, Max: floats in seconds (v3.3 table shows floats; older code sometimes modeled ns).
# If your environment expects ns, you can wrap conversions in the service layer. :contentReference[oaicite:7]{index=7}

class TimeOfFlight(HermesBaseModel):
    tdc_reference: Literal["internal", "external"] = Field(
        "internal", alias="TdcReference",
        description="TOF reference source. [v3.3 Table 4.13]"
    )
    min_s: float = Field(
        0.0, alias="Min", ge=0.0,
        description="TOF window start [s]. [v3.3 Table 4.13]"
    )
    max_s: float = Field(
        0.0, alias="Max", ge=0.0,
        description="TOF window end [s] (≥ Min). [v3.3 Table 4.13]"
    )

    @field_validator("max_s")
    @classmethod
    def _check_order(cls, v, info):
        min_s = info.data.get("min_s")
        if min_s is not None and v < min_s:
            raise ValueError(f"TimeOfFlight.Max ({v}) must be >= TimeOfFlight.Min ({min_s}).")
        return v

# ──────────────────────────────────────────────────────────────────────────────
# MeasurementConfig (Table 4.11 in v3.3) — v3-only; optional in legacy 2.x flows
# ──────────────────────────────────────────────────────────────────────────────
# v3.3 introduces PUT /measurement/config (and subpaths) to upload measurement settings.
# In 2.1.5, you typically controlled acquisition through detector config + start/stop;
# there was no full JSON schema for /measurement/config. We therefore keep this object
# v3.3-accurate but safe if fields are missing on legacy servers. :contentReference[oaicite:8]{index=8}

class MeasurementConfig(HermesImmutableModel):
    """
    Root measurement configuration for /measurement/config.

    v3.3 Table 4.11 fields (top-level):
      - Mode          : acquisition mode (count, tot, toa, tof, count_fb)
      - StartDelay    : seconds (≥ 0)
      - StopDelay     : seconds (≥ 0)
      - FrameCount    : integer (0 = continuous)
      - AutoSave      : boolean
      - TimeOfFlight  : nested TOF (Table 4.13)
      - Corrections   : nested corrections (Table 4.12)
    v2.1.5: this structured config is not documented; treat as v3-only. :contentReference[oaicite:9]{index=9}
    """
    mode: Mode = Field(
        ..., alias="Mode",
        description="Acquisition mode. [v3.3 Table 4.11]"
    )
    start_delay_s: float = Field(
        0.0, alias="StartDelay", ge=0.0,
        description="Delay before acquisition start [s]. [v3.3 Table 4.11]"
    )
    stop_delay_s: float = Field(
        0.0, alias="StopDelay", ge=0.0,
        description="Delay after acquisition stop [s]. [v3.3 Table 4.11]"
    )
    time_of_flight: Optional[TimeOfFlight] = Field(
        None, alias="TimeOfFlight",
        description="Time-of-flight window. [v3.3 Table 4.13]"
    )
    corrections: Optional[Corrections] = Field(
        default_factory=Corrections, alias="Corrections",
        description="Corrections (multiply + gap-fill). [v3.3 Table 4.12]"
    )
    frame_count: Optional[int] = Field(
        None, alias="FrameCount", ge=0,
        description="Number of frames (0 = continuous). [v3.3 Table 4.11]"
    )
    auto_save: Optional[bool] = Field(
        True, alias="AutoSave",
        description="Automatically save frames/images. [v3.3 Table 4.11]"
    )
