from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from loguru import logger

from hermes.runner.analysis.executables import single_thread_environment
from hermes.runner.analysis.hermes import run as run_module
from hermes.runner.analysis.hermes import unpacker as unpacker_module
from hermes.runner.analysis.hermes.run import HermesAnalysisError, run_hermes_analysis
from hermes.runner.analysis.hermes.unpacker import (
    HermesTpx3Error,
    HermesTpx3PreflightError,
    check_previous_unpacked_file,
    derive_batch_unpacker_command,
    derive_summary_path,
    derive_unpacker_command,
    execute_unpacker,
    execute_unpacker_batch,
    resolve_tpx3_files,
    validate_program_and_inputs,
    _warn_if_timestamps_unanchored,
)
from hermes.state.models.analysis.empir import EmpirAnalysisState
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3SpidrSummary,
    Tpx3Unpacking,
    Tpx3UnpackingRuntimeOptions,
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
    executable.chmod(0o755)

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
    number_of_beats: int = 0,
    failed: int = 0,
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
                    "number_of_beats": number_of_beats,
                },
                "time_adjustments": {
                    "pixel_packets": pixel_rows,
                    "tdc_packets": 0,
                    "control_packets": 0,
                    "failed": failed,
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
        # Validation confirms the listed file exists but never opens it, so the
        # placeholder does not need to be a real Parquet file.
        parquet_path.write_bytes(b"placeholder, not a real parquet file")
    summary_path = derive_summary_path(analysis_root, raw_file)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary.model_dump_json(), encoding="utf-8")


def _capture_unanchored_warnings() -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    sink_id = logger.add(
        lambda message: records.append(message.record),
        filter=lambda record: record["extra"].get("event_type")
        == "analysis.tpx3_unpacking.timestamps_unanchored",
    )
    return records, sink_id


def test_unpacking_warns_when_timestamps_have_no_global_anchor(
    tmp_path: Path,
) -> None:
    analysis_root = _analysis_root(tmp_path)
    raw_file = FileReference(path=tmp_path / "rawTpx3" / "no_beats.tpx3")
    # No global timestamps in the file, so every wrapped counter is left
    # unresolved: this is the SoPhy/GlobalTimestampInterval-off signature.
    summary = _summary(
        analysis_root, "no_beats", pixel_rows=3, number_of_beats=0, failed=3
    )

    records, sink_id = _capture_unanchored_warnings()
    try:
        _warn_if_timestamps_unanchored(raw_file, summary)
    finally:
        logger.remove(sink_id)

    assert len(records) == 1
    warning = records[0]
    assert warning["level"].name == "WARNING"
    assert warning["extra"]["failed"] == 3
    assert warning["extra"]["beats"] == 0
    assert "GlobalTimestampInterval" in warning["message"]


def test_unpacking_does_not_warn_when_all_timestamps_anchored(
    tmp_path: Path,
) -> None:
    analysis_root = _analysis_root(tmp_path)
    raw_file = FileReference(path=tmp_path / "rawTpx3" / "ok.tpx3")
    summary = _summary(
        analysis_root, "ok", pixel_rows=3, number_of_beats=8, failed=0
    )

    records, sink_id = _capture_unanchored_warnings()
    try:
        _warn_if_timestamps_unanchored(raw_file, summary)
    finally:
        logger.remove(sink_id)

    assert records == []


def test_unpacking_warns_per_chip_when_some_beats_present(tmp_path: Path) -> None:
    analysis_root = _analysis_root(tmp_path)
    raw_file = FileReference(path=tmp_path / "rawTpx3" / "partial.tpx3")
    # The file has global timestamps (beats > 0) yet some counters were still
    # unresolved: on a multi-chip detector a chip can lack its own anchor even
    # though others have them. The hint must not blame acquisition here.
    summary = _summary(
        analysis_root, "partial", pixel_rows=5, number_of_beats=4, failed=2
    )

    records, sink_id = _capture_unanchored_warnings()
    try:
        _warn_if_timestamps_unanchored(raw_file, summary)
    finally:
        logger.remove(sink_id)

    assert len(records) == 1
    warning = records[0]
    assert warning["extra"]["failed"] == 2
    assert warning["extra"]["beats"] == 4
    # With anchors present, do not tell the operator to enable it during
    # acquisition; explain the per-chip cause instead.
    assert "GlobalTimestampInterval" not in warning["message"]
    assert "not for every chip" in warning["message"]


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


def test_derives_batch_command_uses_input_list(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "first.tpx3", "second.tpx3")
    analysis_root = _analysis_root(tmp_path)
    list_path = tmp_path / "batch.txt"

    # A batch run passes the shared list file with --input-list; every other
    # option is per-run, so it matches the single-file command.
    assert derive_batch_unpacker_command(
        analysis, analysis_root, list_path, _measurement_info()
    ) == [
        str(analysis.unpacking.program.executable_path),
        "--input-list",
        str(list_path),
        "--output",
        str(analysis_root),
        "--measurement-id",
        "stage-3",
        "--run",
        "test-run",
    ]


def test_execute_unpacker_batch_reports_per_file_result_from_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis(tmp_path, "kept.tpx3", "gone.tpx3")
    analysis_root = _analysis_root(tmp_path)
    kept, gone = analysis.unpacking.tpx3_files
    # Only "kept" ends up with a valid summary and Parquet output on disk; "gone"
    # is a file the process never finished, so it has no summary.
    _save_completed_files(analysis_root, kept, pixel_rows=1)

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.unpacker.subprocess.run", fake_run
    )

    # Each file's result comes from its own summary, not the shared exit code:
    # "kept" is unpacked, "gone" is failed, in the given order.
    results = execute_unpacker_batch(
        analysis, analysis_root, [kept, gone], _measurement_info()
    )

    assert results[0] is not None
    assert results[1] is None


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


def test_extra_unlisted_parquet_file_does_not_fail_validation(
    tmp_path: Path,
) -> None:
    analysis = _analysis(tmp_path, "completed.tpx3")
    analysis_root = _analysis_root(tmp_path)
    raw_file = analysis.unpacking.tpx3_files[0]
    _save_completed_files(analysis_root, raw_file, pixel_rows=1)
    # A leftover Parquet file the summary does not list (for example from an
    # earlier partial run) no longer fails validation: HERMES checks only the
    # files its summary lists, not the whole output directory.
    orphan = (
        analysis_root
        / "pixel_hits"
        / f"{raw_file.path.stem}_chip_0_pixels_00001.parquet"
    )
    orphan.touch()

    assert check_previous_unpacked_file(analysis_root, raw_file)


def test_resume_validation_does_not_open_parquet_footer(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "completed.tpx3")
    analysis_root = _analysis_root(tmp_path)
    raw_file = analysis.unpacking.tpx3_files[0]
    _save_completed_files(analysis_root, raw_file, pixel_rows=1)

    # The listed pixel file exists but is not a real Parquet file: it lacks the
    # "PAR1" magic bytes, so opening its footer would fail. Validation trusts the
    # summary and only checks existence, so the raw file still counts as unpacked.
    listed_file = _summary(
        analysis_root, raw_file.path.stem, pixel_rows=1
    ).output_parquet.pixel_data.files[0]
    assert listed_file.is_file()
    assert not listed_file.read_bytes().startswith(b"PAR1")

    assert check_previous_unpacked_file(analysis_root, raw_file)


def test_unpacker_subprocess_runs_with_single_thread_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis(tmp_path, "completed.tpx3")
    analysis_root = _analysis_root(tmp_path)
    raw_file = analysis.unpacking.tpx3_files[0]
    # A valid completed state lets validation succeed after the faked process.
    _save_completed_files(analysis_root, raw_file, pixel_rows=1)
    monkeypatch.setenv("HERMES_TEST_MARKER", "present")

    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        captured["env"] = kwargs.get("env")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.unpacker.subprocess.run", fake_run
    )

    execute_unpacker(analysis, analysis_root, raw_file, _measurement_info())

    env = captured["env"]
    assert env is not None
    assert env["OMP_NUM_THREADS"] == "1"
    assert env["ARROW_NUM_THREADS"] == "1"
    assert env["ARROW_IO_THREADS"] == "1"
    # The child still inherits the parent environment.
    assert env["HERMES_TEST_MARKER"] == "present"


def test_single_thread_environment_pins_threads_and_inherits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERMES_TEST_MARKER", "present")
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)

    environment = single_thread_environment()

    assert environment["OMP_NUM_THREADS"] == "1"
    assert environment["ARROW_NUM_THREADS"] == "1"
    assert environment["ARROW_IO_THREADS"] == "1"
    assert environment["HERMES_TEST_MARKER"] == "present"


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
        validate_program_and_inputs(
            analysis, analysis_root, list(analysis.unpacking.tpx3_files)
        )


def _capture_binary_stale_warnings() -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    sink_id = logger.add(
        lambda message: records.append(message.record),
        filter=lambda record: record["extra"].get("event_type")
        == "analysis.tpx3_unpacking.binary_stale",
    )
    return records, sink_id


def _make_cpp_source(tmp_path: Path) -> Path:
    source_directory = tmp_path / "cpp"
    source_file = source_directory / "src" / "unpacker.cpp"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("// unpacker\n", encoding="utf-8")
    return source_directory


def test_preflight_warns_when_binary_older_than_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A binary older than its C++ source is flagged as stale before unpacking."""
    analysis = _analysis(tmp_path, "one.tpx3")
    analysis_root = _analysis_root(tmp_path)
    source_directory = _make_cpp_source(tmp_path)
    binary = analysis.unpacking.program.executable_path
    os.utime(binary, (1000.0, 1000.0))
    os.utime(source_directory / "src" / "unpacker.cpp", (2000.0, 2000.0))
    monkeypatch.setattr(unpacker_module, "_UNPACKER_CPP_SOURCE", source_directory)

    records, sink_id = _capture_binary_stale_warnings()
    try:
        validate_program_and_inputs(
            analysis, analysis_root, list(analysis.unpacking.tpx3_files)
        )
    finally:
        logger.remove(sink_id)

    assert len(records) == 1
    warning = records[0]
    assert warning["level"].name == "WARNING"
    assert "pixi reinstall hermes" in warning["message"]
    assert warning["extra"]["source"].endswith("unpacker.cpp")


def test_preflight_does_not_warn_when_binary_is_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A binary newer than its C++ source raises no staleness warning."""
    analysis = _analysis(tmp_path, "one.tpx3")
    analysis_root = _analysis_root(tmp_path)
    source_directory = _make_cpp_source(tmp_path)
    binary = analysis.unpacking.program.executable_path
    os.utime(source_directory / "src" / "unpacker.cpp", (1000.0, 1000.0))
    os.utime(binary, (2000.0, 2000.0))
    monkeypatch.setattr(unpacker_module, "_UNPACKER_CPP_SOURCE", source_directory)

    records, sink_id = _capture_binary_stale_warnings()
    try:
        validate_program_and_inputs(
            analysis, analysis_root, list(analysis.unpacking.tpx3_files)
        )
    finally:
        logger.remove(sink_id)

    assert records == []


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
    # The runner unpacks in chunks: each call receives a list of raw files and
    # returns one summary per file, in order.
    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.run.execute_unpacker_batch",
        lambda analysis, analysis_root, raw_files, measurement_info, **kwargs: [
            _summary(analysis_root, raw_file.path.stem) for raw_file in raw_files
        ],
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


def test_run_failure_keeps_skipped_and_marks_only_attempted_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis(tmp_path, "done.tpx3", "boom.tpx3")
    _save_completed_files(_analysis_root(tmp_path), analysis.unpacking.tpx3_files[0])
    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=CapturingStateLogger(),
    )

    def failing_batch(
        analysis: Any,
        analysis_root: Path,
        raw_files: list[FileReference],
        measurement_info: MeasurementInfo,
        **kwargs: Any,
    ) -> list[Tpx3SpidrSummary | None]:
        # Batch reports a failed file as a None entry, one per input file,
        # rather than raising; here every attempted file fails.
        return [None for _ in raw_files]

    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.run.execute_unpacker_batch", failing_batch
    )

    # One file failing to unpack no longer aborts the run: the failure is
    # recorded and run_hermes_analysis returns normally with no unpacked files.
    unpacked = run_hermes_analysis(manager)

    assert unpacked == []
    results = {
        result.input_file.path.name: result.status
        for result in manager.get_state().analysis.unpacking.results
    }
    assert results == {"done.tpx3": "skipped", "boom.tpx3": "failed"}


def test_run_continues_unpacking_remaining_files_after_one_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis(tmp_path, "good1.tpx3", "boom.tpx3", "good2.tpx3")
    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=CapturingStateLogger(),
    )

    def batch_unpacker(
        analysis: Any,
        analysis_root: Path,
        raw_files: list[FileReference],
        measurement_info: MeasurementInfo,
        **kwargs: Any,
    ) -> list[Tpx3SpidrSummary | None]:
        # "boom.tpx3" fails (None); the others unpack. This holds however the
        # files are split across chunks.
        return [
            None
            if raw_file.path.name == "boom.tpx3"
            else _summary(analysis_root, raw_file.path.stem)
            for raw_file in raw_files
        ]

    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.run.execute_unpacker_batch", batch_unpacker
    )

    unpacked = run_hermes_analysis(manager)

    # The failing file is skipped over; the other two still unpack and are
    # returned in the original tpx3_files order.
    assert [raw.path.name for raw in unpacked] == ["good1.tpx3", "good2.tpx3"]
    results = {
        result.input_file.path.name: result.status
        for result in manager.get_state().analysis.unpacking.results
    }
    assert results == {
        "good1.tpx3": "completed",
        "boom.tpx3": "failed",
        "good2.tpx3": "completed",
    }


def test_scan_failure_stops_stage_and_records_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis(tmp_path, "done.tpx3", "boom.tpx3")
    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=CapturingStateLogger(),
    )

    def scanning(analysis_root: Path, raw_file: FileReference) -> bool:
        # A corrupt or partial prior summary found during the resume scan stops
        # the whole stage, just as the single-file scan it replaced did.
        if raw_file.path.name == "boom.tpx3":
            raise HermesTpx3PreflightError("invalid prior summary")
        return True

    monkeypatch.setattr(run_module, "check_previous_unpacked_file", scanning)

    with pytest.raises(HermesTpx3Error):
        run_hermes_analysis(manager)

    # Files confirmed already done stay skipped; the file that failed to scan is
    # recorded failed.
    results = {
        result.input_file.path.name: result.status
        for result in manager.get_state().analysis.unpacking.results
    }
    assert results == {"done.tpx3": "skipped", "boom.tpx3": "failed"}


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


def _auto_analysis(tmp_path: Path) -> HermesTpx3AnalysisState:
    return HermesTpx3AnalysisState(
        unpacking=Tpx3Unpacking(
            program=BinaryProgram(
                name="tpx3-spidr-cpp",
                executable_path=tmp_path / "hermes-tpx3-spidr",
            ),
            tpx3_files="auto",
        ),
    )


def test_resolve_tpx3_files_returns_explicit_list_unchanged(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "first.tpx3", "second.tpx3")

    resolved = resolve_tpx3_files(analysis, tmp_path / "rawTpx3")

    assert [f.path for f in resolved] == [
        f.path for f in analysis.unpacking.tpx3_files
    ]


def test_resolve_tpx3_files_globs_raw_directory_for_auto(tmp_path: Path) -> None:
    raw_dir = tmp_path / "rawTpx3"
    raw_dir.mkdir(parents=True)
    (raw_dir / "b.tpx3").touch()
    (raw_dir / "a.tpx3").touch()
    (raw_dir / "notes.txt").touch()

    resolved = resolve_tpx3_files(_auto_analysis(tmp_path), raw_dir)

    # Sorted, and only *.tpx3 files.
    assert [f.path.name for f in resolved] == ["a.tpx3", "b.tpx3"]


def test_resolve_tpx3_files_empty_when_directory_unset_or_missing(
    tmp_path: Path,
) -> None:
    analysis = _auto_analysis(tmp_path)

    assert resolve_tpx3_files(analysis, None) == []
    assert resolve_tpx3_files(analysis, tmp_path / "missing") == []


def test_delete_raw_after_unpack_removes_only_successful_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _analysis(tmp_path, "good.tpx3", "done.tpx3", "bad.tpx3")
    analysis = HermesTpx3AnalysisState(
        unpacking=Tpx3Unpacking(
            program=base.unpacking.program,
            tpx3_files=base.unpacking.tpx3_files,
            runtime_options=Tpx3UnpackingRuntimeOptions(
                delete_raw_after_unpack=True
            ),
        ),
    )
    analysis_root = _analysis_root(tmp_path)
    good, done, bad = analysis.unpacking.tpx3_files
    # "done" already has valid outputs, so it is skipped, not re-unpacked here.
    _save_completed_files(analysis_root, done, pixel_rows=1)

    def fake_execute_unpacker_batch(
        analysis_arg,
        analysis_root_arg,
        raw_files,
        measurement_info,
        *,
        overwrite=False,
    ):
        # "bad" fails (None); "good" unpacks. "done" is skipped before the pool.
        return [
            None
            if raw_file.path == bad.path
            else _summary(analysis_root_arg, raw_file.path.stem)
            for raw_file in raw_files
        ]

    monkeypatch.setattr(
        run_module, "execute_unpacker_batch", fake_execute_unpacker_batch
    )

    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )
    run_hermes_analysis(manager)

    # Only the file this run unpacked without error is deleted; the skipped and
    # the failed raw files stay on disk.
    assert not good.path.exists()
    assert done.path.exists()
    assert bad.path.exists()
