"""Build commands for the EMPIR event-to-image program."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from hermes.runner.analysis.empir._errors import EmpirExecutionError
from hermes.runner.analysis.empir._process import (
    run_process,
    validate_step_paths,
)
from hermes.state.models.analysis.empir import (
    EmpirEventToImageResult,
    EmpirEventToImageState,
)
from hermes.state.models.shared_models import FileReference

_STEP_NAME = "event_to_image"
_EVENT_PREFIX = "analysis.empir.event_to_image"
_ANALYSIS_LOGGER = logger.bind(
    domain="analysis",
    mode="empir",
    step=_STEP_NAME,
)


def build_event_to_image_command(
    stage: EmpirEventToImageState,
    resolved_executable_path: Path,
) -> list[str]:
    """Build the image command with exact, comma-separated event inputs."""
    settings = stage.settings
    command = [
        str(resolved_executable_path),
        "-i",
        ",".join(str(file.path) for file in stage.event_files),
        "-o",
        str(stage.tiff_file),
        "-x",
        str(settings.image_width_pixels),
    ]

    optional_arguments = (
        ("-y", settings.image_height_pixels),
        ("-m", settings.minimum_photon_count),
        ("-M", settings.maximum_photon_count),
        ("-p", settings.minimum_psd),
        ("-P", settings.maximum_psd),
        ("-E", settings.external_trigger_mode),
        ("-t", settings.time_bin_width_seconds),
        ("-T", settings.time_bin_count),
        ("--fileFormat", settings.tiff_format),
    )
    for flag, value in optional_arguments:
        if value is not None:
            command.extend([flag, str(value)])

    if settings.parallel is not None:
        command.extend(["--parallel", str(settings.parallel).lower()])

    return command


def execute_event_to_image(
    stage: EmpirEventToImageState,
    resolved_executable_path: Path,
) -> EmpirEventToImageResult:
    """Run event-to-image once and return its verified TIFF result."""
    input_paths = [file.path for file in stage.event_files]
    output_path = stage.tiff_file
    validate_step_paths(_STEP_NAME, input_paths)
    command = build_event_to_image_command(stage, resolved_executable_path)
    _ANALYSIS_LOGGER.info(
        "EMPIR event-to-image started for {input_file_count} files",
        event_type=f"{_EVENT_PREFIX}.started",
        executable_name=stage.program.name,
        configured_executable=str(stage.program.executable_path),
        resolved_executable_path=str(resolved_executable_path),
        executable_version=stage.program.version,
        command=command,
        command_args=command[1:],
        input_files=[str(path) for path in input_paths],
        input_file_count=len(input_paths),
        requested_output_file=str(output_path),
    )

    try:
        outcome = run_process(
            _STEP_NAME,
            command,
            output_path,
        )
    except EmpirExecutionError as exc:
        _log_failure(stage, resolved_executable_path, command, exc)
        raise

    _ANALYSIS_LOGGER.info(
        "EMPIR event-to-image completed in {elapsed_seconds:.3f}s",
        event_type=f"{_EVENT_PREFIX}.completed",
        executable_name=stage.program.name,
        configured_executable=str(stage.program.executable_path),
        resolved_executable_path=str(resolved_executable_path),
        executable_version=stage.program.version,
        command=command,
        command_args=command[1:],
        input_files=[str(path) for path in input_paths],
        input_file_count=len(input_paths),
        requested_output_file=str(output_path),
        exit_code=outcome.exit_code,
        elapsed_seconds=outcome.elapsed_seconds,
        stdout_excerpt=outcome.stdout_excerpt,
        stderr_excerpt=outcome.stderr_excerpt,
    )
    return EmpirEventToImageResult(
        status="completed",
        elapsed_seconds=outcome.elapsed_seconds,
        exit_code=outcome.exit_code,
        tiff_file=FileReference(path=output_path),
    )


def _log_failure(
    stage: EmpirEventToImageState,
    resolved_executable_path: Path,
    command: list[str],
    error: EmpirExecutionError,
) -> None:
    """Log a bounded event-to-image process failure."""
    outcome = error.outcome
    input_paths = [file.path for file in stage.event_files]
    _ANALYSIS_LOGGER.error(
        "EMPIR event-to-image failed: {error}",
        event_type=f"{_EVENT_PREFIX}.failed",
        executable_name=stage.program.name,
        configured_executable=str(stage.program.executable_path),
        resolved_executable_path=str(resolved_executable_path),
        executable_version=stage.program.version,
        command=command,
        command_args=command[1:],
        input_files=[str(path) for path in input_paths],
        input_file_count=len(input_paths),
        requested_output_file=str(stage.tiff_file),
        exit_code=outcome.exit_code,
        elapsed_seconds=outcome.elapsed_seconds,
        stdout_excerpt=outcome.stdout_excerpt,
        stderr_excerpt=outcome.stderr_excerpt,
        error=str(error),
    )
