"""
tpx3Cam.py

Pydantic models for TPX3 hardware-side communication that mirror SERVAL /detector endpoints.
Shapes and field names match the SERVAL JSON so you can round-trip GET/PUT payloads cleanly.
"""

from __future__ import annotations

from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Connection to readout (kept simple; not part of SERVAL JSON)
# ---------------------------------------------------------------------------

class SPIDRConfig(BaseModel):
    host: str = Field(default="localhost", description="SPIDR host address")
    port: int = Field(default=8080, description="SPIDR port number")
    timeout: float = Field(default=30.0, description="Connection timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum connection retries")

    model_config = dict(validate_assignment=True)


# ---------------------------------------------------------------------------
# Read-only payloads returned by SERVAL
# ---------------------------------------------------------------------------

class DetectorBoard(BaseModel):
    ChipboardId: str
    IpAddress: str
    FirmwareVersion: str
    # SERVAL lists chip dicts as {Index:int, Id:int, Name:str}
    Chips: List[dict]


class DetectorInfo(BaseModel):
    IfaceName: str
    SW_version: str
    FW_version: str
    PixCount: int
    RowLen: int
    NumberOfChips: int
    NumberOfRows: int
    MpxType: int
    Boards: List[DetectorBoard]
    SuppAcqModes: int
    ClockReadout: float
    MaxPulseCount: int
    MaxPulseHeight: float
    MaxPulsePeriod: float
    TimerMaxVal: float
    TimerMinVal: float
    TimerStep: float
    ClockTimepix: float


class ChipCanvas(BaseModel):
    Chip: int
    X: int
    Y: int
    Orientation: Literal[
        "LtRBtT", "RtLBtT", "LtRTtB", "RtLTtB",
        "BtTLtR", "TtBLtR", "BtTRtL", "TtBRtL"
    ]


class Canvas(BaseModel):
    Width: int
    Height: int
    Chips: List[ChipCanvas]


class DetectorLayout(BaseModel):
    DetectorOrientation: Literal[
        "UP", "RIGHT", "DOWN", "LEFT",
        "UP_MIRRORED", "RIGHT_MIRRORED", "DOWN_MIRRORED", "LEFT_MIRRORED"
    ]
    Original: Canvas
    Rotated: Canvas


class DetectorHealth(BaseModel):
    LocalTemperature: float
    FPGATemperature: float
    ChipTemperatures: List[int]
    Fan1Speed: int
    Fan2Speed: int
    AVDD: List[float]
    VDD: List[float]
    BiasVoltage: float
    Humidity: int


# ---------------------------------------------------------------------------
# DACs block (per chip)
# ---------------------------------------------------------------------------

class DACs(BaseModel):
    Ibias_Preamp_ON: int
    Ibias_Preamp_OFF: int
    VPreamp_NCAS: int
    Ibias_Ikrum: int
    Vfbk: int
    Vthreshold_fine: int
    Vthreshold_coarse: int
    Ibias_DiscS1_ON: int
    Ibias_DiscS1_OFF: int
    Ibias_DiscS2_ON: int
    Ibias_DiscS2_OFF: int
    Ibias_PixelDAC: int
    Ibias_TPbufferIn: int
    Ibias_TPbufferOut: int
    # Manual shows VTP_* in JSON block; some docs use Vtp_* casing.
    VTP_coarse: Optional[int] = Field(default=None, alias="VTP_coarse")
    VTP_fine: Optional[int] = Field(default=None, alias="VTP_fine")
    Ibias_CP_PLL: int
    PLL_Vcntrl: int

    @model_validator(mode="before")
    @classmethod
    def _normalize_casing(cls, v):
        # Accept Vtp_* keys too
        if isinstance(v, dict):
            if "Vtp_coarse" in v and "VTP_coarse" not in v:
                v["VTP_coarse"] = v.pop("Vtp_coarse")
            if "Vtp_fine" in v and "VTP_fine" not in v:
                v["VTP_fine"] = v.pop("Vtp_fine")
        return v

    model_config = dict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Detector configuration (read/write)
# ---------------------------------------------------------------------------

TriggerMode = Literal[
    "PEXSTART_NEXSTOP",
    "NEXSTART_PEXSTOP",
    "PEXSTART_TIMERSTOP",
    "NEXSTART_TIMERSTOP",
    "AUTOTRIGSTART_TIMERSTOP",
    "CONTINUOUS",
    "SOFTWARESTART_TIMERSTOP",
    "SOFTWARESTART_SOFTWARESTOP",
]

Polarity = Literal["Positive", "Negative"]
ChainMode = Literal["NONE", "LEADER", "FOLLOWER"]


class DetectorConfig(BaseModel):
    # Logging and fans
    LogLevel: int = Field(default=1, ge=0, le=5)
    Fan1PWM: int = Field(default=70, ge=0, le=100)
    Fan2PWM: int = Field(default=100, ge=0, le=100)

    # Bias
    BiasVoltage: float = Field(default=40.0, ge=0, le=140)
    BiasEnabled: bool = Field(default=True)
    Polarity: Polarity = Field(default="Positive")

    # Clock and sync
    PeriphClk80: bool = Field(default=True, description="80 MHz readout for single-chip TPX3")
    ChainMode: ChainMode = Field(default="NONE")

    # Trigger IO
    TriggerIn: int = Field(default=0, ge=0, le=6)
    TriggerOut: int = Field(default=0, ge=0, le=6)

    # Timing
    TriggerPeriod: float = Field(default=0.15, gt=0, le=50.0)
    ExposureTime: float = Field(default=0.10, gt=0, le=10.0)
    TriggerDelay: float = Field(default=0.0, ge=0, le=1.0)
    TriggerMode: TriggerMode = Field(default="AUTOTRIGSTART_TIMERSTOP")
    nTriggers: int = Field(default=11, ge=0)

    # TDC and timestamps
    Tdc: List[str] = Field(default_factory=lambda: ["P0", ""], description="e.g. ['P0','N0'] or ['PN0123','PN0123']")
    GlobalTimestampInterval: float = Field(default=0.0)
    ExternalReferenceClock: bool = Field(default=False)

    @model_validator(mode="after")
    def _check_exposure_vs_period(self) -> "DetectorConfig":
        if self.TriggerMode == "AUTOTRIGSTART_TIMERSTOP":
            deadtime = 0.001 if self.PeriphClk80 else 0.002
            if not (self.TriggerPeriod - self.ExposureTime > deadtime):
                raise ValueError(
                    f"TriggerPeriod - ExposureTime must be > {deadtime} s in AUTOTRIGSTART_TIMERSTOP"
                )
        return self

    @field_validator("TriggerPeriod", "ExposureTime")
    @classmethod
    def _nonnegative_times(cls, v):
        return v


# Per-chip container when reading /detector/chips/<n>
class ChipConfig(BaseModel):
    # SERVAL uses keys DACs, PixelConfig, adjust
    DACs: Optional[DACs] = None
    PixelConfig: Optional[str] = None  # JSON string if requested as JSON
    adjust: Optional[Any] = None


# Full /detector tree when reading GET /detector
class DetectorTop(BaseModel):
    info: Optional[DetectorInfo] = None
    health: Optional[DetectorHealth] = None
    layout: Optional[DetectorLayout] = None
    config: Optional[DetectorConfig] = None
    chips: Optional[List[ChipConfig]] = None


# ---------------------------------------------------------------------------
# Convenience wrapper that mirrors your original structure
# ---------------------------------------------------------------------------

class HardwareConfig(BaseModel):
    spidr: SPIDRConfig = Field(default_factory=SPIDRConfig)
    detector: DetectorConfig = Field(default_factory=DetectorConfig)

    # High-level choices for client logic (not sent to SERVAL directly)
    acquisition_mode: Literal["count", "tot", "toa", "tof", "count_fb"] = "tot"
    trigger_mode: Literal["internal", "external", "software"] = "internal"

    advanced_settings: Optional[dict] = None

    model_config = dict(validate_assignment=True)
