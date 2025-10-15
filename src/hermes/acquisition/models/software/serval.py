"""
serval.py

Pydantic models for SERVAL software-side configuration and metadata.

Covers:
- /server/destination payload (DestinationsConfig and submodels)
- /measurement/config payload (MeasurementConfig and submodels)
- Basic ServalConfig for local paths and connectivity info
"""

from __future__ import annotations

from typing import List, Literal, Optional
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, model_validator


# -----------------------------------------------------------------------------
# Destination configuration (sent to and received from /server/destination)
# -----------------------------------------------------------------------------

ImageMode = Literal["count", "tot", "toa", "tof", "count_fb"]
ImageFormat = Literal["tiff", "pgm", "png", "jsonimage", "jsonhisto"]
SamplingMode = Literal["skipOnFrame", "skipOnPeriod"]


class OutputChannel(BaseModel):
    """
    Config for one output stream in Destination JSON.

    For file outputs, set Base to a file: URI and include FilePattern.
    For HTTP preview/image endpoints, set Base to http://<host>[:port].
    For TCP streaming, set Base to tcp://[listen@|connect@]<host>:<port>.
    """
    Base: str

    # File-specific
    FilePattern: Optional[str] = None
    SplitStrategy: Optional[Literal["single_file", "frame"]] = None

    # Queue behavior
    QueueSize: Optional[int] = None

    # Image and histogram formatting
    Format: Optional[ImageFormat] = None
    Mode: Optional[ImageMode] = None
    Thresholds: Optional[List[int]] = None

    # Integration and corrections
    IntegrationSize: Optional[int] = None
    IntegrationMode: Optional[Literal["sum", "average", "last"]] = None
    StopMeasurementOnDiskLimit: Optional[bool] = None
    Corrections: Optional[List[Literal["multiply"]]] = None

    # Histogram-only fields
    NumberOfBins: Optional[int] = None
    BinWidth: Optional[float] = None
    Offset: Optional[int] = None


class PreviewConfig(BaseModel):
    Period: float
    SamplingMode: SamplingMode
    ImageChannels: Optional[List[OutputChannel]] = None
    HistogramChannels: Optional[List[OutputChannel]] = None


class DestinationsConfig(BaseModel):
    """
    Root Destination JSON.

    Note: current SERVAL requires the same Mode across all channels.
    This model enforces that when Mode values are present.
    """
    Raw: Optional[List[OutputChannel]] = None
    Image: Optional[List[OutputChannel]] = None
    Preview: Optional[PreviewConfig] = None

    @model_validator(mode="after")
    def enforce_mode_consistency(self) -> "DestinationsConfig":
        modes: List[ImageMode] = []

        for ch_list in [self.Raw or [], self.Image or []]:
            for ch in ch_list:
                if ch.Mode is not None:
                    modes.append(ch.Mode)

        if self.Preview:
            for ch in (self.Preview.ImageChannels or []):
                if ch.Mode is not None:
                    modes.append(ch.Mode)
            for ch in (self.Preview.HistogramChannels or []):
                if ch.Mode is not None:
                    modes.append(ch.Mode)

        if modes and len(set(modes)) > 1:
            raise ValueError("All channels in Destination must use the same Mode")
        return self


# -----------------------------------------------------------------------------
# Measurement configuration (sent to and received from /measurement/config)
# -----------------------------------------------------------------------------

class CorrectionsGapfill(BaseModel):
    Distance: int
    Strategy: Literal["NEIGHBOUR", "SPLIT"]


class Corrections(BaseModel):
    Multiply: Optional[List[float]] = None
    Gapfill: Optional[CorrectionsGapfill] = None


class TimeOfFlight(BaseModel):
    # Example: ["P0","N0"] or ["PN0123","PN0123"] or ["",""] to disable
    TdcReference: List[str]
    Min: float
    Max: float


class MeasurementConfig(BaseModel):
    Corrections: Optional[Corrections] = None
    TimeOfFlight: Optional[TimeOfFlight] = None


# -----------------------------------------------------------------------------
# Optional: light-weight dashboard structures (GET /dashboard)
# -----------------------------------------------------------------------------

class DiskSpaceInfo(BaseModel):
    Message: str
    Path: str
    FreeSpace: int
    WriteSpeed: Optional[float] = None
    LowerLimit: Optional[int] = None
    DiskLimitReached: Optional[bool] = None


class Notification(BaseModel):
    Type: Literal["update", "info", "severe", "error"]
    Domain: Literal["server", "detector", "chip"]
    Message: str
    ReferenceID: Optional[str] = None
    Timestamp: Optional[int] = None


class DashboardServer(BaseModel):
    SoftwareVersion: Optional[str] = None
    SoftwareTimestamp: Optional[str] = None
    SoftwareCommit: Optional[str] = None
    SoftwareBuild: Optional[str] = None
    DiskSpace: Optional[List[DiskSpaceInfo]] = None
    Notifications: Optional[List[Notification]] = None


class DashboardMeasurement(BaseModel):
    StartDateTime: Optional[int] = None  # UNIX timestamp (ms)
    TimeLeft: Optional[float] = None
    ElapsedTime: Optional[float] = None
    FrameCount: Optional[int] = None
    DroppedFrames: Optional[int] = None
    Status: Optional[Literal["DA_IDLE", "DA_PREPARING", "DA_RECORDING", "DA_STOPPING"]] = None
    PixelEventRate: Optional[int] = None
    Tdc1EventRate: Optional[int] = None
    Tdc2EventRate: Optional[int] = None


class DashboardDetector(BaseModel):
    DetectorType: Optional[str] = None  # e.g. "Tpx3"


class Dashboard(BaseModel):
    Server: Optional[DashboardServer] = None
    Measurement: Optional[DashboardMeasurement] = None
    Detector: Optional[DashboardDetector] = None


# -----------------------------------------------------------------------------
# Local client configuration for connecting to a SERVAL instance
# -----------------------------------------------------------------------------

class ServalConfig(BaseModel):
    host: str = Field(default="localhost", description="Hostname or IP address for the Serval server.")
    port: int = Field(default=8080, description="Port number for the Serval server.")
    version: str = Field(default="3.3.0", description="SERVAL software version for reference.")

    # HTTP client settings
    timeout: float = Field(default=10.0, description="HTTP request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of HTTP request retries")
    retry_delay: float = Field(default=1.0, description="Delay between HTTP retries in seconds")
    health_check_interval: float = Field(default=30.0, description="Health check interval in seconds")

    # Optional paths to local resources. These are not sent to SERVAL.
    path_to_serval: Optional[str] = Field(default=None, description="Path to the serval directory.")
    path_to_serval_config_files: Optional[str] = Field(default=None, description="Path to config files directory.")
    destinations_file_name: Optional[str] = Field(default=None, description="Initial destinations JSON file name.")
    detector_config_file_name: Optional[str] = Field(default=None, description="Initial detector config file name.")
    bpc_file_name: Optional[str] = Field(default=None, description="PixelConfig BPC file name.")
    dac_file_name: Optional[str] = Field(default=None, description="DACs file name.")

    # Convenience
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    # Validators
    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {v}")
        return v

    @field_validator("path_to_serval")
    @classmethod
    def validate_serval_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Serval directory does not exist: {v}")
        if not path.is_dir():
            raise ValueError(f"Serval path is not a directory: {v}")
        return v

    @field_validator("path_to_serval_config_files")
    @classmethod
    def validate_config_files_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Serval config files directory does not exist: {v}")
        if not path.is_dir():
            raise ValueError(f"Serval config files path is not a directory: {v}")
        return v

    @model_validator(mode="after")
    def validate_config_files_exist(self):
        # Only check if a config dir is set
        if self.path_to_serval_config_files is None:
            return self

        config_dir = Path(self.path_to_serval_config_files)

        def must_exist(name: Optional[str], label: str):
            if name:
                f = config_dir / name
                if not f.exists():
                    raise ValueError(f"{label} does not exist: {f}")

        must_exist(self.destinations_file_name, "Destinations file")
        must_exist(self.detector_config_file_name, "Detector config file")
        must_exist(self.bpc_file_name, "BPC file")
        must_exist(self.dac_file_name, "DAC file")

        return self

    model_config = dict(validate_assignment=True)
