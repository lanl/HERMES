"""Build commands for the EMPIR pixel-to-photon program."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from hermes.runner.analysis.empir._errors import EmpirExecutionError
from hermes.runner.analysis.empir._process import (
    run_process,
    validate_step_paths,
)
from hermes.state.models.analysis.empir import (
    EmpirPixelToPhotonResult,
    EmpirPixelToPhotonRun,
    EmpirPixelToPhotonState,
)
from hermes.state.models.shared_models import FileReference

_STEP_NAME = "pixel_to_photon"
_EVENT_PREFIX = "analysis.empir.pixel_to_photon"
_ANALYSIS_LOGGER = logger.bind(
    domain="analysis",
    mode="empir",
    step=_STEP_NAME,
)


def build_pixel_to_photon_command(
    stage: EmpirPixelToPhotonState,
    run: EmpirPixelToPhotonRun,
    resolved_executable_path: Path,
) -> list[str]:
    """Build the command for one TPX3 input without invoking a shell."""
    settings = stage.settings
    command = [
        str(resolved_executable_path),
        "-i",
        str(run.tpx3_file.path),
        "-o",
        str(run.photon_file),
        "-s",
        str(settings.spatial_distance_pixels),
        "-t",
        str(settings.time_distance_seconds),
        "-k",
        str(settings.minimum_pixel_count),
    ]
    if settings.include_tdc1:
        command.append("-T")
    return command


def execute_pixel_to_photon(
    stage: EmpirPixelToPhotonState,
    run: EmpirPixelToPhotonRun,
    resolved_executable_path: Path,
) -> EmpirPixelToPhotonResult:
    """Run pixel-to-photon once and return its verified result."""
    input_path = run.tpx3_file.path
    output_path = run.photon_file
    validate_step_paths(_STEP_NAME, [input_path])
    command = build_pixel_to_photon_command(
        stage,
        run,
        resolved_executable_path,
    )
    _ANALYSIS_LOGGER.info(
        "EMPIR pixel-to-photon started for {input_file}",
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
        )
    except EmpirExecutionError as exc:
        _log_failure(stage, run, resolved_executable_path, command, exc)
        raise

    _ANALYSIS_LOGGER.info(
        "EMPIR pixel-to-photon completed in {elapsed_seconds:.3f}s",
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
    return EmpirPixelToPhotonResult(
        status="completed",
        elapsed_seconds=outcome.elapsed_seconds,
        exit_code=outcome.exit_code,
        photon_file=FileReference(path=output_path),
    )


def _log_failure(
    stage: EmpirPixelToPhotonState,
    run: EmpirPixelToPhotonRun,
    resolved_executable_path: Path,
    command: list[str],
    error: EmpirExecutionError,
) -> None:
    """Log a bounded pixel-to-photon process failure."""
    outcome = error.outcome
    _ANALYSIS_LOGGER.error(
        "EMPIR pixel-to-photon failed: {error}",
        event_type=f"{_EVENT_PREFIX}.failed",
        executable_name=stage.program.name,
        configured_executable=str(stage.program.executable_path),
        resolved_executable_path=str(resolved_executable_path),
        executable_version=stage.program.version,
        command=command,
        command_args=command[1:],
        input_file=str(run.tpx3_file.path),
        requested_output_file=str(run.photon_file),
        input_size_bytes=run.tpx3_file.path.stat().st_size,
        exit_code=outcome.exit_code,
        elapsed_seconds=outcome.elapsed_seconds,
        stdout_excerpt=outcome.stdout_excerpt,
        stderr_excerpt=outcome.stderr_excerpt,
        error=str(error),
    )
