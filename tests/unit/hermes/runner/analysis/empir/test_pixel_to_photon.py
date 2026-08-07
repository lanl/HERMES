"""Tests for EMPIR pixel-to-photon command construction."""

from pathlib import Path

import pytest
from loguru import logger

from hermes.runner.analysis.empir._errors import (
    EmpirExecutionError,
    EmpirOutputError,
    EmpirPreflightError,
)
from hermes.runner.analysis.empir.pixel_to_photon import (
    build_pixel_to_photon_command,
    execute_pixel_to_photon,
)
from hermes.state.models.analysis.empir import (
    EmpirPixelToPhotonRun,
    EmpirPixelToPhotonSettings,
    EmpirPixelToPhotonState,
)
from hermes.state.models.shared_models import BinaryProgram, FileReference
from _fake_program import write_fake_empir_program


def _stage(tmp_path: Path, *, include_tdc1: bool) -> EmpirPixelToPhotonState:
    """Build one pixel-to-photon stage for command tests."""
    return EmpirPixelToPhotonState(
        program=BinaryProgram(
            name="empir-pixel2photon",
            executable_path="empir_pixel2photon_tpx3spidr",
        ),
        settings=EmpirPixelToPhotonSettings(
            spatial_distance_pixels=5,
            time_distance_seconds=500e-9,
            minimum_pixel_count=3,
            include_tdc1=include_tdc1,
        ),
        runs=[
            EmpirPixelToPhotonRun(
                input_tpx3_file=FileReference(path=tmp_path / "raw.tpx3"),
                requested_photon_file=tmp_path / "raw.empirphot",
            )
        ],
    )


def test_build_pixel_to_photon_minimal_command(tmp_path: Path) -> None:
    """Omit the optional TDC1 flag when it is disabled."""
    stage = _stage(tmp_path, include_tdc1=False)
    executable = tmp_path / "bin/empir_pixel2photon_tpx3spidr"

    assert build_pixel_to_photon_command(
        stage, stage.runs[0], executable
    ) == [
        str(executable),
        "-i",
        str(tmp_path / "raw.tpx3"),
        "-o",
        str(tmp_path / "raw.empirphot"),
        "-s",
        "5.0",
        "-t",
        "5e-07",
        "-k",
        "3",
    ]


def test_build_pixel_to_photon_full_command(tmp_path: Path) -> None:
    """Append the standalone TDC1 flag when it is enabled."""
    stage = _stage(tmp_path, include_tdc1=True)
    executable = tmp_path / "bin/empir_pixel2photon_tpx3spidr"

    command = build_pixel_to_photon_command(stage, stage.runs[0], executable)

    assert command[-1] == "-T"
    assert command.count("-T") == 1


def test_execute_pixel_to_photon_records_result_and_logs(tmp_path: Path) -> None:
    """Record verified output, timing, and bounded process text on success."""
    stage = _stage(tmp_path, include_tdc1=True)
    run = stage.runs[0]
    run.input_tpx3_file.path.write_text("success", encoding="utf-8")
    executable = tmp_path / "bin/empir_pixel2photon_tpx3spidr"
    write_fake_empir_program(executable)
    records: list[dict[str, object]] = []
    sink_id = logger.add(lambda message: records.append(message.record))

    try:
        result = execute_pixel_to_photon(stage, run, executable)
    finally:
        logger.remove(sink_id)

    assert result.status == "completed"
    assert result.exit_code == 0
    assert result.elapsed_seconds is not None
    assert result.elapsed_seconds >= 0
    assert result.saved_photon_file is not None
    assert result.saved_photon_file.path == run.requested_photon_file
    events = [
        record["extra"]
        for record in records
        if str(record["extra"].get("event_type", "")).startswith(
            "analysis.empir.pixel_to_photon."
        )
    ]
    assert [event["event_type"] for event in events] == [
        "analysis.empir.pixel_to_photon.started",
        "analysis.empir.pixel_to_photon.completed",
    ]
    completed = events[1]
    assert completed["domain"] == "analysis"
    assert completed["mode"] == "empir"
    assert completed["step"] == "pixel_to_photon"
    assert completed["resolved_executable_path"] == str(executable)
    assert completed["input_size_bytes"] == len("success")
    assert completed["exit_code"] == 0
    assert len(completed["stdout_excerpt"]) == 4_000
    assert len(completed["stderr_excerpt"]) == 4_000


@pytest.mark.parametrize(
    ("mode", "error_type", "message", "exit_code"),
    [
        ("nonzero", EmpirExecutionError, "exited with code 7", 7),
        ("missing_output", EmpirOutputError, "did not create", 0),
    ],
)
def test_execute_pixel_to_photon_reports_process_failure(
    tmp_path: Path,
    mode: str,
    error_type: type[EmpirExecutionError],
    message: str,
    exit_code: int,
) -> None:
    """Report nonzero exits and zero exits without the requested output."""
    stage = _stage(tmp_path, include_tdc1=False)
    run = stage.runs[0]
    run.input_tpx3_file.path.write_text(mode, encoding="utf-8")
    executable = tmp_path / "bin/empir_pixel2photon_tpx3spidr"
    write_fake_empir_program(executable)
    records: list[dict[str, object]] = []
    sink_id = logger.add(lambda log: records.append(log.record))

    try:
        with pytest.raises(error_type, match=message) as raised:
            execute_pixel_to_photon(stage, run, executable)
    finally:
        logger.remove(sink_id)

    assert raised.value.outcome.exit_code == exit_code
    failed = next(
        record["extra"]
        for record in records
        if record["extra"].get("event_type")
        == "analysis.empir.pixel_to_photon.failed"
    )
    assert failed["exit_code"] == exit_code
    assert len(failed["stdout_excerpt"]) == 4_000
    assert len(failed["stderr_excerpt"]) == 4_000
    assert message in failed["error"]


def test_execute_pixel_to_photon_reports_launch_failure(tmp_path: Path) -> None:
    """Record elapsed time and no exit code when process launch fails."""
    stage = _stage(tmp_path, include_tdc1=False)
    run = stage.runs[0]
    run.input_tpx3_file.path.write_text("success", encoding="utf-8")
    missing_executable = tmp_path / "bin/missing"

    with pytest.raises(EmpirExecutionError, match="failed to launch") as raised:
        execute_pixel_to_photon(stage, run, missing_executable)

    assert raised.value.outcome.exit_code is None
    assert raised.value.outcome.elapsed_seconds >= 0


def test_execute_pixel_to_photon_checks_paths_before_start(tmp_path: Path) -> None:
    """Reject a missing input before starting an external process."""
    stage = _stage(tmp_path, include_tdc1=False)
    run = stage.runs[0]

    with pytest.raises(EmpirPreflightError, match="input is not a regular file"):
        execute_pixel_to_photon(stage, run, tmp_path / "bin/program")
