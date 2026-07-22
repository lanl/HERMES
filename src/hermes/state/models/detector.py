from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator

from hermes.state.models.shared_models import StrictBaseModel, utc_now

SupplyReading = Annotated[list[float], Field(min_length=3, max_length=3)]
DetectorLayoutOrientation = Literal[
    "UP",
    "RIGHT",
    "DOWN",
    "LEFT",
    "UP_MIRRORED",
    "RIGHT_MIRRORED",
    "DOWN_MIRRORED",
    "LEFT_MIRRORED",
]
DetectorChipOrientation = Literal[
    "LtRBtT",
    "RtLBtT",
    "LtRTtB",
    "RtLTtB",
    "BtTLtR",
    "TtBLtR",
    "BtTRtL",
    "TtBRtL",
]
DetectorLogLevel = Literal[0, 1, 2]
DetectorPolarity = Literal["Negative", "Positive"]
DetectorChainMode = Literal["NONE", "LEADER", "FOLLOWER"]
DetectorTriggerMode = Literal[
    "PEXSTART_NEXSTOP",
    "NEXSTART_PEXSTOP",
    "PEXSTART_TIMERSTOP",
    "NEXSTART_TIMERSTOP",
    "AUTOTRIGSTART_TIMERSTOP",
    "CONTINUOUS",
    "SOFTWARESTART_TIMERSTOP",
    "SOFTWARESTART_SOFTWARESTOP",
]
DetectorTdcChannel = Annotated[str, Field(pattern=r"^(?:|(?:P|N|PN)[0-3]{1,4})$")]
DetectorTdcConfig = Annotated[
    list[DetectorTdcChannel],
    Field(min_length=2, max_length=2),
]


class DetectorApiModel(StrictBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class DetectorInfoChip(DetectorApiModel):
    index: int = Field(ge=0, alias="Index")
    id: int = Field(ge=0, alias="Id")
    name: str = Field(min_length=1, alias="Name")


class DetectorInfoBoard(DetectorApiModel):
    chipboard_id: str | None = Field(default=None, alias="ChipboardId")
    ip_address: str | None = Field(default=None, alias="IpAddress")
    firmware_version: str | None = Field(default=None, alias="FirmwareVersion")
    chips: list[DetectorInfoChip] = Field(default_factory=list, alias="Chips")


class DetectorInfo(DetectorApiModel):
    iface_name: str | None = Field(default=None, alias="IfaceName")
    software_version: str | None = Field(default=None, alias="SW_version")
    firmware_version: str | None = Field(default=None, alias="FW_version")
    pixel_count: int | None = Field(default=None, ge=0, alias="PixCount")
    row_length: int | None = Field(default=None, ge=0, alias="RowLen")
    number_of_chips: int | None = Field(default=None, ge=0, alias="NumberOfChips")
    number_of_rows: int | None = Field(default=None, ge=0, alias="NumberOfRows")
    medipix_type: int | None = Field(default=None, ge=0, alias="MpxType")
    boards: list[DetectorInfoBoard] = Field(default_factory=list, alias="Boards")
    supported_acquisition_modes: int | None = Field(
        default=None,
        ge=0,
        alias="SuppAcqModes",
    )
    clock_readout_mhz: float | None = Field(default=None, ge=0, alias="ClockReadout")
    max_pulse_count: int | None = Field(default=None, ge=0, alias="MaxPulseCount")
    max_pulse_height: float | None = Field(default=None, ge=0, alias="MaxPulseHeight")
    max_pulse_period_s: float | None = Field(
        default=None,
        ge=0,
        alias="MaxPulsePeriod",
    )
    timer_max_s: float | None = Field(default=None, ge=0, alias="TimerMaxVal")
    timer_min_s: float | None = Field(default=None, ge=0, alias="TimerMinVal")
    timer_step_s: float | None = Field(default=None, ge=0, alias="TimerStep")
    clock_timepix_mhz: float | None = Field(default=None, ge=0, alias="ClockTimepix")


class DetectorHealth(DetectorApiModel):
    local_temperature_c: float | None = Field(default=None, alias="LocalTemperature")
    fpga_temperature_c: float | None = Field(default=None, alias="FPGATemperature")
    chip_temperatures_c: list[int] = Field(
        default_factory=list,
        alias="ChipTemperatures",
    )
    fan1_speed_rpm: int | None = Field(default=None, ge=0, alias="Fan1Speed")
    fan2_speed_rpm: int | None = Field(default=None, ge=0, alias="Fan2Speed")
    avdd: SupplyReading | None = Field(default=None, alias="AVDD")
    vdd: SupplyReading | None = Field(default=None, alias="VDD")
    bias_voltage_v: float | None = Field(default=None, ge=0, alias="BiasVoltage")
    humidity_percent: int | None = Field(default=None, ge=0, alias="Humidity")


class DetectorLayoutChip(DetectorApiModel):
    chip: int = Field(ge=0, alias="Chip")
    x: int = Field(ge=0, alias="X")
    y: int = Field(ge=0, alias="Y")
    orientation: DetectorChipOrientation = Field(alias="Orientation")


class DetectorLayoutCanvas(DetectorApiModel):
    width: int = Field(gt=0, alias="Width")
    height: int = Field(gt=0, alias="Height")
    chips: list[DetectorLayoutChip] = Field(default_factory=list, alias="Chips")


class DetectorLayout(DetectorApiModel):
    detector_orientation: DetectorLayoutOrientation | None = Field(
        default=None,
        alias="DetectorOrientation",
    )
    original: DetectorLayoutCanvas | None = Field(default=None, alias="Original")
    rotated: DetectorLayoutCanvas | None = Field(default=None, alias="Rotated")


class DetectorConfiguration(DetectorApiModel):
    log_level: DetectorLogLevel | None = Field(default=None, alias="LogLevel")
    fan1_pwm: int | None = Field(default=None, ge=0, le=100, alias="Fan1PWM")
    fan2_pwm: int | None = Field(default=None, ge=0, le=100, alias="Fan2PWM")
    bias_voltage_v: float | None = Field(
        default=None,
        ge=0,
        le=140,
        alias="BiasVoltage",
    )
    bias_enabled: bool | None = Field(default=None, alias="BiasEnabled")
    polarity: DetectorPolarity | None = Field(default=None, alias="Polarity")
    periph_clk_80: bool | None = Field(default=None, alias="PeriphClk80")
    chain_mode: DetectorChainMode | None = Field(default=None, alias="ChainMode")
    trigger_in: int | None = Field(default=None, ge=0, le=6, alias="TriggerIn")
    trigger_out: int | None = Field(default=None, ge=0, le=6, alias="TriggerOut")
    trigger_period_s: float | None = Field(
        default=None,
        ge=0,
        le=50,
        alias="TriggerPeriod",
    )
    exposure_time_s: float | None = Field(
        default=None,
        ge=0,
        le=10,
        alias="ExposureTime",
    )
    trigger_delay_s: float | None = Field(
        default=None,
        ge=0,
        le=1,
        alias="TriggerDelay",
    )
    trigger_mode: DetectorTriggerMode | None = Field(default=None, alias="TriggerMode")
    n_triggers: int | None = Field(default=None, ge=0, alias="nTriggers")
    tdc: DetectorTdcConfig | None = Field(default=None, alias="Tdc")
    global_timestamp_interval_s: float | None = Field(
        default=None,
        le=10_000_000,
        alias="GlobalTimestampInterval",
    )
    external_reference_clock: bool | None = Field(
        default=None,
        alias="ExternalReferenceClock",
    )
    pixel_config: str | None = None
    dacs: list[dict[str, int]] | None = None

    @field_validator("global_timestamp_interval_s")
    @classmethod
    def validate_global_timestamp_interval(cls, value: float | None) -> float | None:
        if value is None or value <= 0 or value >= 0.001:
            return value
        msg = "GlobalTimestampInterval must be <= 0 or >= 0.001 seconds"
        raise ValueError(msg)


class DetectorSnapshot(StrictBaseModel):
    """Detector-specific state from `/detector/*` endpoints."""

    captured_at: datetime = Field(default_factory=utc_now)
    info: DetectorInfo | None = None
    health: DetectorHealth | None = None
    layout: DetectorLayout | None = None
    configuration: DetectorConfiguration | None = None
