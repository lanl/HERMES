from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import ConfigDict, Field, model_validator

from hermes.state.models.detector import DetectorConfiguration, DetectorSnapshot
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
ServalDestinationFormat = Literal["tiff", "pgm", "png", "jsonimage", "jsonhisto"]
ServalDestinationMode = Literal["count", "tot", "toa", "tof", "count_fb"]
ServalRawSplitStrategy = Literal["single_file", "frame", "SINGLE_FILE", "FRAME"]
ServalPreviewSamplingMode = Literal["skipOnFrame", "skipOnPeriod"]
ServalIntegrationMode = Literal["sum", "average", "last"]
ServalCorrection = Literal["multiply"]
ServalConfigLoadFormat = Literal["pixelconfig", "dacs"]
ServalDestinationBase = Annotated[str, Field(min_length=1)]
ServalConfigLoadPath = Annotated[str, Field(min_length=1)]
ServalThreshold = Annotated[int, Field(ge=0, le=7)]
ServalQueueSize = Annotated[int, Field(gt=0)]
ServalIntegrationSize = Annotated[int, Field(ge=-1, le=32)]


class ServalApiModel(StrictBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class ServalDashboardDiskSpace(ServalApiModel):
    message: str | None = Field(default=None, alias="Message")
    path: str | None = Field(default=None, alias="Path")
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


class ServalRawDestination(ServalApiModel):
    base: ServalDestinationBase = Field(alias="Base")
    file_pattern: str | None = Field(default=None, min_length=1, alias="FilePattern")
    split_strategy: ServalRawSplitStrategy | None = Field(
        default=None,
        alias="SplitStrategy",
    )
    queue_size: ServalQueueSize | None = Field(default=None, alias="QueueSize")


class ServalOutputChannel(ServalApiModel):
    base: ServalDestinationBase = Field(alias="Base")
    file_pattern: str | None = Field(default=None, min_length=1, alias="FilePattern")
    format: ServalDestinationFormat | None = Field(default=None, alias="Format")
    mode: ServalDestinationMode | None = Field(default=None, alias="Mode")
    thresholds: list[ServalThreshold] | None = Field(default=None, alias="Thresholds")
    integration_size: ServalIntegrationSize | None = Field(
        default=None,
        alias="IntegrationSize",
    )
    integration_mode: ServalIntegrationMode | None = Field(
        default=None,
        alias="IntegrationMode",
    )
    stop_measurement_on_disk_limit: bool | None = Field(
        default=None,
        alias="StopMeasurementOnDiskLimit",
    )
    queue_size: ServalQueueSize | None = Field(default=None, alias="QueueSize")
    corrections: list[ServalCorrection] | None = Field(
        default=None,
        alias="Corrections",
    )
    number_of_bins: int | None = Field(default=None, ge=0, alias="NumberOfBins")
    bin_width: float | None = Field(default=None, gt=0, alias="BinWidth")
    offset: int | None = Field(default=None, alias="Offset")


class ServalPreviewDestination(ServalApiModel):
    period: float | None = Field(default=None, ge=0, alias="Period")
    sampling_mode: ServalPreviewSamplingMode | None = Field(
        default=None,
        alias="SamplingMode",
    )
    image_channels: list[ServalOutputChannel] = Field(
        default_factory=list,
        alias="ImageChannels",
    )
    histogram_channels: list[ServalOutputChannel] = Field(
        default_factory=list,
        alias="HistogramChannels",
    )


class DestinationConfiguration(ServalApiModel):
    raw: list[ServalRawDestination] = Field(default_factory=list, alias="Raw")
    image: list[ServalOutputChannel] = Field(default_factory=list, alias="Image")
    preview: ServalPreviewDestination | None = Field(default=None, alias="Preview")


class ServalConfigLoadRequest(ServalApiModel):
    format: ServalConfigLoadFormat
    serval_file_path: ServalConfigLoadPath = Field(alias="file")
    source_artifact: ArtifactRef | None = None


class ServalConfigLoadResult(StrictBaseModel):
    applied_at: datetime | None = None
    status: str | None = Field(default=None, min_length=1)
    http_status_code: int | None = Field(default=None, ge=100, le=599)
    response_text: str | None = None
    response_summary: JsonObject = Field(default_factory=dict)


class CalibrationState(StrictBaseModel):
    pixel_config_file: ArtifactRef | None = None
    dacs_file: ArtifactRef | None = None
    pixel_config_load_request: ServalConfigLoadRequest | None = None
    dacs_load_request: ServalConfigLoadRequest | None = None
    pixel_config_load_result: ServalConfigLoadResult | None = None
    dacs_load_result: ServalConfigLoadResult | None = None

    @model_validator(mode="after")
    def validate_load_request_formats(self) -> CalibrationState:
        if (
            self.pixel_config_load_request is not None
            and self.pixel_config_load_request.format != "pixelconfig"
        ):
            msg = "pixel_config_load_request must use format='pixelconfig'"
            raise ValueError(msg)
        if (
            self.dacs_load_request is not None
            and self.dacs_load_request.format != "dacs"
        ):
            msg = "dacs_load_request must use format='dacs'"
            raise ValueError(msg)
        return self


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
    requested_detector_config: DetectorConfiguration | None = None
    requested_destination_configuration: DestinationConfiguration | None = None
    applied_detector_config: DetectorConfiguration | None = None
    applied_destination_configuration: DestinationConfiguration | None = None
    initial_detector_snapshot: DetectorSnapshot | None = None
    final_detector_snapshot: DetectorSnapshot | None = None
    calibration: CalibrationState | None = None
    result: ServalAcquisitionResult | None = None
