from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from hermes.mcp.server import RunStatusRequest, report_run_status

_PROCESS = 7


def _log_line(
    level: str,
    message: str,
    event_type: str,
    *,
    process: int = _PROCESS,
    time: float = 1_000.0,
    **extra: object,
) -> dict:
    """One line as HERMES's JSON-lines log files write it."""
    number = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}[level]
    return {
        "text": f"2026-10-08 00:00:00.000 | {level:<8} | hermes - {message}\n",
        "record": {
            "level": {"name": level, "no": number},
            "message": message,
            "extra": {"domain": "analysis", "event_type": event_type, **extra},
            "process": {"id": process, "name": "MainProcess"},
            "time": {"repr": "2026-10-08 00:00:00", "timestamp": time},
        },
    }


def _write_lines(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")


def _write_summary(path: Path, section: str, **values: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({section: values}), encoding="utf-8")


def _write_outputs(analysis: Path, folder: str, names: list[str]) -> None:
    (analysis / folder).mkdir(parents=True, exist_ok=True)
    for name in names:
        (analysis / folder / name).write_bytes(b"parquet")


def _stage_line(stage: str, file: str, status: str = "success") -> dict:
    return {"event": "stage_completed", "stage": stage, "file": file, "status": status}


def _write_workflow_log(run: Path, stages: list[str], lines: list[dict]) -> None:
    closing = {"event": "workflow_completed", "stages": stages}
    if any(line.get("status") == "failed" for line in lines):
        closing = {"event": "workflow_failed", "stages": stages}
    _write_lines(
        run / "logs" / "HERMES-workflow.jsonl",
        [
            {"event": "HERMES_record_initialized", "record": "HERMES_record.yaml"},
            {"event": "workflow_initialized", "stages": stages},
            *lines,
            closing,
        ],
    )
    # The workflow log is written after every other log line of the run.
    os.utime(run / "logs" / "HERMES-workflow.jsonl", (2_000, 2_000))


@pytest.fixture
def finished_run(tmp_path: Path) -> Path:
    """A run that acquired two raw files and took both through every stage."""
    run = tmp_path / "run-1"
    analysis = run / "analysis"
    summaries = analysis / "logs"
    for raw in ("a", "b"):
        (run / "raw").mkdir(parents=True, exist_ok=True)
        (run / "raw" / f"{raw}.tpx3").write_bytes(b"raw")
        _write_summary(
            summaries / "unpacking" / f"{raw}_unpacker_summary.json",
            "unpacking",
            warnings=[f"Unknown SPIDR control at chip 0, chunk {n}" for n in range(3)],
            errors=[],
        )
        _write_summary(
            summaries
            / "photon_reconstruction"
            / f"{raw}_chip_0_photon_reconstruction_summary_00000.json",
            "reconstruction",
            warnings=[],
            errors=[],
        )
        _write_summary(
            summaries
            / "event_reconstruction"
            / f"{raw}_event_reconstruction_summary.json",
            "reconstruction",
            warnings=[],
            errors=[],
        )
    _write_outputs(
        analysis,
        "pixel_hits",
        ["a_chip_0_pixels_00000.parquet", "b_chip_0_pixels_00000.parquet"],
    )
    _write_outputs(analysis, "tdc_triggers", ["a_tdc.parquet", "b_tdc.parquet"])
    _write_outputs(
        analysis,
        "photons",
        ["a_chip_0_photon_00000.parquet", "b_chip_0_photon_00000.parquet"],
    )
    _write_outputs(
        analysis,
        "events",
        ["a_event_candidates.parquet", "b_event_candidates.parquet"],
    )
    (run / "HERMES_record.yaml").write_text(
        yaml.safe_dump(
            {
                "acquisition": {
                    "status": "completed",
                    "result": {
                        "stop_reason": "completed",
                        "frames": 2,
                        "dropped_frames": 0,
                        "warnings": [],
                        "errors": [],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    _write_lines(
        run / "logs" / "analysis.jsonl",
        [_log_line("INFO", "Unpacked raw/a.tpx3", "analysis.tpx3_unpacking.completed")],
    )
    _write_workflow_log(
        run,
        ["acquisition", "unpacking", "reconstruction", "event_reconstruction"],
        [
            {"event": "stage_completed", "stage": "acquisition", "status": "success"},
            *[_stage_line("unpacking", f"raw/{raw}.tpx3") for raw in ("a", "b")],
            *[
                _stage_line(
                    "reconstruction",
                    f"analysis/pixel_hits/{raw}_chip_0_pixels_00000.parquet",
                )
                for raw in ("a", "b")
            ],
            *[
                _stage_line(
                    "event_reconstruction",
                    f"analysis/events/{raw}_event_candidates.parquet",
                )
                for raw in ("a", "b")
            ],
        ],
    )
    return run


def _report(run: Path):
    return report_run_status(RunStatusRequest(run_directory=run))


def test_a_finished_run(finished_run: Path) -> None:
    result = _report(finished_run)

    assert result.run_directory == finished_run.resolve()
    assert result.outcome == "completed"
    assert result.acquisition is not None
    assert result.acquisition.status == "completed"
    assert result.acquisition.frames == 2
    assert result.acquisition.dropped_frames == 0
    assert [
        (stage.stage, stage.succeeded, stage.failed, stage.not_run, stage.parquet_files)
        for stage in result.stages
    ] == [
        ("unpacking", 2, 0, 0, 4),
        ("photon_reconstruction", 2, 0, 0, 2),
        ("event_reconstruction", 2, 0, 0, 2),
    ]
    assert result.problem_files == []
    assert result.errors == []
    # Six summary warnings that differ only in their numbers are one kind.
    assert len(result.warnings) == 1
    assert result.warnings[0].source == "unpacking summaries"
    assert result.warnings[0].count == 6
    assert result.message.startswith("The run ended: completed.")
    assert "Acquisition: completed (completed), 2 frame(s), 0 dropped." in (
        result.message
    )
    assert "unpacking: 2 succeeded." in result.message


def test_a_run_with_one_failed_file(finished_run: Path) -> None:
    # junk.tpx3 failed before the unpacker wrote its summary, so the error text
    # is only in analysis.jsonl. Its later stages were never run.
    (finished_run / "raw" / "junk.tpx3").write_bytes(b"junk")
    _write_lines(
        finished_run / "logs" / "analysis.jsonl",
        [
            _log_line(
                "ERROR",
                "Unpacking raw/junk.tpx3 failed: summary path is not a regular "
                "file\nstderr: Invalid TPX3 signature at chunk 0",
                "analysis.tpx3_unpacking.failed",
                raw_tpx3_file="raw/junk.tpx3",
            ),
        ],
    )
    log = finished_run / "logs" / "HERMES-workflow.jsonl"
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    log.unlink()
    _write_workflow_log(
        finished_run,
        lines[1]["stages"],
        [*lines[2:-1], _stage_line("unpacking", "raw/junk.tpx3", "failed")],
    )

    result = _report(finished_run)

    assert result.outcome == "failed"
    unpacking = result.stages[0]
    assert (unpacking.succeeded, unpacking.failed) == (2, 1)
    assert [stage.not_run for stage in result.stages] == [0, 0, 0]
    assert len(result.problem_files) == 1
    problem = result.problem_files[0]
    assert (problem.stage, problem.file, problem.status) == (
        "unpacking",
        "junk.tpx3",
        "failed",
    )
    assert problem.error_count == 1
    assert "Invalid TPX3 signature at chunk 0" in problem.errors[0]
    # The file's error is listed with the file, not again with the run's errors.
    assert result.errors == []
    assert "unpacking: 2 succeeded, 1 failed." in result.message
    assert "1 file(s) failed" in result.message


def test_a_stage_that_was_never_reached(finished_run: Path) -> None:
    log = finished_run / "logs" / "HERMES-workflow.jsonl"
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    log.unlink()
    without_b_events = [line for line in lines[2:-1] if "b_event" not in str(line)]
    _write_workflow_log(finished_run, lines[1]["stages"], without_b_events)

    result = _report(finished_run)

    events = result.stages[2]
    assert (events.succeeded, events.not_run) == (1, 1)
    assert [(p.stage, p.file, p.status) for p in result.problem_files] == [
        ("event_reconstruction", "b.tpx3", "not run")
    ]


def test_a_run_that_has_not_finished(tmp_path: Path) -> None:
    # Ctrl-C or a crash, or a run still going: no workflow log or record yet,
    # only summaries, logs and files.
    run = tmp_path / "run-1"
    summaries = run / "analysis" / "logs"
    for raw in ("a", "b", "c"):
        (run / "raw").mkdir(parents=True, exist_ok=True)
        (run / "raw" / f"{raw}.tpx3").write_bytes(b"raw")
    _write_summary(
        summaries / "unpacking" / "a_unpacker_summary.json",
        "unpacking",
        warnings=[],
        errors=[],
    )
    _write_summary(
        summaries
        / "photon_reconstruction"
        / "a_chip_0_photon_reconstruction_summary_00000.json",
        "reconstruction",
        warnings=[],
        errors=[],
    )
    (summaries / "unpacking" / "b_unpacker_summary.json").write_text(
        '{"unpacking": ', encoding="utf-8"
    )
    _write_lines(
        run / "logs" / "acquisition.serval.jsonl",
        [
            _log_line(
                "INFO",
                "Measurement running: 3 frames",
                "acquisition.serval.measurement_progress",
                status="DA_RECORDING",
                frames=3,
                dropped_frames=0,
            ),
        ],
    )

    result = _report(run)

    assert result.outcome == "not finished"
    assert result.acquisition is not None
    assert result.acquisition.status == "running"
    assert result.acquisition.frames == 3
    assert [
        (stage.stage, stage.succeeded, stage.not_run) for stage in result.stages
    ] == [("unpacking", 1, 2), ("photon_reconstruction", 1, 0)]
    # Files still waiting to be unpacked are not problems yet.
    assert result.problem_files == []
    assert result.message.startswith("The run has not finished")
    assert "Acquisition: running, 3 frame(s), 0 dropped." in result.message


def test_a_run_going_on_files_outside_the_run_folder(tmp_path: Path) -> None:
    # A config from create_analysis_config lists .tpx3 files in the data
    # folder, not the run folder. The config the run started with, logged to
    # state.jsonl, names them and the stages to run.
    data = tmp_path / "data"
    data.mkdir()
    for raw in ("a", "b", "c"):
        (data / f"{raw}.tpx3").write_bytes(b"raw")
    run = data / "run-1"
    _write_summary(
        run / "analysis" / "logs" / "unpacking" / "a_unpacker_summary.json",
        "unpacking",
        warnings=[],
        errors=[],
    )
    config = {
        "analysis": {
            "unpacking": {
                "tpx3_files": [{"path": str(data / f"{raw}.tpx3")} for raw in "abc"]
            },
            "photon_reconstruction": {"pixel_files": "auto"},
            "event_reconstruction": {"photon_parquet_files": "auto"},
        }
    }
    _write_lines(
        run / "logs" / "state.jsonl",
        [
            _log_line(
                "INFO",
                "Initialized HERMES Record for measurement demo, run run-1",
                "state.initial_record",
                record=config,
            )
        ],
    )

    result = _report(run)

    assert result.outcome == "not finished"
    assert [
        (stage.stage, stage.succeeded, stage.not_run) for stage in result.stages
    ] == [
        ("unpacking", 1, 2),
        ("photon_reconstruction", 0, 1),
        ("event_reconstruction", 0, 0),
    ]
    assert result.problem_files == []


def test_a_new_run_in_an_old_run_folder_has_not_finished(finished_run: Path) -> None:
    # The workflow log is from the run before; a new process is now logging.
    _write_lines(
        finished_run / "logs" / "analysis.jsonl",
        [
            _log_line(
                "INFO",
                "Unpacked raw/a.tpx3",
                "analysis.tpx3_unpacking.completed",
                process=_PROCESS + 1,
                time=3_000.0,
            )
        ],
    )

    result = _report(finished_run)

    assert result.outcome == "not finished"


def test_a_new_run_leaves_out_the_errors_of_the_run_before(
    finished_run: Path,
) -> None:
    # The run before logged an error; the new run has so far logged only one
    # acquisition line and nothing to analysis.jsonl.
    _write_lines(
        finished_run / "logs" / "analysis.jsonl",
        [
            _log_line(
                "ERROR",
                "Unpacking raw/junk.tpx3 failed: Invalid TPX3 signature",
                "analysis.tpx3_unpacking.failed",
                raw_tpx3_file="raw/junk.tpx3",
            )
        ],
    )
    _write_lines(
        finished_run / "logs" / "acquisition.serval.jsonl",
        [
            _log_line(
                "INFO",
                "Measurement running: 1 frames",
                "acquisition.serval.measurement_progress",
                process=_PROCESS + 1,
                time=3_000.0,
                frames=1,
                dropped_frames=0,
            )
        ],
    )

    result = _report(finished_run)

    assert result.outcome == "not finished"
    assert result.acquisition is not None
    assert result.acquisition.frames == 1
    assert "junk.tpx3" not in [problem.file for problem in result.problem_files]
    assert result.errors == []


def test_repeated_warnings_are_shown_once_with_a_count(finished_run: Path) -> None:
    raw_files = [f"raw/{n:06d}.tpx3" for n in range(12)]
    _write_lines(
        finished_run / "logs" / "analysis.jsonl",
        [
            # An earlier run in the same folder, which is left out.
            _log_line(
                "WARNING",
                "Skipped raw/old.tpx3: valid outputs already exist",
                "analysis.tpx3_unpacking.skipped",
                process=_PROCESS - 1,
                raw_tpx3_file="raw/old.tpx3",
            ),
            *[
                _log_line(
                    "WARNING",
                    f"Skipped {raw}: valid outputs already exist",
                    "analysis.tpx3_unpacking.skipped",
                    raw_tpx3_file=raw,
                )
                for raw in raw_files
            ],
            # A warning that names three files whose names differ in more
            # than their numbers.
            *[
                _log_line(
                    "WARNING",
                    f"raw/{now}.tpx3: the last global timestamp of "
                    f"raw/{earlier}.tpx3 is 20.0 s before the next one, in "
                    f"raw/{later}.tpx3",
                    "analysis.tpx3_unpacking.earlier_timestamp_too_far",
                    raw_tpx3_file=f"raw/{now}.tpx3",
                    earlier_tpx3_file=f"raw/{earlier}.tpx3",
                    later_tpx3_file=f"raw/{later}.tpx3",
                )
                for earlier, now, later in (
                    ("iron", "lead", "tin"),
                    ("open", "beam", "dark"),
                )
            ],
        ],
    )

    result = _report(finished_run)

    logged = [w for w in result.warnings if w.source == "analysis.jsonl"]
    assert [(w.text, w.count) for w in logged] == [
        ("Skipped raw/000000.tpx3: valid outputs already exist", 12),
        (
            "raw/lead.tpx3: the last global timestamp of raw/iron.tpx3 is "
            "20.0 s before the next one, in raw/tin.tpx3",
            2,
        ),
    ]


def test_a_summary_with_errors_marks_its_file_failed(tmp_path: Path) -> None:
    run = tmp_path / "run-1"
    _write_summary(
        run / "analysis" / "logs" / "unpacking" / "a_unpacker_summary.json",
        "unpacking",
        warnings=[],
        errors=["Truncated chunk at byte 4096"],
    )

    result = _report(run)

    assert result.stages[0].failed == 1
    assert result.problem_files[0].file == "a.tpx3"
    assert result.problem_files[0].errors == ["Truncated chunk at byte 4096"]
    assert "There is no logs/ folder" in result.message


def test_an_acquisition_with_no_dropped_frame_count(finished_run: Path) -> None:
    record = finished_run / "HERMES_record.yaml"
    saved = yaml.safe_load(record.read_text(encoding="utf-8"))
    saved["acquisition"]["result"]["dropped_frames"] = None
    record.write_text(yaml.safe_dump(saved), encoding="utf-8")

    result = _report(finished_run)

    assert "Acquisition: completed (completed), 2 frame(s)." in result.message


def test_a_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        _report(tmp_path / "missing")


def test_a_folder_that_is_not_a_run(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no HERMES run found"):
        _report(tmp_path)
