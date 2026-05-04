from __future__ import annotations

from datetime import datetime

from pydantic import Field

from hermes.state.models.payloads import ExternalPayloadRef
from hermes.state.models.shared_models import JsonObject, StrictBaseModel, utc_now

SnapshotPayload = JsonObject | ExternalPayloadRef


class DetectorInfo(StrictBaseModel):
    detector_type: str | None = None
    serial_number: str | None = None
    firmware_version: str | None = None
    chip_count: int | None = Field(default=None, ge=0)
    chip_ids: list[str] = Field(default_factory=list)
    raw: SnapshotPayload | None = None


class DetectorHealth(StrictBaseModel):
    status: str | None = None
    readings: JsonObject = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    raw: SnapshotPayload | None = None


class DetectorLayout(StrictBaseModel):
    layout: SnapshotPayload | None = None
    summary: JsonObject = Field(default_factory=dict)


class DetectorConfiguration(StrictBaseModel):
    pixel_config: str | ExternalPayloadRef | None = None
    dacs: list[dict[str, int]] | ExternalPayloadRef | None = None
    settings: SnapshotPayload | None = None


class DetectorSnapshot(StrictBaseModel):
    """Detector-specific state from `/detector/*` endpoints."""

    captured_at: datetime = Field(default_factory=utc_now)
    info: DetectorInfo | None = None
    health: DetectorHealth | None = None
    layout: DetectorLayout | None = None
    configuration: DetectorConfiguration | None = None
