from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from hermes.state.models.payloads import ExternalPayloadRef
from hermes.state.models.shared_models import JsonObject, StrictBaseModel, utc_now

SnapshotPayload = JsonObject | ExternalPayloadRef
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
    raw: SnapshotPayload | None = None


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
    raw: SnapshotPayload | None = None


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
    raw: SnapshotPayload | None = None


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
