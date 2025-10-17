# src/hermes/acquisition/models/detector.py
"""
Detector-related configuration and state models for HERMES (Serval integration).

Manual references:
- Serval v3.3 (2023): §4.5 /detector requests; Info (§4.5.4), Health (§4.5.5),
  Layout (§4.5.6, Table 4.8), Config (§4.5.7), DACs (§4.5.8).  (Fields & examples)  [v3.3]  
- Serval v1.22 (2021; Serval 2.1.5): Same /detector tree and parameter shapes,
  so these models are backward-compatible.  [v1.22]  :contentReference[oaicite:5]{index=5}

Versioning notes:
- Structures below are unchanged between 2.1.5 and 3.3; any minor additions are kept optional.
- Use `model_dump(by_alias=True)` to emit exact Serval keys.
- Models remain PURE (validation only): no I/O, logging, or service calls.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional

from pydantic import Field, field_validator

# explicit imports (all __init__.py files are blank)
from .common import HermesBaseModel, HermesImmutableModel, Seconds


# =============================================================================
# Enums (from Serval docs)
# - TriggerMode list appears identically in v1.22 Table 4.9 and v3.3 §4.5.7
# - DetectorOrientation and ChipReadoutOrientation from v3.3 Layout Table 4.8
#   (same semantics apply to v1.22).  
# =============================================================================

class ChainMode(str, Enum):
    NONE = "NONE"
    LEADER = "LEADER"
    FOLLOWER = "FOLLOWER"


class ServalTriggerMode(str, Enum):
    PEXSTART_NEXSTOP = "PEXSTART_NEXSTOP"
    NEXSTART_PEXSTOP = "NEXSTART_PEXSTOP"
    PEXSTART_TIMERSTOP = "PEXSTART_TIMERSTOP"
    NEXSTART_TIMERSTOP = "NEXSTART_TIMERSTOP"
    AUTOTRIGSTART_TIMERSTOP = "AUTOTRIGSTART_TIMERSTOP"
    CONTINUOUS = "CONTINUOUS"
    SOFTWARESTART_TIMERSTOP = "SOFTWARESTART_TIMERSTOP"
    SOFTWARESTART_SOFTWARESTOP = "SOFTWARESTART_SOFTWARESTOP"


class DetectorOrientation(str, Enum):
    UP = "UP"
    RIGHT = "RIGHT"
    DOWN = "DOWN"
    LEFT = "LEFT"
    UP_MIRRORED = "UP_MIRRORED"
    RIGHT_MIRRORED = "RIGHT_MIRRORED"
    DOWN_MIRRORED = "DOWN_MIRRORED"
    LEFT_MIRRORED = "LEFT_MIRRORED"


class ChipReadoutOrientation(str, Enum):
    # 8 possible readout orders (rotation/mirroring combos) — v3.3 Table 4.8. :contentReference[oaicite:7]{index=7}
    LtRBtT = "LtRBtT"
    RtLBtT = "RtLBtT"
    LtRTtB = "LtRTtB"
    RtLTtB = "RtLTtB"
    BtTLtR = "BtTLtR"
    TtBLtR = "TtBLtR"
    BtTRtL = "BtTRtL"
    TtBRtL = "TtBRtL"


# =============================================================================
# /detector/config — DetectorConfig
# v3.3 §4.5.7 (fields, JSON example + bounds) — same structure in v1.22.  
# =============================================================================

class DetectorConfig(HermesImmutableModel):
    """
    Detector configuration for PUT/GET /detector/config.

    Fields & ranges mirror v3.3 Table under §4.5.7, which is compatible with v1.22.
    """
    log_level: int = Field(1, alias="LogLevel", ge=0, le=2, description="Logging level [0..2].")
    fan1_pwm: int = Field(100, alias="Fan1PWM", ge=0, le=100, description="Fan1 PWM duty cycle [%].")
    fan2_pwm: int = Field(100, alias="Fan2PWM", ge=0, le=100, description="Fan2 PWM duty cycle [%].")

    bias_voltage: float = Field(..., alias="BiasVoltage", ge=0.0, le=140.0, description="Bias voltage [V].")
    bias_enabled: bool = Field(True, alias="BiasEnabled", description="Enable detector bias.")
    polarity: str = Field("Positive", alias="Polarity", pattern="^(Positive|Negative)$", description="Pixel polarity.")
    periph_clk80: bool = Field(False, alias="PeriphClk80", description="Enable 80 MHz readout (single-chip TPX3).")
    chain_mode: ChainMode = Field(ChainMode.NONE, alias="ChainMode", description="LEADER/FOLLOWER/NONE (sync mode).")

    trigger_in: int = Field(1, alias="TriggerIn", ge=1, le=6, description="HDMI channel number for trigger input [1..6].")
    trigger_out: int = Field(1, alias="TriggerOut", ge=1, le=6, description="HDMI channel number for trigger output [1..6].")

    trigger_period: Seconds = Field(0.016666666666666666, alias="TriggerPeriod", ge=0.0, le=50.0,
                                   description="Trigger period [s].")
    exposure_time: Seconds = Field(0.0002, alias="ExposureTime", ge=0.0, le=10.0, description="Exposure time [s].")
    trigger_delay: float = Field(0.0, alias="TriggerDelay", ge=0.0, le=1.0, description="Trigger delay [s].")
    trigger_mode: ServalTriggerMode = Field(ServalTriggerMode.AUTOTRIGSTART_TIMERSTOP,
                                            alias="TriggerMode", description="Shutter/trigger mode.")

    n_triggers: int = Field(100, alias="nTriggers", ge=0, description="Number of triggers (0..max).")

    # Tdc: exactly two entries (TDC1, TDC2). Examples: "", "P0", "N0", "PN0123".  (v1.22/v3.3)  :contentReference[oaicite:9]{index=9}
    tdc: List[str] = Field(default_factory=lambda: ["PN0123", "PN0123"],
                           alias="Tdc", min_length=2, max_length=2,
                           description="TDC recording spec for [TDC1, TDC2]; '' disables.")

    global_timestamp_interval: float = Field(10.0, alias="GlobalTimestampInterval",
                                             description="<=0 disables; else [0.001..1e7] s.")
    external_reference_clock: bool = Field(False, alias="ExternalReferenceClock",
                                           description="Use external reference clock (special setup).")

    @field_validator("global_timestamp_interval")
    @classmethod
    def _validate_gti(cls, v: float) -> float:
        if v <= 0:
            return v
        if not (0.001 <= v <= 1.0e7):
            raise ValueError("GlobalTimestampInterval must be <=0 or within [0.001, 1e7] seconds.")
        return v

    @field_validator("tdc")
    @classmethod
    def _validate_tdc(cls, v: List[str]) -> List[str]:
        # Accept "", "P", "N", "PN" optionally followed by digits 0..3 (chip numbers).  (examples in manual)
        import re
        pat = re.compile(r"^(|P|N|PN)[0-3]{0,4}$")
        for s in v:
            if not isinstance(s, str) or not pat.match(s):
                raise ValueError("Each TDC entry must be '', 'P', 'N', 'PN' plus optional digits 0..3 (e.g., 'P0', 'PN0123').")
        return v


# =============================================================================
# /detector/info — Info
# v3.3 §4.5.4 JSON example & fields (same presence in v1.22).  
# =============================================================================

class ChipInfo(HermesBaseModel):
    index: int = Field(alias="Index")
    id: int = Field(alias="Id")
    name: str = Field(alias="Name")


class BoardInfo(HermesBaseModel):
    chipboard_id: str = Field(alias="ChipboardId")
    ip_address: str = Field(alias="IpAddress")
    firmware_version: str = Field(alias="FirmwareVersion")
    chips: List[ChipInfo] = Field(alias="Chips")


class Info(HermesBaseModel):
    iface_name: str = Field(alias="IfaceName")
    sw_version: str = Field(alias="SW_version")
    fw_version: str = Field(alias="FW_version")

    pix_count: int = Field(alias="PixCount")
    row_len: int = Field(alias="RowLen")
    number_of_chips: int = Field(alias="NumberOfChips")
    number_of_rows: int = Field(alias="NumberOfRows")
    mpx_type: int = Field(alias="MpxType")

    boards: List[BoardInfo] = Field(alias="Boards")

    supp_acq_modes: int = Field(alias="SuppAcqModes")
    clock_readout: float = Field(alias="ClockReadout")
    max_pulse_count: int = Field(alias="MaxPulseCount")
    max_pulse_height: float = Field(alias="MaxPulseHeight")
    max_pulse_period: float = Field(alias="MaxPulsePeriod")
    timer_max_val: float = Field(alias="TimerMaxVal")
    timer_min_val: float = Field(alias="TimerMinVal")
    timer_step: float = Field(alias="TimerStep")
    clock_timepix: float = Field(alias="ClockTimepix")


# =============================================================================
# /detector/health — Health
# v3.3 §4.5.5 (table & example).  (v1.22 contains same concept/fields)  :contentReference[oaicite:11]{index=11}
# =============================================================================

class Health(HermesBaseModel):
    local_temperature: float = Field(alias="LocalTemperature", description="Acquisition board temperature [°C].")
    fpga_temperature: float = Field(alias="FPGATemperature", description="FPGA temperature [°C].")
    chip_temperatures: List[int] = Field(alias="ChipTemperatures", description="Per-chip temperatures [°C].")

    fan1_speed: int = Field(alias="Fan1Speed", description="Fan 1 speed [rpm].")
    fan2_speed: int = Field(alias="Fan2Speed", description="Fan 2 speed [rpm].")

    avdd: List[float] = Field(alias="AVDD", description="Analog supply readings [V, A, W].")
    vdd: List[float] = Field(alias="VDD", description="Supply readings [V, A, W].")

    bias_voltage: float = Field(alias="BiasVoltage", description="Bias voltage [V].")
    humidity: Optional[int] = Field(default=None, alias="Humidity", description="Board humidity [%].")


# =============================================================================
# /detector/layout — Layout (canvas + chip placement/orientation)
# v3.3 §4.5.6 Table 4.8 (unchanged semantics vs v1.22).  
# =============================================================================

class LayoutChip(HermesBaseModel):
    chip: int = Field(alias="Chip")
    x: int = Field(alias="X", ge=0)
    y: int = Field(alias="Y", ge=0)
    orientation: ChipReadoutOrientation = Field(alias="Orientation")


class LayoutCanvas(HermesBaseModel):
    width: int = Field(alias="Width", ge=1)
    height: int = Field(alias="Height", ge=1)
    chips: List[LayoutChip] = Field(alias="Chips")


class Layout(HermesBaseModel):
    detector_orientation: DetectorOrientation = Field(alias="DetectorOrientation")
    original: LayoutCanvas = Field(alias="Original")
    rotated: LayoutCanvas = Field(alias="Rotated")


# =============================================================================
# /detector/chips/<n>/dacs — DACs
# v3.3 §4.5.8 (list of DAC parameter names) — same in v1.22.  
# =============================================================================

class Dacs(HermesBaseModel):
    # Field names keep Serval capitalization via alias, to round-trip 1:1.
    ibias_preamp_on: int = Field(alias="Ibias_Preamp_ON")
    ibias_preamp_off: int = Field(alias="Ibias_Preamp_OFF")
    vpreamp_ncas: int = Field(alias="VPreamp_NCAS")
    ibias_ikrum: int = Field(alias="Ibias_Ikrum")
    vfbk: int = Field(alias="Vfbk")
    vthreshold_fine: int = Field(alias="Vthreshold_fine")
    vthreshold_coarse: int = Field(alias="Vthreshold_coarse")
    ibias_discs1_on: int = Field(alias="Ibias_DiscS1_ON")
    ibias_discs1_off: int = Field(alias="Ibias_DiscS1_OFF")
    ibias_discs2_on: int = Field(alias="Ibias_DiscS2_ON")
    ibias_discs2_off: int = Field(alias="Ibias_DiscS2_OFF")
    ibias_pixeldac: int = Field(alias="Ibias_PixelDAC")
    ibias_tpbuff_in: int = Field(alias="Ibias_TPbufferIn")
    ibias_tpbuff_out: int = Field(alias="Ibias_TPbufferOut")
    vtp_coarse: int = Field(alias="VTP_coarse")
    vtp_fine: int = Field(alias="VTP_fine")
    ibias_cp_pll: int = Field(alias="Ibias_CP_PLL")
    pll_vcntrl: int = Field(alias="PLL_Vcntrl")
