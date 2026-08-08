"""Build commands for the EMPIR photon-to-event program."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from hermes.runner.analysis.empir._errors import EmpirExecutionError
from hermes.runner.analysis.empir._process import (
    run_process,
    validate_step_paths,
)
from hermes.state.models.analysis.empir import (
    EmpirPhotonToEventResult,
    EmpirPhotonToEventRun,
    EmpirPhotonToEventState,
)
from hermes.state.models.shared_models import FileReference, utc_now

_STEP_NAME = "photon_to_event"
_EVENT_PREFIX = "analysis.empir.photon_to_event"
_ANALYSIS_LOGGER = logger.bind(
    domain="analysis",
    mode="empir",
    step=_STEP_NAME,
)


def build_photon_to_event_command(
    stage: EmpirPhotonToEventState,
    run: EmpirPhotonToEventRun,
    resolved_executable_path: Path,
) -> list[str]:
    """Build the command for one EMPIR photon input without a shell."""
    settings = stage.settings
    return [
        str(resolved_executable_path),
        "-i",
        str(run.photon_file.path),
        "-o",
        str(run.event_file),
        "-s",
        str(settings.spatial_distance_pixels),
        "-t",
        str(settings.time_distance_seconds),
        "-D",
        str(settings.maximum_duration_seconds),
    ]


def execute_photon_to_event(
    stage: EmpirPhotonToEventState,
    run: EmpirPhotonToEventRun,
    resolved_executable_path: Path,
) -> EmpirPhotonToEventResult:
    """Run photon-to-event once and return its verified result."""
    input_path = run.photon_file.path
    output_path = run.event_file
    validate_step_paths(_STEP_NAME, [input_path], output_path)
    command = build_photon_to_event_command(
        stage,
        run,
        resolved_executable_path,
    )
    started_at = utc_now()
    _ANALYSIS_LOGGER.info(
        "EMPIR photon-to-event started for {input_file}",
        event_type=f"{_EVENT_PREFIX}.started",
        executable_name=stage.program.name,
        configured_executable=str(stage.program.executable_path),
        resolved_executable_path=str(resolved_executable_path),
        executable_version=stage.program.version,
        command=command,
        command_args=command[1:],
        input_file=str(input_path),
        requested_output_file=str(output_path),
        input_size_bytes=input_path.stat().st_size,
    )

    try:
        outcome = run_process(
            _STEP_NAME,
            command,
            output_path,
            started_at,
        )
    except EmpirExecutionError as exc:
        _log_failure(stage, run, resolved_executable_path, command, exc)
        raise

    _ANALYSIS_LOGGER.info(
        "EMPIR photon-to-event completed in {elapsed_seconds:.3f}s",
        event_type=f"{_EVENT_PREFIX}.completed",
        executable_name=stage.program.name,
        configured_executable=str(stage.program.executable_path),
        resolved_executable_path=str(resolved_executable_path),
        executable_version=stage.program.version,
        command=command,
        command_args=command[1:],
        input_file=str(input_path),
        requested_output_file=str(output_path),
        input_size_bytes=input_path.stat().st_size,
        exit_code=outcome.exit_code,
        elapsed_seconds=outcome.elapsed_seconds,
        stdout_excerpt=outcome.stdout_excerpt,
        stderr_excerpt=outcome.stderr_excerpt,
    )
    return EmpirPhotonToEventResult(
        status="completed",
        started_at=outcome.started_at,
        completed_at=outcome.completed_at,
        elapsed_seconds=outcome.elapsed_seconds,
        exit_code=outcome.exit_code,
        event_file=FileReference(path=output_path),
    )


def _log_failure(
    stage: EmpirPhotonToEventState,
    run: EmpirPhotonToEventRun,
    resolved_executable_path: Path,
    command: list[str],
    error: EmpirExecutionError,
) -> None:
    """Log a bounded photon-to-event process failure."""
    outcome = error.outcome
    _ANALYSIS_LOGGER.error(
        "EMPIR photon-to-event failed: {error}",
        event_type=f"{_EVENT_PREFIX}.failed",
        executable_name=stage.program.name,
        configured_executable=str(stage.program.executable_path),
        resolved_executable_path=str(resolved_executable_path),
        executable_version=stage.program.version,
        command=command,
        command_args=command[1:],
        input_file=str(run.photon_file.path),
        requested_output_file=str(run.event_file),
        input_size_bytes=run.photon_file.path.stat().st_size,
        exit_code=outcome.exit_code,
        elapsed_seconds=outcome.elapsed_seconds,
        stdout_excerpt=outcome.stdout_excerpt,
        stderr_excerpt=outcome.stderr_excerpt,
        error=str(error),
    )
