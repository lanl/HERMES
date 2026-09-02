from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes.state.models.acquisition.serval import (
    CalibrationState,
    DacsFile,
    DacsLoad,
    DestinationConfiguration,
    PixelConfigFile,
    PixelConfigLoad,
    ServalAcquisitionState,
    ServalDashboard,
    ServalServer,
)


HASH = "a" * 64


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
    assert dashboard.server.disk_space[0].path == "/data/raw"
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


def test_calibration_state_records_saved_files_and_serval_loads() -> None:
    pixel_config_file = PixelConfigFile(
        path="config/pixelConfig.bpc",
        source_path="/detector-setup/tpx3-demo.bpc",
        file_hash=HASH,
    )
    dacs_file = DacsFile(
        path="config/dacsFile.dacs",
        source_path="/detector-setup/tpx3-demo.dacs",
        file_hash=HASH,
    )

    calibration = CalibrationState.model_validate(
        {
            "pixel_config_file": pixel_config_file.model_dump(mode="json"),
            "dacs_file": dacs_file.model_dump(mode="json"),
            "pixel_config_load": {
                "server_file_path": "~/tpx3-demo.bpc",
                "applied_at": "2026-05-04T12:00:00Z",
                "status": "completed",
                "http_status_code": 200,
                "server_response_body": "Successfully uploaded config.",
            },
            "dacs_load": {
                "server_file_path": "~/tpx3-demo.dacs",
                "applied_at": "2026-05-04T12:00:01Z",
                "status": "completed",
                "http_status_code": 200,
                "server_response_body": "Successfully uploaded config.",
            },
        }
    )

    assert calibration.pixel_config_file is not None
    assert calibration.pixel_config_file.path == Path("config/pixelConfig.bpc")
    assert calibration.dacs_file is not None
    assert calibration.dacs_file.file_hash == HASH
    assert calibration.pixel_config_load is not None
    assert calibration.pixel_config_load.server_file_path == "~/tpx3-demo.bpc"
    assert calibration.pixel_config_load.http_status_code == 200
    assert calibration.dacs_load is not None
    assert calibration.dacs_load.server_file_path == "~/tpx3-demo.dacs"

    dumped = calibration.model_dump(mode="json")
    assert dumped["pixel_config_file"]["path"] == "config/pixelConfig.bpc"
    assert dumped["dacs_file"]["path"] == "config/dacsFile.dacs"
    assert dumped["pixel_config_load"]["server_response_body"] == (
        "Successfully uploaded config."
    )


@pytest.mark.parametrize(
    ("model", "path", "message"),
    [
        (PixelConfigFile, "config/pixelConfig.dacs", ".bpc"),
        (DacsFile, "config/dacsFile.json", ".dacs"),
        (PixelConfigFile, "/tmp/pixelConfig.bpc", "relative"),
        (DacsFile, "/tmp/dacsFile.dacs", "relative"),
        (PixelConfigFile, "../pixelConfig.bpc", "relative"),
        (DacsFile, "../dacsFile.dacs", "relative"),
    ],
)
def test_saved_calibration_files_validate_paths(
    model: type[PixelConfigFile] | type[DacsFile],
    path: str,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        model(path=path, file_hash=HASH)


@pytest.mark.parametrize("model", [PixelConfigFile, DacsFile])
def test_saved_calibration_files_require_sha256_hash(
    model: type[PixelConfigFile] | type[DacsFile],
) -> None:
    suffix = ".bpc" if model is PixelConfigFile else ".dacs"
    with pytest.raises(ValidationError, match="file_hash"):
        model(path=f"config/settings{suffix}", file_hash="not-a-sha256-hash")


def test_calibration_state_rejects_legacy_responses_field() -> None:
    with pytest.raises(ValidationError, match="responses"):
        CalibrationState.model_validate({"responses": {"pixelconfig": "loaded"}})


@pytest.mark.parametrize("model", [PixelConfigLoad, DacsLoad])
def test_serval_config_load_validates_http_status_code(
    model: type[PixelConfigLoad] | type[DacsLoad],
) -> None:
    with pytest.raises(ValidationError, match="http_status_code"):
        model(server_file_path="settings", http_status_code=99)

    with pytest.raises(ValidationError, match="http_status_code"):
        model(server_file_path="settings", http_status_code=600)


def test_serval_acquisition_state_loads_config() -> None:
    state = ServalAcquisitionState.model_validate(
        {
            "config": {
                "serval": {
                    "url": "http://localhost:8080",
                    "program_path": "/opt/serval/serv-3.3.0.jar",
                    "version": "3.3.0",
                },
                "calibration_files": {
                    "pixel_config_file": "/data/calib/chip.bpc",
                    "dacs_file": "/data/calib/chip.dacs",
                },
                "detector_config": {
                    "TriggerMode": "AUTOTRIGSTART_TIMERSTOP",
                    "ExposureTime": 0.0002,
                    "TriggerPeriod": 0.01,
                    "nTriggers": 10,
                },
                "run_timing": {
                    "trigger_mode": "AUTOTRIGSTART_TIMERSTOP",
                    "exposure_time_s": 0.0005,
                    "trigger_count": 25,
                },
            },
        }
    )

    assert state.status == "planned"
    assert state.config.serval.program_path == Path("/opt/serval/serv-3.3.0.jar")
    assert state.config.serval.version == "3.3.0"
    assert state.config.calibration_files is not None
    assert state.config.calibration_files.pixel_config_file == Path(
        "/data/calib/chip.bpc"
    )
    assert state.config.detector_config is not None
    assert state.config.detector_config.n_triggers == 10
    assert state.config.run_timing is not None
    assert state.config.run_timing.trigger_count == 25

    dumped = state.model_dump(mode="json", by_alias=True)
    assert dumped["config"]["detector_config"]["TriggerMode"] == (
        "AUTOTRIGSTART_TIMERSTOP"
    )
    assert dumped["config"]["detector_config"]["nTriggers"] == 10
    assert dumped["config"]["run_timing"]["trigger_count"] == 25


def test_serval_acquisition_state_accepts_detector_config_file() -> None:
    state = ServalAcquisitionState.model_validate(
        {
            "config": {
                "serval": {"url": "http://localhost:8080"},
                "detector_config_file": "/data/detector.json",
            }
        }
    )

    assert state.config.detector_config is None
    assert state.config.detector_config_file == Path("/data/detector.json")


def test_serval_acquisition_config_rejects_bad_file_suffixes() -> None:
    with pytest.raises(ValidationError, match="program_path"):
        ServalAcquisitionState.model_validate(
            {"config": {"serval": {"url": "u", "program_path": "/x/serv.txt"}}}
        )
    with pytest.raises(ValidationError, match="pixel_config_file"):
        ServalAcquisitionState.model_validate(
            {
                "config": {
                    "serval": {"url": "u"},
                    "calibration_files": {
                        "pixel_config_file": "/a.txt",
                        "dacs_file": "/b.dacs",
                    },
                }
            }
        )
    with pytest.raises(ValidationError, match="detector_config_file"):
        ServalAcquisitionState.model_validate(
            {
                "config": {
                    "serval": {"url": "u"},
                    "detector_config_file": "/x/cfg.yaml",
                }
            }
        )


def test_serval_acquisition_state_rejects_removed_request_fields() -> None:
    with pytest.raises(ValidationError, match="requested_detector_config"):
        ServalAcquisitionState.model_validate(
            {
                "config": {"serval": {"url": "http://localhost:8080"}},
                "requested_detector_config": {"nTriggers": 10},
            }
        )


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("3.3.0", 3),
        ("2.1.6", 2),
        ("v3.0.0", 3),
        (None, None),
        ("unknown", None),
    ],
)
def test_serval_server_parses_major_version(
    version: str | None,
    expected: int | None,
) -> None:
    server = ServalServer(url="http://localhost:8080", version=version)
    assert server.major_version == expected


def test_serval_server_validates_tcp_ip() -> None:
    with pytest.raises(ValidationError, match="tcp_ip"):
        ServalServer(url="http://localhost:8080", tcp_ip="not-an-ip")


def test_serval_server_allows_tcp_flags_on_version_3() -> None:
    server = ServalServer(
        url="http://localhost:8080",
        version="3.3.0",
        tcp_ip="192.168.100.1",
        tcp_port=50000,
    )
    assert server.tcp_ip == "192.168.100.1"
    assert server.tcp_port == 50000


@pytest.mark.parametrize("field", ["tcp_ip", "tcp_port"])
def test_serval_server_rejects_tcp_flags_on_version_2(field: str) -> None:
    value: object = "192.168.100.1" if field == "tcp_ip" else 50000
    with pytest.raises(ValidationError, match="3.0 or newer"):
        ServalServer(url="http://localhost:8080", version="2.1.6", **{field: value})


def test_serval_server_does_not_gate_tcp_flags_when_version_unset() -> None:
    server = ServalServer(url="http://localhost:8080", tcp_ip="192.168.100.1")
    assert server.tcp_ip == "192.168.100.1"
    assert server.major_version is None
