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
    HermesTpx3UnpackingResult,
    Tpx3Unpacking,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import BinaryProgram, FileReference
from hermes.state.state import HermesRecord


HASH = "a" * 64


def test_run_directory_defaults_to_run_name_when_omitted(tmp_path: Path) -> None:
    record = HermesRecord.model_validate(
        {
            "measurement_info": {"measurement_id": "LC-1", "run": "ambe-run"},
            "environment": {
                "working_directory": str(tmp_path),
                "raw_data_directory": "raw",
            },
        }
    )

    run_directory = record.environment.run_directory
    assert run_directory.path == Path("ambe-run")
    assert run_directory.resolved_path == (tmp_path / "ambe-run").resolve()
    # Sub-directories nest under the derived run directory.
    assert record.environment.raw_data_directory.resolved_path == (
        tmp_path / "ambe-run" / "raw"
    ).resolve()


def test_explicit_run_directory_overrides_run_name(tmp_path: Path) -> None:
    record = HermesRecord.model_validate(
        {
            "measurement_info": {"measurement_id": "LC-1", "run": "ambe-run"},
            "environment": {
                "working_directory": str(tmp_path),
                "run_directory": "explicit-dir",
                "raw_data_directory": "raw",
            },
        }
    )

    assert record.environment.run_directory.path == Path("explicit-dir")
    assert record.environment.raw_data_directory.resolved_path == (
        tmp_path / "explicit-dir" / "raw"
    ).resolve()


def test_record_without_analysis_needs_no_analysis_directory(
    tmp_path: Path,
) -> None:
    record = HermesRecord(
        measurement_info=MeasurementInfo(measurement_id="LC-1", run="test-run"),
        environment=RuntimeEnvironment(working_directory=tmp_path),
        analysis=None,
    )

    assert record.analysis is None
    assert record.environment.analysis_directory.resolved_path is None


def test_hermes_record_serializes_paths_datetimes_and_mode_tags(tmp_path: Path) -> None:
    raw_file = FileReference(
        path=tmp_path / "run-001/data/tpx3/raw.tpx3",
        media_type="application/octet-stream",
    )
    record = HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id=" LC-20231023 ",
            run="test-run",
            beamline="DCS",
        ),
        environment=RuntimeEnvironment(
            working_directory=tmp_path / "run-001",
            analysis_directory=tmp_path / "run-001/data/analyzed",
        ),
        acquisition=ServalAcquisitionState(
            config={"serval": {"url": "http://localhost:8080"}},
            status="completed",
            result=ServalAcquisitionResult(output_files=[raw_file]),
        ),
        analysis=HermesTpx3AnalysisState(
            unpacking=Tpx3Unpacking(
                program=BinaryProgram(
                    name="tpx3-spidr-cpp",
                    executable_path=tmp_path / "bin/hermes-tpx3-spidr",
                    version="0.1.0",
                ),
                tpx3_files=[raw_file],
                results=[
                    HermesTpx3UnpackingResult(
                        input_file=raw_file,
                        status="completed",
                    )
                ],
            ),
        ),
    )

    dumped = record.model_dump(mode="json")

    assert dumped["measurement_info"]["measurement_id"] == "LC-20231023"
    assert dumped["environment"]["working_directory"]["resolved_path"] == str(
        (tmp_path / "run-001").resolve()
    )
    assert dumped["environment"]["raw_data_directory"]["resolved_path"] is None
    assert dumped["acquisition"]["mode"] == "serval"
    assert dumped["acquisition"]["result"]["output_files"][0]["path"].endswith(
        "raw.tpx3"
    )
    assert dumped["analysis"]["mode"] == "hermes"
    assert dumped["analysis"]["unpacking"]["tpx3_files"][0]["path"].endswith(
        "raw.tpx3"
    )
    assert (
        dumped["analysis"]["unpacking"]["results"][0]["status"] == "completed"
    )


def test_hermes_record_serializes_serval_config_and_calibration(
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
        measurement_info=MeasurementInfo(measurement_id="LC-20231024", run="test-run"),
        environment=RuntimeEnvironment(working_directory=tmp_path / "run-002"),
        acquisition=ServalAcquisitionState(
            config={
                "serval": {
                    "url": "http://localhost:8080",
                    "program_path": str(tmp_path / "serv-3.3.0.jar"),
                    "version": "3.3.0",
                },
                "calibration_files": {
                    "pixel_config_file": str(tmp_path / "tpx3-demo.bpc"),
                    "dacs_file": str(tmp_path / "tpx3-demo.dacs"),
                },
                "detector_config": {
                    "TriggerMode": "AUTOTRIGSTART_TIMERSTOP",
                    "ExposureTime": 0.0002,
                    "nTriggers": 100,
                    "BiasEnabled": True,
                },
                "run_timing": {
                    "trigger_mode": "AUTOTRIGSTART_TIMERSTOP",
                    "exposure_time_s": 0.0005,
                    "trigger_count": 25,
                },
            },
            destination={
                "Raw": [{"Base": "file:/data/raw", "QueueSize": 16384}],
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

    assert acquisition["config"]["serval"]["url"] == "http://localhost:8080"
    assert acquisition["config"]["serval"]["version"] == "3.3.0"
    assert acquisition["config"]["detector_config"]["TriggerMode"] == (
        "AUTOTRIGSTART_TIMERSTOP"
    )
    assert acquisition["config"]["detector_config"]["nTriggers"] == 100
    assert acquisition["config"]["detector_config"]["BiasEnabled"] is True
    assert acquisition["config"]["run_timing"]["trigger_count"] == 25
    assert acquisition["destination"]["Raw"][0]["QueueSize"] == 16384
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
