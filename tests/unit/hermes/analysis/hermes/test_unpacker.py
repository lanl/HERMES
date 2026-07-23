from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from hermes.analysis.hermes.run import HermesAnalysisError, run_hermes_analysis
from hermes.analysis.hermes.unpacker import (
    HermesTpx3PreflightError,
    derive_summary_path,
    derive_unpacker_command,
    plan_unpacking,
)
from hermes.state.models.analysis.empir import EmpirAnalysisState
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3SpidrSummary,
    Tpx3SpidrUnpackerProgram,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.change_requests import ChangeRequest
from hermes.state_service.shared_types import (
    ChangeApprovalError,
    StateServiceConfig,
)
from hermes.state_service.state_manager import StateManager


class CapturingStateLogger:
    def __init__(self) -> None:
        self.changes: list[ChangeRequest] = []

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
        unpacker_program=Tpx3SpidrUnpackerProgram(
            name="tpx3-spidr-cpp",
            executable_path=executable,
            version="0.1.0",
        ),
        analysis_directory=tmp_path / "analysis",
        tpx3_files=raw_files,
    )


def _record(
    tmp_path: Path,
    analysis: HermesTpx3AnalysisState | EmpirAnalysisState | None,
) -> HermesRecord:
    return HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id="stage-3",
            run_number=1,
        ),
        environment=RuntimeEnvironment(working_dir=tmp_path),
        acquisition=None,
        analysis=analysis,
    )


def _summary(raw_stem: str, *, pixel_rows: int = 0) -> Tpx3SpidrSummary:
    pixel_files = (
        [f"pixelHits/{raw_stem}-chip-0-part-00000.parquet"]
        if pixel_rows
        else []
    )
    return Tpx3SpidrSummary.model_validate(
        {
            "unpacking": {
                "chunks_read": 0,
                "packets_read": pixel_rows,
                "decoded_pixel_hits": pixel_rows,
                "decoded_tdc_triggers": 0,
                "decoded_global_timestamps": 0,
                "decoded_spidr_control_packets": 0,
                "decoded_tpx3_control_packets": 0,
                "decoded_unknown_packets": 0,
                "warnings": [],
                "errors": [],
            },
            "timestamp_processing": {
                "anchors": {
                    "total": 0,
                    "unpaired_low": 0,
                    "unpaired_high": 0,
                    "warnings": [],
                },
                "epoch_assignment": {
                    "pixels_assigned": pixel_rows,
                    "tdc_triggers_assigned": 0,
                    "controls_assigned": 0,
                    "ambiguous_timestamps": 0,
                    "unresolved_timestamps": 0,
                    "used_fallback": False,
                    "warnings": [],
                },
            },
            "sorting": {
                "method": "in_memory",
                "memory_budget_bytes": 0,
                "estimated_memory_bytes": 0,
                "temporary_runs_created": 0,
            },
            "parquet": {
                "pixel_hits": {
                    "row_count": pixel_rows,
                    "files": pixel_files,
                },
                "tdc_triggers": {"row_count": 0, "files": []},
                "global_timestamps": {"row_count": 0, "files": []},
                "control_packets": {"row_count": 0, "files": []},
                "unknown_packets": {"row_count": 0, "files": []},
                "errors": [],
            },
            "processing_times_seconds": {
                "unpacking": 0,
                "epoch_assignment": 0,
                "conversion": 0,
                "sorting": 0,
                "parquet_writing": 0,
                "total": 0,
            },
        }
    )


def _save_completed_files(
    analysis: HermesTpx3AnalysisState,
    raw_file: FileReference,
    *,
    pixel_rows: int = 0,
) -> None:
    summary = _summary(raw_file.path.stem, pixel_rows=pixel_rows)
    for relative_path in summary.parquet.pixel_hits.files:
        parquet_path = analysis.analysis_directory / relative_path
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        parquet_path.touch()
    summary_path = derive_summary_path(analysis, raw_file)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary.model_dump_json(), encoding="utf-8")


def test_derives_command_and_input_specific_summary_path(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "first.tpx3")
    raw_file = analysis.tpx3_files[0]

    assert derive_unpacker_command(analysis, raw_file) == [
        str(analysis.unpacker_program.executable_path),
        str(raw_file.path),
        str(analysis.analysis_directory),
    ]
    assert derive_summary_path(analysis, raw_file) == (
        analysis.analysis_directory / "logs/first-unpacker-summary.json"
    )


def test_plan_preserves_multiple_raw_file_order(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "first.tpx3", "second.tpx3")

    plan = plan_unpacking(analysis)

    assert [(raw.path.name, action) for raw, action in plan] == [
        ("first.tpx3", "run"),
        ("second.tpx3", "run"),
    ]


def test_plan_skips_valid_completed_files(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "completed.tpx3")
    raw_file = analysis.tpx3_files[0]
    _save_completed_files(analysis, raw_file, pixel_rows=1)

    assert plan_unpacking(analysis) == [(raw_file, "skip")]


@pytest.mark.parametrize("missing_file", ["executable", "raw_tpx3"])
def test_plan_rejects_missing_required_files(
    tmp_path: Path,
    missing_file: str,
) -> None:
    analysis = _analysis(tmp_path, "missing.tpx3")
    path = (
        analysis.unpacker_program.executable_path
        if missing_file == "executable"
        else analysis.tpx3_files[0].path
    )
    path.unlink()

    with pytest.raises(HermesTpx3PreflightError, match="does not exist"):
        plan_unpacking(analysis)


@pytest.mark.parametrize("invalid_existing_output", ["invalid_summary", "partial"])
def test_plan_rejects_invalid_or_partial_existing_output(
    tmp_path: Path,
    invalid_existing_output: str,
) -> None:
    analysis = _analysis(tmp_path, "broken.tpx3")
    if invalid_existing_output == "invalid_summary":
        summary_path = derive_summary_path(analysis, analysis.tpx3_files[0])
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text("not JSON", encoding="utf-8")
    else:
        parquet_path = (
            analysis.analysis_directory
            / "pixelHits/broken-chip-0-part-00000.parquet"
        )
        parquet_path.parent.mkdir(parents=True)
        parquet_path.touch()

    with pytest.raises(HermesTpx3PreflightError):
        plan_unpacking(analysis)


def test_plan_rejects_summary_with_missing_parquet_file(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "incomplete.tpx3")
    raw_file = analysis.tpx3_files[0]
    summary_path = derive_summary_path(analysis, raw_file)
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(
        _summary(raw_file.path.stem, pixel_rows=1).model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(HermesTpx3PreflightError, match="missing Parquet file"):
        plan_unpacking(analysis)


def test_plan_rejects_duplicate_raw_filename_stems(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "first.tpx3", "second.tpx3")
    duplicate = tmp_path / "other/first.tpx3"
    duplicate.parent.mkdir()
    duplicate.touch()
    analysis = analysis.model_copy(
        update={
            "tpx3_files": [
                analysis.tpx3_files[0],
                FileReference(path=duplicate),
            ]
        }
    )

    with pytest.raises(HermesTpx3PreflightError, match="stems must be unique"):
        plan_unpacking(analysis)


def test_run_marks_analysis_only_state_running_through_state_manager(
    tmp_path: Path,
) -> None:
    analysis = _analysis(tmp_path, "first.tpx3", "second.tpx3")
    state_logger = CapturingStateLogger()
    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=state_logger,
    )

    files_to_run = run_hermes_analysis(manager)

    assert [raw.path.name for raw in files_to_run] == [
        "first.tpx3",
        "second.tpx3",
    ]
    result = manager.get_state().analysis.results.unpacking
    assert result.status == "running"
    assert result.started_at is not None
    assert result.finished_at is None
    assert state_logger.changes[-1].path == "analysis.results"
    assert state_logger.changes[-1].origin == "trusted_workflow"
    assert state_logger.changes[-1].proposer == "tpx3_spidr_unpacking"
    assert state_logger.changes[-1].status == "applied"


def test_run_with_only_completed_files_does_not_mark_running(
    tmp_path: Path,
) -> None:
    analysis = _analysis(tmp_path, "completed.tpx3")
    _save_completed_files(analysis, analysis.tpx3_files[0])
    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=CapturingStateLogger(),
    )

    assert run_hermes_analysis(manager) == []
    assert manager.get_state().analysis.results.unpacking.status == "planned"


def test_run_rejects_non_hermes_analysis(tmp_path: Path) -> None:
    empir = EmpirAnalysisState.model_construct(mode="empir")
    manager = StateManager(_record(tmp_path, empir), state_logger=CapturingStateLogger())

    with pytest.raises(HermesAnalysisError, match="not HERMES"):
        run_hermes_analysis(manager)


def test_disabled_bypass_leaves_pending_change_before_process_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis(tmp_path, "first.tpx3")
    state_logger = CapturingStateLogger()
    manager = StateManager(
        _record(tmp_path, analysis),
        state_logger=state_logger,
    )
    process_called = False

    def unexpected_process(*args: object, **kwargs: object) -> None:
        nonlocal process_called
        process_called = True

    monkeypatch.setattr(subprocess, "run", unexpected_process)

    with pytest.raises(ChangeApprovalError, match="requires approval"):
        run_hermes_analysis(manager)

    assert process_called is False
    assert manager.get_state().analysis.results.unpacking.status == "planned"
    pending = manager.list_pending_changes()
    assert len(pending) == 1
    assert pending[0].path == "analysis.results"
    assert pending[0].origin == "trusted_workflow"
    assert pending[0].proposer == "tpx3_spidr_unpacking"
