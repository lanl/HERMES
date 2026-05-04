from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes.state.models.acquisition.serval import (
    DestinationConfiguration,
    ServalAcquisitionState,
    ServalDashboard,
)


def test_serval_dashboard_validates_manual_alias_payload() -> None:
    dashboard = ServalDashboard.model_validate(
        {
            "Server": {
                "SoftwareVersion": "3.3.0",
                "SoftwareTimestamp": "2023/10/23 14:04",
                "SoftwareCommit": "60be309",
                "SoftwareBuild": "311",
                "DiskSpace": [
                    {
                        "Message": "Free Space: 670.8 GB.",
                        "Path": "/data/raw",
                        "FreeSpace": 670758268928,
                        "WriteSpeed": 1.050576e9,
                        "LowerLimit": 100000000,
                        "DiskLimitReached": False,
                    }
                ],
                "Notifications": [
                    {
                        "Type": "info",
                        "Domain": "server",
                        "Message": "Destination ready.",
                        "ReferenceID": "REF_ID_GENERAL",
                        "Timestamp": 1617277710219,
                    }
                ],
            },
            "Measurement": {
                "StartDateTime": 1656070697593,
                "TimeLeft": 5992.0,
                "ElapsedTime": 189.855,
                "FrameCount": 379617,
                "DroppedFrames": 0,
                "Status": "DA_RECORDING",
                "PixelEventRate": 1455120,
                "Tdc1EventRate": 100,
                "Tdc2EventRate": 100,
            },
            "Detector": {"DetectorType": "Tpx3"},
        }
    )

    assert dashboard.server.software_version == "3.3.0"
    assert dashboard.server.disk_space[0].path == Path("/data/raw")
    assert dashboard.server.notifications[0].reference_id == "REF_ID_GENERAL"
    assert dashboard.measurement is not None
    assert dashboard.measurement.frame_count == 379617
    assert dashboard.measurement.status == "DA_RECORDING"
    assert dashboard.detector is not None
    assert dashboard.detector.detector_type == "Tpx3"

    dumped = dashboard.model_dump(mode="json", by_alias=True)
    assert dumped["Server"]["SoftwareVersion"] == "3.3.0"
    assert dumped["Measurement"]["FrameCount"] == 379617
    assert dumped["Detector"]["DetectorType"] == "Tpx3"


def test_serval_dashboard_accepts_pythonic_field_names() -> None:
    dashboard = ServalDashboard.model_validate(
        {
            "server": {
                "software_version": "3.3.0",
                "disk_space": [{"path": "/data/raw", "free_space": 1024}],
            },
            "measurement": {"status": "DA_IDLE", "frame_count": 0},
            "detector": {"detector_type": "Tpx3"},
        }
    )

    assert dashboard.server.software_version == "3.3.0"
    assert dashboard.measurement is not None
    assert dashboard.measurement.status == "DA_IDLE"


def test_serval_dashboard_rejects_invalid_measurement_status() -> None:
    with pytest.raises(ValidationError, match="Status"):
        ServalDashboard.model_validate(
            {
                "Server": {"SoftwareVersion": "3.3.0"},
                "Measurement": {"Status": "RUNNING"},
            }
        )


def test_destination_configuration_validates_native_serval_payload() -> None:
    destination = DestinationConfiguration.model_validate(
        {
            "Raw": [
                {
                    "Base": "file:/data/raw",
                    "FilePattern": "raw%Hms_",
                    "SplitStrategy": "FRAME",
                    "QueueSize": 16384,
                }
            ],
            "Image": [
                {
                    "Base": "file:/data/image",
                    "FilePattern": "image%Hms_",
                    "Format": "tiff",
                    "Mode": "tot",
                    "Thresholds": [0, 1, 2, 3, 4, 5, 6, 7],
                    "IntegrationSize": 0,
                    "StopMeasurementOnDiskLimit": True,
                    "QueueSize": 1024,
                    "Corrections": [],
                }
            ],
            "Preview": {
                "Period": 0.1,
                "SamplingMode": "skipOnFrame",
                "ImageChannels": [
                    {
                        "Base": "http://localhost",
                        "Format": "tiff",
                        "Mode": "tot",
                    },
                    {
                        "Base": "tcp://connect@127.0.0.1:8088",
                        "Format": "jsonimage",
                        "Mode": "tot",
                        "IntegrationSize": -1,
                        "IntegrationMode": "last",
                    },
                ],
                "HistogramChannels": [
                    {
                        "Base": "tcp://listen@127.0.0.1:8089",
                        "Format": "jsonhisto",
                        "Mode": "tof",
                        "NumberOfBins": 100,
                        "BinWidth": 1.0,
                        "Offset": 0,
                    }
                ],
            },
        }
    )

    assert destination.raw[0].base == "file:/data/raw"
    assert destination.image[0].base == "file:/data/image"
    assert destination.preview is not None
    assert destination.preview.image_channels[0].base == "http://localhost"
    assert (
        destination.preview.image_channels[1].base
        == "tcp://connect@127.0.0.1:8088"
    )
    assert (
        destination.preview.histogram_channels[0].base
        == "tcp://listen@127.0.0.1:8089"
    )

    dumped = destination.model_dump(mode="json", by_alias=True)
    assert dumped["Raw"][0]["Base"] == "file:/data/raw"
    assert dumped["Preview"]["ImageChannels"][0]["Base"] == "http://localhost"
    assert dumped["Preview"]["HistogramChannels"][0]["Format"] == "jsonhisto"


def test_destination_configuration_accepts_pythonic_field_names() -> None:
    destination = DestinationConfiguration.model_validate(
        {
            "raw": [{"base": "file:/data/raw", "split_strategy": "frame"}],
            "preview": {
                "sampling_mode": "skipOnPeriod",
                "image_channels": [{"base": "http://localhost", "mode": "count"}],
            },
        }
    )

    assert destination.raw[0].split_strategy == "frame"
    assert destination.preview is not None
    assert destination.preview.sampling_mode == "skipOnPeriod"


def test_destination_configuration_rejects_flattened_destination_shape() -> None:
    with pytest.raises(ValidationError, match="destinations"):
        DestinationConfiguration.model_validate(
            {
                "destinations": [
                    {
                        "name": "raw",
                        "destination_type": "Raw",
                        "path": "/data/raw",
                    }
                ]
            }
        )


def test_destination_configuration_rejects_invalid_output_mode() -> None:
    with pytest.raises(ValidationError, match="Mode"):
        DestinationConfiguration.model_validate(
            {"Image": [{"Base": "file:/data/image", "Mode": "energy"}]}
        )


def test_serval_acquisition_state_separates_requested_and_applied_config() -> None:
    state = ServalAcquisitionState.model_validate(
        {
            "requested_detector_config": {
                "TriggerMode": "AUTOTRIGSTART_TIMERSTOP",
                "ExposureTime": 0.0002,
                "nTriggers": 10,
            },
            "applied_detector_config": {
                "TriggerMode": "AUTOTRIGSTART_TIMERSTOP",
                "ExposureTime": 0.0002,
                "nTriggers": 10,
                "BiasEnabled": True,
            },
            "requested_destination_configuration": {
                "Raw": [{"Base": "file:/requested/raw"}],
            },
            "applied_destination_configuration": {
                "Raw": [{"Base": "file:/applied/raw", "QueueSize": 1024}],
            },
        }
    )

    assert state.requested_detector_config is not None
    assert state.requested_detector_config.n_triggers == 10
    assert state.applied_detector_config is not None
    assert state.applied_detector_config.bias_enabled is True
    assert state.requested_destination_configuration is not None
    assert (
        state.requested_destination_configuration.raw[0].base
        == "file:/requested/raw"
    )
    assert state.applied_destination_configuration is not None
    assert state.applied_destination_configuration.raw[0].queue_size == 1024

    dumped = state.model_dump(mode="json", by_alias=True)
    assert dumped["requested_detector_config"]["TriggerMode"] == (
        "AUTOTRIGSTART_TIMERSTOP"
    )
    assert dumped["requested_detector_config"]["nTriggers"] == 10
    assert dumped["applied_detector_config"]["BiasEnabled"] is True
    assert dumped["requested_destination_configuration"]["Raw"][0]["Base"] == (
        "file:/requested/raw"
    )
    assert (
        dumped["applied_destination_configuration"]["Raw"][0]["QueueSize"] == 1024
    )


def test_serval_acquisition_state_rejects_legacy_destination_field() -> None:
    with pytest.raises(ValidationError, match="destination_configuration"):
        ServalAcquisitionState.model_validate(
            {"destination_configuration": {"Raw": [{"Base": "file:/data/raw"}]}}
        )
