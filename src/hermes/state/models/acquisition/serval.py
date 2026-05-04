from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal, TypeAlias

from pydantic import ConfigDict, Field

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
ServalMeasurementStatus = Literal[
    "DA_IDLE",
    "DA_PREPARING",
    "DA_RECORDING",
    "DA_STOPPING",
]
ServalNotificationType = Literal["update", "info", "severe", "error"]
ServalNotificationDomain = Literal["server", "detector", "chip"]


class ServalApiModel(StrictBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class ServalDashboardDiskSpace(ServalApiModel):
    message: str | None = Field(default=None, alias="Message")
    path: Path | None = Field(default=None, alias="Path")
    free_space: int | None = Field(default=None, ge=0, alias="FreeSpace")
    write_speed: float | None = Field(default=None, ge=0, alias="WriteSpeed")
    lower_limit: int | None = Field(default=None, ge=0, alias="LowerLimit")
    disk_limit_reached: bool | None = Field(default=None, alias="DiskLimitReached")


class ServalDashboardNotification(ServalApiModel):
    type: ServalNotificationType | None = Field(default=None, alias="Type")
    domain: ServalNotificationDomain | None = Field(default=None, alias="Domain")
    message: str | None = Field(default=None, alias="Message")
    reference_id: str | None = Field(default=None, alias="ReferenceID")
    timestamp: int | None = Field(default=None, ge=0, alias="Timestamp")


class ServalDashboardServer(ServalApiModel):
    software_version: str | None = Field(default=None, alias="SoftwareVersion")
    software_timestamp: str | None = Field(default=None, alias="SoftwareTimestamp")
    software_commit: str | None = Field(default=None, alias="SoftwareCommit")
    software_build: str | None = Field(default=None, alias="SoftwareBuild")
    disk_space: list[ServalDashboardDiskSpace] = Field(
        default_factory=list,
        alias="DiskSpace",
    )
    notifications: list[ServalDashboardNotification] = Field(
        default_factory=list,
        alias="Notifications",
    )


class ServalDashboardMeasurement(ServalApiModel):
    start_date_time_ms: int | None = Field(default=None, ge=0, alias="StartDateTime")
    time_left_s: float | None = Field(default=None, ge=0, alias="TimeLeft")
    elapsed_time_s: float | None = Field(default=None, ge=0, alias="ElapsedTime")
    frame_count: int | None = Field(default=None, ge=0, alias="FrameCount")
    dropped_frames: int | None = Field(default=None, ge=0, alias="DroppedFrames")
    status: ServalMeasurementStatus | None = Field(default=None, alias="Status")
    pixel_event_rate: int | None = Field(default=None, ge=0, alias="PixelEventRate")
    tdc1_event_rate: int | None = Field(default=None, ge=0, alias="Tdc1EventRate")
    tdc2_event_rate: int | None = Field(default=None, ge=0, alias="Tdc2EventRate")


class ServalDashboardDetector(ServalApiModel):
    detector_type: str | None = Field(default=None, alias="DetectorType")


class ServalDashboard(ServalApiModel):
    server: ServalDashboardServer = Field(alias="Server")
    measurement: ServalDashboardMeasurement | None = Field(
        default=None,
        alias="Measurement",
    )
    detector: ServalDashboardDetector | None = Field(default=None, alias="Detector")


ServalDashboardSnapshot: TypeAlias = ServalDashboard


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
