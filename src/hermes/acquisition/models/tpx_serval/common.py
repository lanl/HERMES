# src/hermes/acquisition/models/common.py
"""
HERMES common model definitions.

This module provides:
- The project-wide base model hierarchy (HermesBaseModel + variants)
- Shared enums and type aliases used throughout detector, destination, etc.
- Small reusable value models (RangeF, Size2D, JsonPath)

All models here must remain PURE — no I/O, threading, or service calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, field_serializer


# =============================================================================
# Base model hierarchy
# =============================================================================

class HermesBaseModel(BaseModel):
    """Base class for all HERMES Pydantic models (strict & JSON-safe)."""
    model_config = ConfigDict(
        extra="forbid",                 # reject unknown fields
        populate_by_name=True,          # allow field names and aliases
        validate_assignment=True,       # revalidate on mutation
        ser_json_inf_nan=False,         # forbid NaN/Inf in JSON
        arbitrary_types_allowed=False,  # only JSON-serializable fields
        frozen=False,                   # may be made immutable in subclasses
    )


class HermesImmutableModel(HermesBaseModel):
    """Immutable variant used for static configurations."""
    model_config = ConfigDict(**HermesBaseModel.model_config, frozen=True)


class HermesRuntimeModel(HermesBaseModel):
    """
    Runtime state variant: adds UUID and timestamps.
    Used for live session data or telemetry.
    """
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def touch(self) -> None:
        """Update the 'updated_at' timestamp to now."""
        object.__setattr__(self, "updated_at", datetime.utcnow())


class HermesAPIPayloadModel(HermesBaseModel):
    """Lenient variant that ignores unknown keys (useful for Serval responses)."""
    model_config = ConfigDict(**HermesBaseModel.model_config, extra="ignore")


class HermesValueModel(HermesImmutableModel):
    """Immutable, hashable value objects (e.g., small geometry or numeric types)."""
    def __hash__(self) -> int:
        return hash(self.model_dump_json())


# =============================================================================
# Shared enums
# =============================================================================

class Mode(str, Enum):
    """Acquisition or image mode."""
    count = "count"
    tot = "tot"
    toa = "toa"
    tof = "tof"
    count_fb = "count_fb"


class ImageFormat(str, Enum):
    tiff = "tiff"
    pgm = "pgm"
    png = "png"
    jsonimage = "jsonimage"


class HistogramFormat(str, Enum):
    jsonhisto = "jsonhisto"


class SamplingMode(str, Enum):
    skip_on_frame = "skipOnFrame"
    skip_on_period = "skipOnPeriod"


class TriggerMode(str, Enum):
    internal = "internal"
    external = "external"
    software = "software"


class Polarity(str, Enum):
    positive = "positive"
    negative = "negative"


class TdcReference(str, Enum):
    internal = "internal"
    external = "external"


class AcquisitionStatus(str, Enum):
    DA_IDLE = "DA_IDLE"
    DA_RUNNING = "DA_RUNNING"
    DA_ERROR = "DA_ERROR"


# =============================================================================
# Constrained type aliases
# =============================================================================

Percent01 = Annotated[float, Field(ge=0.0, le=1.0)]
Seconds = Annotated[float, Field(gt=0.0)]
Milliseconds = Annotated[float, Field(gt=0.0)]
Nanoseconds = Annotated[int, Field(ge=0)]
Frames = Annotated[int, Field(ge=1)]
Pixels = Annotated[int, Field(ge=1)]
Port = Annotated[int, Field(ge=1, le=65535)]
PathStr = Annotated[str, Field(min_length=1)]


# =============================================================================
# Small reusable value models
# =============================================================================

class RangeF(HermesValueModel):
    """Inclusive float range."""
    min: float
    max: float

    @field_validator("max")
    @classmethod
    def check_order(cls, v, info):
        min_v = info.data.get("min")
        if min_v is not None and v < min_v:
            raise ValueError(f"max ({v}) must be >= min ({min_v})")
        return v


class Size2D(HermesValueModel):
    """Positive 2D size (e.g., image width/height in pixels)."""
    width: int = Field(..., ge=1)
    height: int = Field(..., ge=1)


class JsonPath(HermesValueModel):
    """Filesystem path that serializes to a POSIX string in JSON."""
    path: Path

    @field_validator("path", mode="before")
    @classmethod
    def normalize(cls, v):
        if isinstance(v, Path):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                raise ValueError("path cannot be empty")
            return Path(s)
        raise TypeError("path must be str or Path")

    @field_serializer("path")
    def ser_path(self, v: Path):
        return v.as_posix()


class Duration(HermesValueModel):
    """Duration in seconds, optionally built from timedelta."""
    seconds: float = Field(ge=0.0)

    @classmethod
    def from_timedelta(cls, td: timedelta) -> Duration:
        return cls(seconds=td.total_seconds())


# =============================================================================
# Utility mixins
# =============================================================================

class Named(HermesBaseModel):
    """Adds a simple 'name' field."""
    name: str = Field(..., min_length=1)


class Timestamped(HermesRuntimeModel):
    """Base with runtime timestamps only."""
    pass
