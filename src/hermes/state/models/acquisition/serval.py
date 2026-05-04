from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal, TypeAlias

from pydantic import Field

from hermes.state.models.detector import DetectorSnapshot, SnapshotPayload
from hermes.state.models.shared_models import ArtifactRef, JsonObject, StrictBaseModel

AcquisitionRunStatus = Literal[
    "planned",
    "configured",
    "running",
    "completed",
    "failed",
    "stopped",
    "unknown",
]
ServalDashboardSnapshot: TypeAlias = SnapshotPayload


class ServalEnvironment(StrictBaseModel):
    """SERVAL backend identity and latest backend status snapshot."""

    serval_url: str = Field(min_length=1)
    version: str | None = None
    dashboard: ServalDashboardSnapshot | None = None


class ServalDestination(StrictBaseModel):
    name: str = Field(min_length=1)
    destination_type: str = Field(min_length=1)
    path: Path | None = None
    enabled: bool = True
    options: JsonObject = Field(default_factory=dict)


class DestinationConfiguration(StrictBaseModel):
    destinations: list[ServalDestination] = Field(default_factory=list)
    raw_response: SnapshotPayload | None = None


class CalibrationState(StrictBaseModel):
    pixel_config_file: ArtifactRef | None = None
    dacs_file: ArtifactRef | None = None
    applied_at: datetime | None = None
    status: str | None = None
    responses: JsonObject = Field(default_factory=dict)


class ServalAcquisitionPlan(StrictBaseModel):
    trigger_mode: str | None = None
    trigger_count: int | None = Field(default=None, ge=0)
    exposure_time_s: float | None = Field(default=None, ge=0)
    trigger_period_s: float | None = Field(default=None, ge=0)
    expected_artifacts: list[ArtifactRef] = Field(default_factory=list)
    options: JsonObject = Field(default_factory=dict)


class ServalAcquisitionResult(StrictBaseModel):
    status: AcquisitionRunStatus = "unknown"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stop_reason: str | None = None
    frames: int | None = Field(default=None, ge=0)
    dropped_frames: int | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    final_dashboard: ServalDashboardSnapshot | None = None


class ServalAcquisitionState(StrictBaseModel):
    mode: Literal["serval"] = "serval"
    serval_environment: ServalEnvironment | None = None
    requested_plan: ServalAcquisitionPlan | None = None
    destination_configuration: DestinationConfiguration | None = None
    initial_detector_snapshot: DetectorSnapshot | None = None
    final_detector_snapshot: DetectorSnapshot | None = None
    calibration: CalibrationState | None = None
    result: ServalAcquisitionResult | None = None
