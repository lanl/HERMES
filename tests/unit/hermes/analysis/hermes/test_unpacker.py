from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from loguru import logger

from hermes.analysis.hermes.run import HermesAnalysisError, run_hermes_analysis
from hermes.analysis.hermes.unpacker import (
    HermesTpx3ExecutionError,
    HermesTpx3OutputError,
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
from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)


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
        pq.write_table(pa.table({"value": [1]}), parquet_path)
    summary_path = derive_summary_path(analysis, raw_file)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary.model_dump_json(), encoding="utf-8")


def _write_fake_unpacker(executable: Path) -> None:
    script = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import json
        import sys
        from pathlib import Path

        import pyarrow as pa
        import pyarrow.parquet as pq

        raw_file = Path(sys.argv[1])
        analysis_directory = Path(sys.argv[2])
        raw_stem = raw_file.stem
        mode = raw_file.read_text(encoding="utf-8").strip() or "success"

        print("o" * 5000)
        print("e" * 5000, file=sys.stderr)
        if mode == "nonzero":
            raise SystemExit(7)

        summary_path = (
            analysis_directory
            / "logs"
            / f"{{raw_stem}}-unpacker-summary.json"
        )
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "missing_summary":
            raise SystemExit(0)
        if mode == "invalid_summary":
            summary_path.write_text("not JSON", encoding="utf-8")
            raise SystemExit(0)

        if mode == "unsafe_path":
            relative_parquet = Path("../outside.parquet")
        elif mode == "bad_prefix":
            relative_parquet = Path("pixelHits/other-chip-0-part-00000.parquet")
        elif mode == "bad_part":
            relative_parquet = Path(
                f"pixelHits/{{raw_stem}}-chip-0-part-00001.parquet"
            )
        else:
            relative_parquet = Path(
                f"pixelHits/{{raw_stem}}-chip-0-part-00000.parquet"
            )

        parquet_path = analysis_directory / relative_parquet
        if mode not in {{"missing_parquet", "unsafe_path"}}:
            parquet_path.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(pa.table({{"value": [1]}}), parquet_path)

        if mode == "unexpected_parquet":
            unexpected = (
                analysis_directory
                / "pixelHits"
                / f"{{raw_stem}}-chip-0-part-00001.parquet"
            )
            pq.write_table(pa.table({{"value": [2]}}), unexpected)

        row_count = 2 if mode == "row_mismatch" else 1
        summary = {{
            "unpacking": {{
                "chunks_read": 1,
                "packets_read": 1,
                "decoded_pixel_hits": 1,
                "decoded_tdc_triggers": 0,
                "decoded_global_timestamps": 0,
                "decoded_spidr_control_packets": 0,
                "decoded_tpx3_control_packets": 0,
                "decoded_unknown_packets": 0,
                "warnings": ["test warning"],
                "errors": (
                    ["test unpacking error"]
                    if mode == "unpacking_errors"
                    else []
                ),
            }},
            "timestamp_processing": {{
                "anchors": {{
                    "total": 0,
                    "unpaired_low": 0,
                    "unpaired_high": 0,
                    "warnings": [],
                }},
                "epoch_assignment": {{
                    "pixels_assigned": 1,
                    "tdc_triggers_assigned": 0,
                    "controls_assigned": 0,
                    "ambiguous_timestamps": 0,
                    "unresolved_timestamps": 0,
                    "used_fallback": False,
                    "warnings": [],
                }},
            }},
            "sorting": {{
                "method": "in_memory",
                "memory_budget_bytes": 1000,
                "estimated_memory_bytes": 100,
                "temporary_runs_created": 0,
            }},
            "parquet": {{
                "pixel_hits": {{
                    "row_count": row_count,
                    "files": [str(relative_parquet)],
                }},
                "tdc_triggers": {{"row_count": 0, "files": []}},
                "global_timestamps": {{"row_count": 0, "files": []}},
                "control_packets": {{"row_count": 0, "files": []}},
                "unknown_packets": {{"row_count": 0, "files": []}},
                "errors": (
                    ["test Parquet error"] if mode == "summary_errors" else []
                ),
            }},
            "processing_times_seconds": {{
                "unpacking": 0.1,
                "epoch_assignment": 0.1,
                "conversion": 0.1,
                "sorting": 0.1,
                "parquet_writing": 0.1,
                "total": 0.5,
            }},
        }}
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        """
    )
    executable.write_text(script, encoding="utf-8")
    executable.chmod(0o755)


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
        "hermes.analysis.hermes.run.execute_unpacker",
        lambda analysis, raw_file: _summary(raw_file.path.stem),
    )

    files_to_run = run_hermes_analysis(manager)

    assert [raw.path.name for raw in files_to_run] == [
        "first.tpx3",
        "second.tpx3",
    ]
    result = manager.get_state().analysis.results.unpacking
    assert result.status == "completed"
    assert result.started_at is not None
    assert result.finished_at is not None
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
    result = manager.get_state().analysis.results.unpacking
    assert result.status == "completed"
    assert result.started_at is None
    assert result.finished_at is not None


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


def test_run_executes_fake_unpacker_logs_details_and_round_trips_yaml(
    tmp_path: Path,
) -> None:
    analysis = _analysis(tmp_path, "success.tpx3")
    _write_fake_unpacker(analysis.unpacker_program.executable_path)
    state_logger = CapturingStateLogger()
    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=state_logger,
    )
    records: list[dict[str, Any]] = []
    sink_id = logger.add(
        lambda message: records.append(message.record),
        filter=lambda record: record["extra"].get("domain") == "analysis",
    )
    try:
        files_run = run_hermes_analysis(manager)
    finally:
        logger.remove(sink_id)

    assert files_run == analysis.tpx3_files
    result = manager.get_state().analysis.results.unpacking
    assert result.status == "completed"
    assert result.started_at is not None
    assert result.finished_at is not None

    started = next(
        record
        for record in records
        if record["extra"].get("event_type")
        == "analysis.tpx3_unpacking.started"
    )
    assert started["extra"]["command"] == derive_unpacker_command(
        analysis,
        analysis.tpx3_files[0],
    )
    completed = next(
        record
        for record in records
        if record["extra"].get("summary") is not None
    )
    assert completed["extra"]["exit_code"] == 0
    assert len(completed["extra"]["stdout_excerpt"]) == 4_000
    assert len(completed["extra"]["stderr_excerpt"]) == 4_000
    assert completed["extra"]["summary"]["unpacking"]["decoded_pixel_hits"] == 1
    assert completed["extra"]["summary"]["sorting"]["method"] == "in_memory"
    assert completed["extra"]["summary"]["parquet"]["pixel_hits"][
        "row_count"
    ] == 1

    record_path = tmp_path / "hermes-record.yaml"
    save_hermes_record_to_yaml(manager.get_state(), record_path)
    loaded = load_hermes_record_from_yaml(record_path)
    assert loaded == manager.get_state()


def test_run_processes_multiple_inputs_and_then_skips_them(
    tmp_path: Path,
) -> None:
    analysis = _analysis(tmp_path, "first.tpx3", "second.tpx3")
    _write_fake_unpacker(analysis.unpacker_program.executable_path)
    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=CapturingStateLogger(),
    )

    assert run_hermes_analysis(manager) == analysis.tpx3_files
    for raw_file in analysis.tpx3_files:
        assert (
            analysis.analysis_directory
            / "pixelHits"
            / f"{raw_file.path.stem}-chip-0-part-00000.parquet"
        ).is_file()

    records: list[dict[str, Any]] = []
    sink_id = logger.add(
        lambda message: records.append(message.record),
        filter=lambda record: record["extra"].get("domain") == "analysis",
    )
    try:
        assert run_hermes_analysis(manager) == []
    finally:
        logger.remove(sink_id)

    skipped = [
        record
        for record in records
        if record["extra"].get("event_type")
        == "analysis.tpx3_unpacking.skipped"
    ]
    assert [Path(record["extra"]["raw_tpx3_file"]).name for record in skipped] == [
        "first.tpx3",
        "second.tpx3",
    ]


@pytest.mark.parametrize(
    ("mode", "expected_exception", "message"),
    [
        ("nonzero", HermesTpx3ExecutionError, "code 7"),
        ("missing_summary", HermesTpx3PreflightError, "summary path"),
        ("invalid_summary", HermesTpx3PreflightError, "invalid summary"),
        ("summary_errors", HermesTpx3OutputError, "reports"),
        ("unpacking_errors", HermesTpx3OutputError, "reports"),
        ("unsafe_path", HermesTpx3PreflightError, "invalid summary"),
        ("missing_parquet", HermesTpx3OutputError, "missing Parquet"),
        ("bad_prefix", HermesTpx3OutputError, "unexpected Parquet filename"),
        ("bad_part", HermesTpx3OutputError, "part numbers"),
        ("unexpected_parquet", HermesTpx3OutputError, "does not match"),
        ("row_mismatch", HermesTpx3OutputError, "row count mismatch"),
    ],
)
def test_run_saves_failed_state_before_raising_for_output_failures(
    tmp_path: Path,
    mode: str,
    expected_exception: type[Exception],
    message: str,
) -> None:
    analysis = _analysis(tmp_path, f"{mode}.tpx3")
    analysis.tpx3_files[0].path.write_text(mode, encoding="utf-8")
    _write_fake_unpacker(analysis.unpacker_program.executable_path)
    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=CapturingStateLogger(),
    )

    records: list[dict[str, Any]] = []
    sink_id = logger.add(
        lambda log_message: records.append(log_message.record),
        filter=lambda record: record["extra"].get("domain") == "analysis",
    )
    try:
        with pytest.raises(expected_exception, match=message):
            run_hermes_analysis(manager)
    finally:
        logger.remove(sink_id)

    result = manager.get_state().analysis.results.unpacking
    assert result.status == "failed"
    assert result.started_at is not None
    assert result.finished_at is not None
    failures = [
        record
        for record in records
        if record["extra"].get("event_type")
        == "analysis.tpx3_unpacking.failed"
    ]
    assert failures
    if mode == "nonzero":
        process_failure = next(
            record for record in failures if record["extra"].get("exit_code") == 7
        )
        assert len(process_failure["extra"]["stdout_excerpt"]) == 4_000
        assert len(process_failure["extra"]["stderr_excerpt"]) == 4_000
    if mode == "summary_errors":
        summary_failure = next(
            record for record in failures if record["extra"].get("summary")
        )
        assert summary_failure["extra"]["summary"]["parquet"]["errors"] == [
            "test Parquet error"
        ]


def test_run_saves_failed_state_for_preflight_failure(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "invalid-existing.tpx3")
    summary_path = derive_summary_path(analysis, analysis.tpx3_files[0])
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text("not JSON", encoding="utf-8")
    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=CapturingStateLogger(),
    )

    with pytest.raises(HermesTpx3PreflightError, match="invalid summary"):
        run_hermes_analysis(manager)

    result = manager.get_state().analysis.results.unpacking
    assert result.status == "failed"
    assert result.started_at is None
    assert result.finished_at is not None
