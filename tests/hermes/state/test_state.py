from __future__ import annotations

from pathlib import Path

from hermes.state.models.acquisition.serval import (
    CalibrationState,
    DacsFile,
    PixelConfigFile,
    ServalAcquisitionResult,
    ServalAcquisitionState,
)
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3SpidrUnpackerProgram,
    Tpx3SpidrUnpackerResult,
    Tpx3SpidrUnpackerSettings,
    Tpx3SpidrUnpackingRun,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import FileReference
from hermes.state.state import HermesRecord


HASH = "a" * 64


def test_hermes_record_serializes_paths_datetimes_and_mode_tags(tmp_path: Path) -> None:
    raw_file = FileReference(
        path=tmp_path / "run-001/data/tpx3/raw.tpx3",
        media_type="application/octet-stream",
        sha256=HASH,
        size_bytes=1024,
    )
    summary_file = FileReference(
        path=tmp_path / "run-001/data/analyzed/summary.json",
        media_type="application/json",
    )
    record = HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id=" LC-20231023 ",
            run_number=1,
            beamline="DCS",
        ),
        environment=RuntimeEnvironment(working_dir=tmp_path / "run-001"),
        acquisition=ServalAcquisitionState(
            result=ServalAcquisitionResult(status="completed", output_files=[raw_file])
        ),
        analysis=HermesTpx3AnalysisState(
            unpacking_runs=[
                Tpx3SpidrUnpackingRun(
                    program=Tpx3SpidrUnpackerProgram(
                        name="tpx3-spidr-cpp",
                        executable_path=tmp_path / "bin/hermes-tpx3-spidr",
                        version="0.1.0",
                    ),
                    settings=Tpx3SpidrUnpackerSettings(
                        input_tpx3_file=raw_file,
                        tpx3_parquet_directory=(
                            tmp_path / "run-001/data/analyzed/tpx3_parquet"
                        ),
                        command_args=[
                            str(raw_file.path),
                            str(tmp_path / "run-001/data/analyzed/tpx3_parquet"),
                        ],
                    ),
                    result=Tpx3SpidrUnpackerResult(
                        status="completed",
                        exit_code=0,
                        summary_json_file=summary_file,
                        pixel_hit_count=42,
                        tdc_hit_count=3,
                    ),
                )
            ]
        ),
    )

    dumped = record.model_dump(mode="json")

    assert dumped["measurement_info"]["measurement_id"] == "LC-20231023"
    assert dumped["environment"]["working_dir"]["resolved_path"] == str(
        (tmp_path / "run-001").resolve()
    )
    assert dumped["environment"]["raw_data_dir"]["resolved_path"] is None
    assert dumped["acquisition"]["mode"] == "serval"
    assert dumped["acquisition"]["result"]["output_files"][0]["path"].endswith(
        "raw.tpx3"
    )
    assert dumped["analysis"]["mode"] == "hermes"
    assert dumped["analysis"]["unpacking_runs"][0]["result"][
        "pixel_hit_count"
    ] == 42


def test_hermes_record_serializes_serval_requested_applied_and_calibration(
    tmp_path: Path,
) -> None:
    pixel_config_file = PixelConfigFile(
        path="config/pixelConfig.bpc",
        source_path=tmp_path / "tpx3-demo.bpc",
        file_hash=HASH,
    )
    dacs_file = DacsFile(
        path="config/dacsFile.dacs",
        source_path=tmp_path / "tpx3-demo.dacs",
        file_hash=HASH,
    )
    record = HermesRecord(
        measurement_info=MeasurementInfo(measurement_id="LC-20231024", run_number=2),
        environment=RuntimeEnvironment(working_dir=tmp_path / "run-002"),
        acquisition=ServalAcquisitionState(
            requested_detector_config={
                "TriggerMode": "AUTOTRIGSTART_TIMERSTOP",
                "ExposureTime": 0.0002,
                "nTriggers": 100,
            },
            applied_detector_config={
                "TriggerMode": "AUTOTRIGSTART_TIMERSTOP",
                "ExposureTime": 0.0002,
                "nTriggers": 100,
                "BiasEnabled": True,
            },
            requested_destination_configuration={
                "Raw": [{"Base": "file:/requested/raw"}],
            },
            applied_destination_configuration={
                "Raw": [{"Base": "file:/applied/raw", "QueueSize": 16384}],
            },
            calibration=CalibrationState(
                pixel_config_file=pixel_config_file,
                dacs_file=dacs_file,
                pixel_config_load={
                    "server_file_path": "tpx3-demo.bpc",
                    "status": "completed",
                    "http_status_code": 200,
                    "server_response_body": "Successfully uploaded config.",
                },
                dacs_load={
                    "server_file_path": "tpx3-demo.dacs",
                    "status": "completed",
                    "http_status_code": 200,
                    "server_response_body": "Successfully uploaded config.",
                },
            ),
        ),
    )

    dumped = record.model_dump(mode="json", by_alias=True)
    acquisition = dumped["acquisition"]

    assert acquisition["requested_detector_config"]["TriggerMode"] == (
        "AUTOTRIGSTART_TIMERSTOP"
    )
    assert acquisition["applied_detector_config"]["BiasEnabled"] is True
    assert acquisition["requested_destination_configuration"]["Raw"][0]["Base"] == (
        "file:/requested/raw"
    )
    assert (
        acquisition["applied_destination_configuration"]["Raw"][0]["QueueSize"]
        == 16384
    )
    assert acquisition["calibration"]["pixel_config_file"]["path"] == (
        "config/pixelConfig.bpc"
    )
    assert acquisition["calibration"]["pixel_config_load"][
        "server_file_path"
    ] == (
        "tpx3-demo.bpc"
    )
    assert acquisition["calibration"]["dacs_load"]["server_file_path"] == (
        "tpx3-demo.dacs"
    )
    assert acquisition["calibration"]["pixel_config_load"][
        "server_response_body"
    ] == (
        "Successfully uploaded config."
    )
