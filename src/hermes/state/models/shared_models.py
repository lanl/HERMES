from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
try:
    from typing import TypeAliasType
except ImportError:  # pragma: no cover - compatibility for Python 3.11
    from typing_extensions import TypeAliasType

from pydantic import BaseModel, ConfigDict, Field

JsonScalar = str | int | float | bool | None
JsonValue = TypeAliasType(
    "JsonValue",
    JsonScalar | list["JsonValue"] | dict[str, "JsonValue"],
)
JsonObject = dict[str, JsonValue]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class FileReference(StrictBaseModel):
    """Path and optional verification details for a file used by HERMES."""

    path: Path
    media_type: str | None = Field(default=None, min_length=1)
    sha256: str | None = Field(default=None, pattern=r"^[A-Fa-f0-9]{64}$")
    size_bytes: int | None = Field(default=None, ge=0)
    created_at: datetime | None = None
    description: str | None = None
