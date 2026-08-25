from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from pydantic import ConfigDict, Field, field_validator, model_validator

from hermes.state.models.detector import (
    DetectorConfiguration,
    DetectorSnapshot,
    DetectorTriggerMode,
)
from hermes.state.models.shared_models import FileReference, StrictBaseModel

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
ServalDestinationBase = Annotated[str, Field(min_length=1)]
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


class ServalServer(StrictBaseModel):
    """Where the SERVAL server lives and which version to run.

    HERMES launches SERVAL itself with `java -jar <program_path>` when a program
    path is given and the server at `url` does not already answer.

    HERMES never talks to the camera directly; SERVAL does. When `tcp_ip` is set,
    HERMES passes it (and `tcp_port` if given) to SERVAL as `--tcpIp`/`--tcpPort`
    launch flags so SERVAL connects to that camera. When both are unset, SERVAL
    autodiscovers the camera.

    `version` is the SERVAL version HERMES is driving (e.g. "3.3.0"). Options and
    launch flags differ between versions: `tcp_ip`/`tcp_port` only exist from
    SERVAL 3.0 onward; older versions point at the camera with `spidrNet` alone.
    HERMES uses `major_version` to emit the launch flags that version accepts.
    """

    url: str = Field(min_length=1)
    program_path: Path | None = None
    version: str | None = None
    tcp_ip: str | None = None
    tcp_port: int | None = Field(default=None, ge=1, le=65535)

    @property
    def major_version(self) -> int | None:
        """Leading major version parsed from `version` ("3.3.0" -> 3).

        None when `version` is unset or does not begin with a number.
        """
        if self.version is None:
            return None
        match = re.match(r"\s*v?(\d+)", self.version)
        return int(match.group(1)) if match else None

    @field_validator("program_path")
    @classmethod
    def validate_program_path(cls, value: Path | None) -> Path | None:
        if value is not None and value.suffix.lower() != ".jar":
            msg = "SERVAL program_path must be a .jar file"
            raise ValueError(msg)
        return value

    @field_validator("tcp_ip")
    @classmethod
    def validate_tcp_ip(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ipaddress.ip_address(value)
            except ValueError as error:
                msg = f"SERVAL tcp_ip must be a valid IP address: {value!r}"
                raise ValueError(msg) from error
        return value

    @model_validator(mode="after")
    def validate_tcp_needs_v3(self) -> ServalServer:
        if (self.tcp_ip is not None or self.tcp_port is not None) and (
            self.major_version is not None and self.major_version < 3
        ):
            msg = (
                "SERVAL tcp_ip/tcp_port require version 3.0 or newer; "
                f"version {self.version!r} points at the camera with spidrNet only"
            )
            raise ValueError(msg)
        return self


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


class PixelConfigFile(StrictBaseModel):
    """Saved SoPhy pixel-configuration file used for this run."""

    path: Path
    source_path: Path | None = None
    file_hash: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")

    @field_validator("path")
    @classmethod
    def validate_saved_path(cls, value: Path) -> Path:
        if value.is_absolute() or ".." in value.parts:
            msg = "pixel config file path must be relative to the run directory"
            raise ValueError(msg)
        if value.suffix.lower() != ".bpc":
            msg = "pixel config file path must end with .bpc"
            raise ValueError(msg)
        return value


class DacsFile(StrictBaseModel):
    """Saved SoPhy DAC-settings file used for this run."""

    path: Path
    source_path: Path | None = None
    file_hash: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")

    @field_validator("path")
    @classmethod
    def validate_saved_path(cls, value: Path) -> Path:
        if value.is_absolute() or ".." in value.parts:
            msg = "DAC settings file path must be relative to the run directory"
            raise ValueError(msg)
        if value.suffix.lower() != ".dacs":
            msg = "DAC settings file path must end with .dacs"
            raise ValueError(msg)
        return value


class PixelConfigLoad(StrictBaseModel):
    """Result of asking SERVAL to load a .bpc file."""

    server_file_path: str = Field(min_length=1)
    applied_at: datetime | None = None
    status: str | None = Field(default=None, min_length=1)
    http_status_code: int | None = Field(default=None, ge=100, le=599)
    server_response_body: str | None = None


class DacsLoad(StrictBaseModel):
    """Result of asking SERVAL to load a .dacs file."""

    server_file_path: str = Field(min_length=1)
    applied_at: datetime | None = None
    status: str | None = Field(default=None, min_length=1)
    http_status_code: int | None = Field(default=None, ge=100, le=599)
    server_response_body: str | None = None


class CalibrationState(StrictBaseModel):
    pixel_config_file: PixelConfigFile | None = None
    dacs_file: DacsFile | None = None
    pixel_config_load: PixelConfigLoad | None = None
    dacs_load: DacsLoad | None = None


class CalibrationFiles(StrictBaseModel):
    """User-supplied SoPhy calibration files to load into the detector.

    These are the source `.bpc` and `.dacs` paths named in the config file.
    During a run HERMES copies them into the run's config directory and records
    the saved copies and hashes on `CalibrationState`.
    """

    pixel_config_file: Path
    dacs_file: Path

    @field_validator("pixel_config_file")
    @classmethod
    def validate_pixel_config_suffix(cls, value: Path) -> Path:
        if value.suffix.lower() != ".bpc":
            msg = "pixel_config_file must end with .bpc"
            raise ValueError(msg)
        return value

    @field_validator("dacs_file")
    @classmethod
    def validate_dacs_suffix(cls, value: Path) -> Path:
        if value.suffix.lower() != ".dacs":
            msg = "dacs_file must end with .dacs"
            raise ValueError(msg)
        return value


class ServalRunTiming(StrictBaseModel):
    """Exposure and trigger settings for the run.

    Any field set here overrides the matching field in the detector
    configuration. `trigger_count` maps to the detector config's `n_triggers`.
    """

    trigger_mode: DetectorTriggerMode | None = None
    exposure_time_s: float | None = Field(default=None, ge=0, le=10)
    trigger_period_s: float | None = Field(default=None, ge=0, le=50)
    trigger_count: int | None = Field(default=None, ge=0)


class ServalAcquisitionConfig(StrictBaseModel):
    """Everything HERMES loads from the acquisition config file.

    The detector configuration comes either inline as `detector_config` or from
    a JSON file named by `detector_config_file`; when both are given the file
    wins. `run_timing` then overrides the matching detector-config fields.
    """

    serval: ServalServer
    calibration_files: CalibrationFiles | None = None
    detector_config: DetectorConfiguration | None = None
    detector_config_file: Path | None = None
    run_timing: ServalRunTiming | None = None

    @field_validator("detector_config_file")
    @classmethod
    def validate_detector_config_suffix(cls, value: Path | None) -> Path | None:
        if value is not None and value.suffix.lower() != ".json":
            msg = "detector_config_file must be a .json file"
            raise ValueError(msg)
        return value


class ServalAcquisitionResult(StrictBaseModel):
    """Outcome of one measurement: when it ran and what it produced."""

    started_at: datetime | None = None
    completed_at: datetime | None = None
    stop_reason: str | None = None
    frames: int | None = Field(default=None, ge=0)
    dropped_frames: int | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    output_files: list[FileReference] = Field(default_factory=list)


class ServalAcquisitionState(StrictBaseModel):
    """Durable acquisition state: the loaded config plus what HERMES observed.

    `config` is what was loaded from the config file. Every other field is
    filled in by HERMES as the run progresses: the latest dashboard, the
    detector snapshots taken before and after, the destination that was
    configured, the calibration files that were saved and loaded, and the
    measurement result.
    """

    mode: Literal["serval"] = "serval"
    config: ServalAcquisitionConfig
    status: AcquisitionRunStatus = "planned"
    dashboard: ServalDashboardSnapshot | None = None
    initial_detector_snapshot: DetectorSnapshot | None = None
    final_detector_snapshot: DetectorSnapshot | None = None
    destination: DestinationConfiguration | None = None
    calibration: CalibrationState | None = None
    result: ServalAcquisitionResult | None = None
