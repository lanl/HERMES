# src/hermes/acquisition/models/destinations.py
"""
Destination and Preview configuration models for HERMES (Serval integration).

Manual references:
──────────────────
- Serval 2.1.5 manual (V1.22, May 2021)  → §4.4.1 "Destination JSON specification", Tables 4.2–4.4:contentReference[oaicite:0]{index=0}
- Serval 3.3.0 manual (V3.3, Oct 2023)   → §4.4.1–4.4.3 "Destination", with expanded OutputChannel fields.

Compatibility:
──────────────
The Serval 3.3 schema is a *superset* of 2.1.5:
- All 2.1.5 fields are still valid in 3.3.
- 3.3 adds optional fields like `Thresholds`, `Corrections`,
  `StopMeasurementOnDiskLimit`, and per-channel `QueueSize`.
- HERMES models therefore implement the full 3.3 schema,
  marking 3.3-only additions as optional for backward compatibility.

Usage:
──────
Use `model_dump(by_alias=True)` to produce JSON compatible with Serval.
All field aliases mirror the exact JSON keys in the manuals.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import Field, field_validator

# explicit imports (all __init__.py remain blank)
from .common import (
    HermesBaseModel,
    HermesImmutableModel,
    Mode,
    ImageFormat,
    HistogramFormat,
    SamplingMode,
)

# =============================================================================
# RAW output entries  (Destination.Raw[]) — present since Serval 2.1.5
# =============================================================================

class RawEntry(HermesBaseModel):
    """
    Single raw output sink entry.
    Serval 2.1.5: Table 4.4 (“OutputChannel object parameters”)
      - Base (URI)
      - FilePattern
      - SplitStrategy
      - QueueSize (implicit in later versions)
    Serval 3.3 adds explicit QueueSize.
    """
    base: str = Field(..., alias="Base", min_length=1,
        description="URI for output target (file://, tcp://, etc.). (§4.4.1 V1.22)")
    file_pattern: Optional[str] = Field(None, alias="FilePattern",
        description="Filename pattern for raw files. (§4.4.1 V1.22)")
    split_strategy: Optional[str] = Field(None, alias="SplitStrategy",
        description="File splitting strategy (e.g., 'frame', 'single_file'). (§4.4.1 V1.22)")
    queue_size: Optional[int] = Field(None, alias="QueueSize", ge=1,
        description="[3.3+] Producer/consumer queue bound for raw stream.")

# =============================================================================
# OutputChannel  (Destination.Image[] and Preview.ImageChannels[])
# =============================================================================

class OutputChannel(HermesBaseModel):
    """
    Image output channel.
    Serval 2.1.5: Table 4.4 lists Base, FilePattern, Format, Mode, IntegrationSize, SamplingMode.
    Serval 3.3 adds: Thresholds, Corrections, StopMeasurementOnDiskLimit, QueueSize.
    """
    base: Optional[str] = Field(None, alias="Base",
        description="URI for output (file/http/tcp). (§4.4.1 V1.22)")
    file_pattern: Optional[str] = Field(None, alias="FilePattern",
        description="Filename pattern for image outputs. (§4.4.1 V1.22)")
    format: ImageFormat = Field(..., alias="Format",
        description="Image format (tiff, pgm, png, jsonimage). (Table 4.4 V1.22)")
    mode: Mode = Field(..., alias="Mode",
        description="Acquisition mode (count, tot, toa, tof, count_fb). (Table 4.4 V1.22)")
    integration_size: int = Field(1, alias="IntegrationSize", ge=-1,
        description="Frames integrated per output image (-1 = all). (Table 4.4 V1.22)")
    sampling_mode: Optional[SamplingMode] = Field(None, alias="SamplingMode",
        description="skipOnFrame | skipOnPeriod (Table 4.4 V1.22)")
    skip: Optional[int] = Field(0, alias="Skip", ge=0,
        description="Frames/periods to skip. (Table 4.4 V1.22)")
    thresholds: Optional[List[int]] = Field(None, alias="Thresholds",
        description="[3.3+] List of thresholds used for multi-level imaging.")
    corrections: Optional[List[dict]] = Field(None, alias="Corrections",
        description="[3.3+] List of correction descriptors (maps, coefficients).")
    stop_measurement_on_disk_limit: Optional[bool] = Field(
        None, alias="StopMeasurementOnDiskLimit",
        description="[3.3+] Stop measurement automatically when disk limit reached.")
    queue_size: Optional[int] = Field(None, alias="QueueSize", ge=1,
        description="[3.3+] Queue size for image output channel.")

# =============================================================================
# HistogramChannel  (Preview.HistogramChannels[])
# =============================================================================

class HistogramChannel(HermesBaseModel):
    """
    Histogram channel for live preview histograms.
    Serval 2.1.5: only Format, Mode, Bins were documented in examples (§3.5).
    Serval 3.3 adds Base and QueueSize explicitly.
    """
    base: Optional[str] = Field(None, alias="Base",
        description="[3.3+] URI for histogram output (file/http/tcp).")
    format: HistogramFormat = Field(..., alias="Format",
        description="Histogram format (jsonhisto). (V1.22 Table 4.4)")
    mode: Mode = Field(..., alias="Mode",
        description="Acquisition mode for histogram. (V1.22 Table 4.4)")
    bins: int = Field(..., alias="Bins", ge=1, le=65536,
        description="Number of histogram bins. (V1.22 example §3.5)")
    queue_size: Optional[int] = Field(None, alias="QueueSize", ge=1,
        description="[3.3+] Queue size for histogram channel.")

# =============================================================================
# Preview  (Destination.Preview) — Present since 2.1.5, extended in 3.3
# =============================================================================

class Preview(HermesBaseModel):
    """
    Preview output configuration.

    Serval 2.1.5: Table 4.3 (Preview parameters) — SamplingMode, Period, ImageChannels, HistogramChannels.
    Serval 3.3 adds: QueueSize and expanded OutputChannel fields.
    """
    sampling_mode: Optional[SamplingMode] = Field(None, alias="SamplingMode",
        description="skipOnFrame | skipOnPeriod (Table 4.3 V1.22)")
    period: Optional[float] = Field(None, alias="Period", ge=0.0,
        description="Preview refresh period [s]. (Table 4.3 V1.22)")
    image_channels: List[OutputChannel] = Field(default_factory=list, alias="ImageChannels",
        description="Image preview channels. (Table 4.3 V1.22)")
    histogram_channels: List[HistogramChannel] = Field(default_factory=list, alias="HistogramChannels",
        description="Histogram preview channels. (Table 4.3 V1.22)")
    queue_size: Optional[int] = Field(None, alias="QueueSize", ge=1,
        description="[3.3+] Global preview queue size.")

    @field_validator("image_channels", "histogram_channels")
    @classmethod
    def _reasonable_counts(cls, v: list) -> list:
        if len(v) > 32:
            raise ValueError("Too many preview channels; consider ≤ 32.")
        return v

# =============================================================================
# Destination  (top-level /server/destination)
# =============================================================================

class Destination(HermesImmutableModel):
    """
    Complete destination configuration object.

    Serval 2.1.5: Table 4.2 ("destination top-level parameters") — Raw[], Image[], Preview object.
    Serval 3.3 keeps same structure and adds optional channel fields within.
    """
    raw: Optional[List[RawEntry]] = Field(default=None, alias="Raw",
        description="Raw data output(s). (Table 4.2 V1.22)")
    image: Optional[List[OutputChannel]] = Field(default=None, alias="Image",
        description="Image output(s). (Table 4.2 V1.22)")
    preview: Optional[Preview] = Field(default=None, alias="Preview",
        description="Live preview output. (Table 4.2 V1.22 / 4.3 V1.22)")

    @field_validator("raw")
    @classmethod
    def _raw_entries_valid(cls, entries: Optional[List[RawEntry]]) -> Optional[List[RawEntry]]:
        return entries

    @field_validator("image")
    @classmethod
    def _image_nonempty_if_present(cls, chans: Optional[List[OutputChannel]]) -> Optional[List[OutputChannel]]:
        if chans is not None and len(chans) == 0:
            raise ValueError("Destination.Image present but empty; either omit or include ≥ 1 channel.")
        return chans
