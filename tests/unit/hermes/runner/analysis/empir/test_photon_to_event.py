"""Tests for EMPIR photon-to-event command construction."""

from pathlib import Path

from loguru import logger

from hermes.runner.analysis.empir.photon_to_event import (
    build_photon_to_event_command,
    execute_photon_to_event,
)
from hermes.state.models.analysis.empir import (
    EmpirPhotonToEventRun,
    EmpirPhotonToEventSettings,
    EmpirPhotonToEventState,
)
from hermes.state.models.shared_models import BinaryProgram, FileReference
from _fake_program import write_fake_empir_program


def _stage(
    tmp_path: Path,
    *,
    spatial_distance: float,
    time_distance: float,
    maximum_duration: float,
) -> EmpirPhotonToEventState:
    """Build one photon-to-event stage for command tests."""
    return EmpirPhotonToEventState(
        program=BinaryProgram(
            name="empir-photon2event",
            executable_path="empir_photon2event",
        ),
        settings=EmpirPhotonToEventSettings(
            spatial_distance_pixels=spatial_distance,
            time_distance_seconds=time_distance,
            maximum_duration_seconds=maximum_duration,
        ),
        runs=[
            EmpirPhotonToEventRun(
                input_photon_file=FileReference(
                    path=tmp_path / "raw.empirphot"
                ),
                event_file=tmp_path / "raw.empirevent",
            )
        ],
    )


def test_build_photon_to_event_minimal_command(tmp_path: Path) -> None:
    """Build the command when each required numeric setting is zero."""
    stage = _stage(
        tmp_path,
        spatial_distance=0,
        time_distance=0,
        maximum_duration=0,
    )
    executable = tmp_path / "bin/empir_photon2event"

    assert build_photon_to_event_command(
        stage, stage.runs[0], executable
    ) == [
        str(executable),
        "-i",
        str(tmp_path / "raw.empirphot"),
        "-o",
        str(tmp_path / "raw.empirevent"),
        "-s",
        "0.0",
        "-t",
        "0.0",
        "-D",
        "0.0",
    ]


def test_build_photon_to_event_full_command(tmp_path: Path) -> None:
    """Map all photon-to-event settings to their documented short flags."""
    stage = _stage(
        tmp_path,
        spatial_distance=4,
        time_distance=100e-6,
        maximum_duration=500e-6,
    )
    executable = tmp_path / "bin/empir_photon2event"

    assert build_photon_to_event_command(
        stage, stage.runs[0], executable
    ) == [
        str(executable),
        "-i",
        str(tmp_path / "raw.empirphot"),
        "-o",
        str(tmp_path / "raw.empirevent"),
        "-s",
        "4.0",
        "-t",
        "0.0001",
        "-D",
        "0.0005",
    ]


def test_execute_photon_to_event_records_result_and_logs(tmp_path: Path) -> None:
    """Run the photon-to-event program and record its completed event."""
    stage = _stage(
        tmp_path,
        spatial_distance=4,
        time_distance=100e-6,
        maximum_duration=500e-6,
    )
    run = stage.runs[0]
    run.input_photon_file.path.write_text("success", encoding="utf-8")
    executable = tmp_path / "bin/empir_photon2event"
    write_fake_empir_program(executable)
    records: list[dict[str, object]] = []
    sink_id = logger.add(lambda message: records.append(message.record))

    try:
        result = execute_photon_to_event(stage, run, executable)
    finally:
        logger.remove(sink_id)

    assert result.status == "completed"
    assert result.saved_event_file is not None
    assert result.saved_event_file.path == run.event_file
    event_types = [
        record["extra"].get("event_type") for record in records
    ]
    assert "analysis.empir.photon_to_event.started" in event_types
    assert "analysis.empir.photon_to_event.completed" in event_types
