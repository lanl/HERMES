from __future__ import annotations

import pytest
from pydantic import ValidationError

from hermes.state.models.acquisition.serval import (
    ServalAcquisitionResult,
    ServalEnvironment,
)
from hermes.state.models.detector import (
    DetectorConfiguration,
    DetectorHealth,
    DetectorInfo,
    DetectorLayout,
    DetectorSnapshot,
)


def test_detector_snapshot_rejects_serval_dashboard() -> None:
    with pytest.raises(ValidationError, match="dashboard"):
        DetectorSnapshot(
            info=DetectorInfo(iface_name="Spidr"),
            dashboard={"Measurement": {"Status": "DA_IDLE"}},
        )


def test_serval_models_own_dashboard_snapshots() -> None:
    dashboard = {
        "Server": {"SoftwareVersion": "3.3.0"},
        "Measurement": {"Status": "DA_IDLE", "FrameCount": 0},
        "Detector": {"DetectorType": "Tpx3"},
    }

    environment = ServalEnvironment(
        serval_url="http://127.0.0.1:8080",
        version="3.3.0",
        dashboard=dashboard,
    )
    result = ServalAcquisitionResult(status="completed", final_dashboard=dashboard)

    assert environment.dashboard is not None
    assert environment.dashboard.server.software_version == "3.3.0"
    assert result.final_dashboard is not None
    assert result.final_dashboard.measurement is not None
    assert result.final_dashboard.measurement.status == "DA_IDLE"


def test_detector_info_validates_manual_alias_payload() -> None:
    info = DetectorInfo.model_validate(
        {
            "IfaceName": "Spidr",
            "SW_version": "21052719",
            "FW_version": "18052510",
            "PixCount": 262144,
            "RowLen": 2,
            "NumberOfChips": 4,
            "NumberOfRows": 512,
            "MpxType": 6,
            "Boards": [
                {
                    "ChipboardId": "41000039",
                    "IpAddress": "127.0.0.10",
                    "FirmwareVersion": "18052510",
                    "Chips": [
                        {"Index": 0, "Id": 680, "Name": "W0002_H10"},
                        {"Index": 1, "Id": 681, "Name": "W0002_I10"},
                    ],
                }
            ],
            "SuppAcqModes": 63,
            "ClockReadout": 125.0,
            "MaxPulseCount": 2147483647,
            "MaxPulseHeight": 1.0,
            "MaxPulsePeriod": 34.35973836,
            "TimerMaxVal": 34.35973836,
            "TimerMinVal": 8.0e-9,
            "TimerStep": 8.0e-9,
            "ClockTimepix": 125.0,
        }
    )

    assert info.iface_name == "Spidr"
    assert info.number_of_chips == 4
    assert info.boards[0].chips[1].name == "W0002_I10"

    dumped = info.model_dump(mode="json", by_alias=True)
    assert dumped["NumberOfChips"] == 4
    assert dumped["Boards"][0]["Chips"][0]["Id"] == 680


def test_detector_health_validates_manual_alias_payload() -> None:
    health = DetectorHealth.model_validate(
        {
            "LocalTemperature": 30.713,
            "FPGATemperature": 50.57,
            "ChipTemperatures": [52, 47, 53, 25],
            "Fan1Speed": 1200,
            "Fan2Speed": 1200,
            "AVDD": [1.44, 1.796, 2.586],
            "VDD": [1.444, 0.708, 1.022],
            "BiasVoltage": 49.951171875,
            "Humidity": 20,
        }
    )

    assert health.local_temperature_c == 30.713
    assert health.chip_temperatures_c == [52, 47, 53, 25]
    assert health.avdd == [1.44, 1.796, 2.586]

    dumped = health.model_dump(mode="json", by_alias=True)
    assert dumped["BiasVoltage"] == 49.951171875


def test_detector_health_rejects_invalid_supply_reading_shape() -> None:
    with pytest.raises(ValidationError, match="AVDD"):
        DetectorHealth.model_validate({"AVDD": [1.44, 1.796]})


def test_detector_layout_validates_manual_alias_payload() -> None:
    layout = DetectorLayout.model_validate(
        {
            "DetectorOrientation": "UP",
            "Original": {
                "Width": 512,
                "Height": 512,
                "Chips": [
                    {"Chip": 0, "X": 256, "Y": 0, "Orientation": "RtLBtT"},
                    {"Chip": 1, "X": 0, "Y": 0, "Orientation": "RtLBtT"},
                ],
            },
            "Rotated": {
                "Width": 512,
                "Height": 512,
                "Chips": [
                    {"Chip": 0, "X": 256, "Y": 0, "Orientation": "RtLBtT"},
                    {"Chip": 1, "X": 0, "Y": 0, "Orientation": "RtLBtT"},
                ],
            },
        }
    )

    assert layout.detector_orientation == "UP"
    assert layout.original is not None
    assert layout.original.width == 512
    assert layout.rotated is not None
    assert layout.rotated.chips[0].orientation == "RtLBtT"

    dumped = layout.model_dump(mode="json", by_alias=True)
    assert dumped["Original"]["Chips"][0]["Chip"] == 0


def test_detector_layout_accepts_pythonic_field_names() -> None:
    layout = DetectorLayout.model_validate(
        {
            "detector_orientation": "RIGHT_MIRRORED",
            "original": {
                "width": 256,
                "height": 256,
                "chips": [{"chip": 0, "x": 0, "y": 0, "orientation": "LtRBtT"}],
            },
        }
    )

    assert layout.detector_orientation == "RIGHT_MIRRORED"
    assert layout.original is not None
    assert layout.original.chips[0].chip == 0


def test_detector_layout_rejects_invalid_orientation() -> None:
    with pytest.raises(ValidationError, match="DetectorOrientation"):
        DetectorLayout.model_validate({"DetectorOrientation": "UPSIDE_DOWN"})


def test_detector_configuration_validates_manual_alias_payload() -> None:
    config = DetectorConfiguration.model_validate(
        {
            "LogLevel": 1,
            "Fan1PWM": 100,
            "Fan2PWM": 100,
            "BiasVoltage": 50,
            "BiasEnabled": True,
            "Polarity": "Positive",
            "PeriphClk80": False,
            "ChainMode": "NONE",
            "TriggerIn": 0,
            "TriggerOut": 0,
            "TriggerPeriod": 0.016666666666666666,
            "ExposureTime": 0.0002,
            "TriggerDelay": 0.0,
            "TriggerMode": "AUTOTRIGSTART_TIMERSTOP",
            "nTriggers": 100,
            "Tdc": ["PN0123", "PN0123"],
            "GlobalTimestampInterval": 10.0,
            "ExternalReferenceClock": False,
        }
    )

    assert config.bias_voltage_v == 50
    assert config.trigger_mode == "AUTOTRIGSTART_TIMERSTOP"
    assert config.n_triggers == 100
    assert config.tdc == ["PN0123", "PN0123"]

    dumped = config.model_dump(mode="json", by_alias=True)
    assert dumped["BiasVoltage"] == 50
    assert dumped["TriggerMode"] == "AUTOTRIGSTART_TIMERSTOP"
    assert dumped["nTriggers"] == 100


def test_detector_configuration_accepts_pythonic_field_names() -> None:
    config = DetectorConfiguration.model_validate(
        {
            "trigger_mode": "PEXSTART_TIMERSTOP",
            "trigger_in": 1,
            "trigger_out": 2,
            "exposure_time_s": 0.5,
            "tdc": ["P0", "N0"],
            "global_timestamp_interval_s": 0,
            "pixel_config": "binary-pixel-config-reference",
            "dacs": [{"Vthreshold_fine": 216}],
        }
    )

    assert config.trigger_mode == "PEXSTART_TIMERSTOP"
    assert config.trigger_in == 1
    assert config.tdc == ["P0", "N0"]
    assert config.global_timestamp_interval_s == 0
    assert config.dacs == [{"Vthreshold_fine": 216}]


def test_detector_configuration_rejects_invalid_trigger_mode() -> None:
    with pytest.raises(ValidationError, match="TriggerMode"):
        DetectorConfiguration.model_validate({"TriggerMode": "AUTO"})


def test_detector_configuration_rejects_invalid_tdc_shape() -> None:
    with pytest.raises(ValidationError, match="Tdc"):
        DetectorConfiguration.model_validate({"Tdc": ["P0"]})


def test_detector_configuration_rejects_invalid_tdc_channel() -> None:
    with pytest.raises(ValidationError, match="Tdc"):
        DetectorConfiguration.model_validate({"Tdc": ["P0", "NP0"]})


def test_detector_configuration_rejects_small_global_timestamp_interval() -> None:
    with pytest.raises(ValidationError, match="GlobalTimestampInterval"):
        DetectorConfiguration.model_validate({"GlobalTimestampInterval": 0.0005})
