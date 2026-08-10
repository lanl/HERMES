from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from loguru import logger

from hermes.runner.analysis.hermes.run import HermesAnalysisError, run_hermes_analysis
from hermes.runner.analysis.hermes.unpacker import (
    HermesTpx3PreflightError,
    check_previous_unpacked_file,
    derive_summary_path,
    derive_unpacker_command,
    validate_program_and_inputs,
)
from hermes.state.models.analysis.empir import EmpirAnalysisState
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3SpidrSummary,
    Tpx3Unpacking,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import BinaryProgram, FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.change_requests import ChangeRequest
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_manager import StateManager


class CapturingStateLogger:
    def __init__(self) -> None:
        self.changes: list[ChangeRequest] = []
        self.initial_records: list[HermesRecord] = []

    def log_initial_state(self, record: HermesRecord) -> None:
        self.initial_records.append(record.model_copy(deep=True))

    def log_change(self, change_request: ChangeRequest) -> None:
        self.changes.append(change_request.model_copy(deep=True))

    def log_validation_failure(
        self,
        path: str,
        error: str,
        *,
        change_id: str | None = None,
        proposed_value: Any = None,
    ) -> None:
        raise AssertionError(f"unexpected validation failure for {path}: {error}")


def _analysis_root(tmp_path: Path) -> Path:
    return tmp_path / "analysis"


def _measurement_info() -> MeasurementInfo:
    return MeasurementInfo(measurement_id="stage-3", run="test-run")


def _analysis(tmp_path: Path, *raw_names: str) -> HermesTpx3AnalysisState:
    executable = tmp_path / "bin/hermes-tpx3-spidr"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.touch()

    raw_files: list[FileReference] = []
    for raw_name in raw_names:
        raw_path = tmp_path / "rawTpx3" / raw_name
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.touch()
        raw_files.append(FileReference(path=raw_path))

    return HermesTpx3AnalysisState(
        unpacking=Tpx3Unpacking(
            program=BinaryProgram(
                name="tpx3-spidr-cpp",
                executable_path=executable,
                version="0.1.0",
            ),
            tpx3_files=raw_files,
        ),
    )


def _record(
    tmp_path: Path,
    analysis: HermesTpx3AnalysisState | EmpirAnalysisState | None,
) -> HermesRecord:
    return HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id="stage-3",
            run="test-run",
        ),
        environment=RuntimeEnvironment(
            working_directory=tmp_path,
            analysis_directory=_analysis_root(tmp_path),
        ),
        acquisition=None,
        analysis=analysis,
    )


def _summary(
    analysis_root: Path,
    raw_stem: str,
    *,
    pixel_rows: int = 0,
) -> Tpx3SpidrSummary:
    # The binary writes each Parquet path as the analysis directory it was given
    # joined with the category subdirectory and filename.
    pixel_files = (
        [
            str(
                analysis_root
                / "pixel_hits"
                / f"{raw_stem}_chip_0_pixels_00000.parquet"
            )
        ]
        if pixel_rows
        else []
    )
    return Tpx3SpidrSummary.model_validate(
        {
            "measurement_info": {
                "measurement_id": "stage-3",
                "run": "test-run",
            },
            "inputfile": f"rawTpx3/{raw_stem}.tpx3",
            "unpacking": {
                "bytes_read": 0,
                "chunks_read": 0,
                "packets_read": pixel_rows,
                "pixel_data_packets": pixel_rows,
                "tdc_timestamps": 0,
                "heartbeat_packets": 0,
                "spidr_control_packets": 0,
                "tpx3_control_packets": 0,
                "unrecognized_packets": 0,
                "tdc1_rising": 0,
                "tdc1_falling": 0,
                "tdc2_rising": 0,
                "tdc2_falling": 0,
                "unknown_tdc_edges": 0,
                "errors": [],
                "warnings": [],
            },
            "timestamp_processing": {
                "heartbeat_pairs": {
                    "number_of_beats": 0,
                },
                "time_adjustments": {
                    "pixel_packets": pixel_rows,
                    "tdc_packets": 0,
                    "control_packets": 0,
                    "failed": 0,
                },
            },
            "sorting": {
                "strategy": "in_memory",
                "memory_budget_bytes": 0,
                "estimated_memory_bytes": 0,
                "sorting_time_seconds": 0.0,
            },
            "output_parquet": {
                "pixel_data": {
                    "row_count": pixel_rows,
                    "files": pixel_files,
                },
                "tdc_timestamps": {"row_count": 0, "files": []},
                "heartbeat_packets": {"row_count": 0, "files": []},
                "control_packets": {"row_count": 0, "files": []},
                "unrecognized_packets": {"row_count": 0, "files": []},
                "errors": [],
            },
            "processing_times_seconds": {
                "canonical_time_seconds": 2.0345e-12,
                "unpacking": 0,
                "canonical_conversion": 0,
                "time_adjustments": 0,
                "sorting": 0,
                "parquet_writing": 0,
                "total": 0,
                "throughput": {
                    "packets_per_second": 0,
                    "megabytes_per_second": 0,
                },
            },
        }
    )


def _save_completed_files(
    analysis_root: Path,
    raw_file: FileReference,
    *,
    pixel_rows: int = 0,
) -> None:
    summary = _summary(analysis_root, raw_file.path.stem, pixel_rows=pixel_rows)
    for parquet_path in summary.output_parquet.pixel_data.files:
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table({"value": [1]}), parquet_path)
    summary_path = derive_summary_path(analysis_root, raw_file)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary.model_dump_json(), encoding="utf-8")


def test_derives_command_and_input_specific_summary_path(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "first.tpx3")
    analysis_root = _analysis_root(tmp_path)
    raw_file = analysis.unpacking.tpx3_files[0]

    assert derive_unpacker_command(
        analysis, analysis_root, raw_file, _measurement_info()
    ) == [
        str(analysis.unpacking.program.executable_path),
        "--input",
        str(raw_file.path),
        "--output",
        str(analysis_root),
        "--measurement-id",
        "stage-3",
        "--run",
        "test-run",
    ]
    assert derive_summary_path(analysis_root, raw_file) == (
        analysis_root / "logs/unpacking/first_unpacker_summary.json"
    )


def test_command_includes_time_sort_false_when_time_sort_disabled(
    tmp_path: Path,
) -> None:
    analysis = _analysis(tmp_path, "first.tpx3")
    analysis_root = _analysis_root(tmp_path)
    analysis.unpacking.runtime_options.time_sort = False
    raw_file = analysis.unpacking.tpx3_files[0]

    assert derive_unpacker_command(
        analysis, analysis_root, raw_file, _measurement_info()
    ) == [
        str(analysis.unpacking.program.executable_path),
        "--input",
        str(raw_file.path),
        "--output",
        str(analysis_root),
        "--measurement-id",
        "stage-3",
        "--run",
        "test-run",
        "--time-sort",
        "false",
    ]


def test_fresh_files_are_not_previously_unpacked(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "first.tpx3", "second.tpx3")
    analysis_root = _analysis_root(tmp_path)

    assert not any(
        check_previous_unpacked_file(analysis_root, raw_file)
        for raw_file in analysis.unpacking.tpx3_files
    )


def test_completed_file_is_detected_as_previously_unpacked(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "completed.tpx3")
    analysis_root = _analysis_root(tmp_path)
    raw_file = analysis.unpacking.tpx3_files[0]
    _save_completed_files(analysis_root, raw_file, pixel_rows=1)

    assert check_previous_unpacked_file(analysis_root, raw_file)


@pytest.mark.parametrize("missing_file", ["executable", "raw_tpx3"])
def test_validate_rejects_missing_required_files(
    tmp_path: Path,
    missing_file: str,
) -> None:
    analysis = _analysis(tmp_path, "missing.tpx3")
    analysis_root = _analysis_root(tmp_path)
    path = (
        analysis.unpacking.program.executable_path
        if missing_file == "executable"
        else analysis.unpacking.tpx3_files[0].path
    )
    path.unlink()

    with pytest.raises(HermesTpx3PreflightError, match="does not exist"):
        validate_program_and_inputs(analysis, analysis_root)


def test_plan_rejects_duplicate_raw_filename_stems(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "first.tpx3", "second.tpx3")
    duplicate = tmp_path / "other/first.tpx3"
    duplicate.parent.mkdir()
    duplicate.touch()

    with pytest.raises(ValueError, match="stems must be unique"):
        analysis.unpacking.tpx3_files = [
            analysis.unpacking.tpx3_files[0],
            FileReference(path=duplicate),
        ]


def test_run_marks_analysis_only_state_running_through_state_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis(tmp_path, "first.tpx3", "second.tpx3")
    state_logger = CapturingStateLogger()
    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=state_logger,
    )
    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.run.execute_unpacker",
        lambda analysis, analysis_root, raw_file, measurement_info, **kwargs: (
            _summary(analysis_root, raw_file.path.stem)
        ),
    )

    files_to_run = run_hermes_analysis(manager)

    assert [raw.path.name for raw in files_to_run] == [
        "first.tpx3",
        "second.tpx3",
    ]
    results = manager.get_state().analysis.unpacking.results
    assert [result.input_file.path.name for result in results] == [
        "first.tpx3",
        "second.tpx3",
    ]
    assert all(result.status == "completed" for result in results)
    assert state_logger.changes[-1].path == "analysis.unpacking.results"
    assert state_logger.changes[-1].origin == "trusted_workflow"
    assert state_logger.changes[-1].proposer == "tpx3_spidr_unpacking"
    assert state_logger.changes[-1].status == "applied"


def test_run_with_only_completed_files_does_not_mark_running(
    tmp_path: Path,
) -> None:
    analysis = _analysis(tmp_path, "completed.tpx3")
    _save_completed_files(_analysis_root(tmp_path), analysis.unpacking.tpx3_files[0])
    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=CapturingStateLogger(),
    )

    assert run_hermes_analysis(manager) == []
    results = manager.get_state().analysis.unpacking.results
    assert len(results) == 1
    assert results[0].status == "skipped"


def test_run_rejects_empir_analysis(tmp_path: Path) -> None:
    empir = EmpirAnalysisState.model_construct(mode="empir")
    manager = StateManager(_record(tmp_path, empir), state_logger=CapturingStateLogger())
    records: list[dict[str, Any]] = []
    sink_id = logger.add(
        lambda message: records.append(message.record),
        filter=lambda record: record["extra"].get("domain") == "analysis",
    )

    try:
        with pytest.raises(HermesAnalysisError, match="no valid HERMES analysis"):
            run_hermes_analysis(manager)
    finally:
        logger.remove(sink_id)

    invalid_mode = next(
        record
        for record in records
        if record["extra"].get("event_type") == "analysis.hermes.invalid_mode"
    )
    assert invalid_mode["level"].name == "ERROR"
    assert "Cannot run HERMES analysis" in invalid_mode["message"]
    assert invalid_mode["extra"]["measurement_id"] == "stage-3"
    assert invalid_mode["extra"]["run"] == "test-run"
    assert invalid_mode["extra"]["expected_analysis_mode"] == "hermes"
    assert invalid_mode["extra"]["actual_analysis_mode"] == "empir"


def test_run_rejects_missing_analysis(tmp_path: Path) -> None:
    manager = StateManager(_record(tmp_path, None), state_logger=CapturingStateLogger())
    records: list[dict[str, Any]] = []
    sink_id = logger.add(
        lambda message: records.append(message.record),
        filter=lambda record: record["extra"].get("domain") == "analysis",
    )

    try:
        with pytest.raises(HermesAnalysisError, match="no valid HERMES analysis"):
            run_hermes_analysis(manager)
    finally:
        logger.remove(sink_id)

    invalid_mode = next(
        record
        for record in records
        if record["extra"].get("event_type") == "analysis.hermes.invalid_mode"
    )
    assert invalid_mode["level"].name == "ERROR"
    assert invalid_mode["extra"]["actual_analysis_mode"] is None


def test_resource_limit_percent_field_defaults_to_90(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "file.tpx3")
    assert analysis.resource_limit_percent == 90


def test_resource_limit_percent_accepts_integers_from_1_to_100(tmp_path: Path) -> None:
    executable = tmp_path / "bin/hermes-tpx3-spidr"
    executable.parent.mkdir(parents=True)
    executable.touch()
    raw_file = tmp_path / "raw.tpx3"
    raw_file.touch()

    for percent in [1, 50, 90, 100]:
        analysis = HermesTpx3AnalysisState(
            resource_limit_percent=percent,
            unpacking=Tpx3Unpacking(
                program=BinaryProgram(
                    name="test",
                    executable_path=executable,
                ),
                tpx3_files=[FileReference(path=raw_file)],
            ),
        )
        assert analysis.resource_limit_percent == percent


def test_resource_limit_percent_rejects_zero_and_above_100(tmp_path: Path) -> None:
    executable = tmp_path / "bin/hermes-tpx3-spidr"
    executable.parent.mkdir(parents=True)
    executable.touch()
    raw_file = tmp_path / "raw.tpx3"
    raw_file.touch()

    for invalid_percent in [0, 101, 200, -1]:
        with pytest.raises(Exception):
            HermesTpx3AnalysisState(
                resource_limit_percent=invalid_percent,
                unpacking=Tpx3Unpacking(
                    program=BinaryProgram(
                        name="test",
                        executable_path=executable,
                    ),
                    tpx3_files=[FileReference(path=raw_file)],
                ),
            )
