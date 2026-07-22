from __future__ import annotations

from pathlib import Path

from hermes.state.models.acquisition.serval import (
    CalibrationState,
    ServalAcquisitionResult,
    ServalAcquisitionState,
)
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3SpidrAnalysisState,
    HermesTpx3SpidrResult,
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
    event_file = FileReference(
        path=tmp_path / "run-001/data/analyzed/events.parquet",
        media_type="application/parquet",
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
        analysis=HermesTpx3SpidrAnalysisState(
            result=HermesTpx3SpidrResult(
                status="completed",
                input_files=[raw_file],
                output_files=[event_file],
                summary_metrics={"events": 42, "duration_s": 1.5},
            )
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
    assert dumped["analysis"]["mode"] == "hermes_tpx3_spidr"
    assert dumped["analysis"]["result"]["summary_metrics"]["events"] == 42


def test_hermes_record_serializes_serval_requested_applied_and_calibration(
    tmp_path: Path,
) -> None:
    pixel_config_file = FileReference(
        path=tmp_path / "config/tpx3-demo.bpc",
        media_type="application/octet-stream",
        sha256=HASH,
        size_bytes=2048,
    )
    dacs_file = FileReference(
        path=tmp_path / "config/tpx3-demo.dacs",
        media_type="application/json",
        size_bytes=512,
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
                pixel_config_load_request={
                    "format": "pixelconfig",
                    "file": "tpx3-demo.bpc",
                    "source_file": pixel_config_file.model_dump(mode="json"),
                },
                dacs_load_request={
                    "format": "dacs",
                    "file": "tpx3-demo.dacs",
                    "source_file": dacs_file.model_dump(mode="json"),
                },
                pixel_config_load_result={
                    "status": "completed",
                    "http_status_code": 200,
                    "response_text": "Successfully uploaded config.",
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
    assert acquisition["calibration"]["pixel_config_file"]["path"].endswith(
        "tpx3-demo.bpc"
    )
    assert acquisition["calibration"]["pixel_config_load_request"]["file"] == (
        "tpx3-demo.bpc"
    )
    assert acquisition["calibration"]["dacs_load_request"]["file"] == "tpx3-demo.dacs"
    assert acquisition["calibration"]["pixel_config_load_result"]["response_text"] == (
        "Successfully uploaded config."
    )
