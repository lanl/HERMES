from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from hermes.state.models.shared_models import StrictBaseModel, utc_now


class ExternalPayloadRef(StrictBaseModel):
    """Reference to a large state value stored under logs/payloads."""

    kind: Literal["external_payload_ref"] = "external_payload_ref"
    path: Path
    media_type: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    description: str | None = None
    source_path: Path | None = None

    @field_validator("path")
    @classmethod
    def require_relative_payload_path(cls, value: Path) -> Path:
        if value.is_absolute():
            msg = "external payload paths must be relative to the run bundle"
            raise ValueError(msg)
        return value
