"""Runs the C++ event reconstruction binary over reconstructed photon data.

Event reconstruction is 1:1: each photon Parquet file produces one event file at
the matching path (input basename kept). plan_event_reconstruction decides which
files still need work, execute_event_reconstruction runs the binary on one file
and reads its summary JSON for the per-file counts.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Literal, TypeAlias

from loguru import logger
from pydantic import ValidationError

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3EventReconstructionResult,
    Tpx3EventReconstruction,
    Tpx3EventReconstructionSummary,
)
from hermes.state.models.shared_models import FileReference

ContinuationAction: TypeAlias = Literal["run", "skip"]
EventReconstructionPlan: TypeAlias = list[tuple[FileReference, ContinuationAction]]

# The photon stage writes an optional diagnostic file beside each photon file;
# it is not a photon_events input and must not be handed to event reconstruction.
_PHOTON_PIXELS_SUFFIX = "-photon-pixels.parquet"

_LOG_TEXT_LIMIT = 4_000
_ANALYSIS_LOGGER = logger.bind(
    domain="analysis",
    mode="hermes",
    step="tpx3_spidr_event_reconstruction",
)


class HermesEventReconstructionError(Exception):
    """Base exception for HERMES event reconstruction failures."""


class HermesEventReconstructionPreflightError(HermesEventReconstructionError):
    """Raised when HERMES cannot safely start or continue event reconstruction."""


class HermesEventReconstructionExecutionError(HermesEventReconstructionError):
    """Raised when the event reconstruction process cannot complete."""


class HermesEventReconstructionOutputError(
    HermesEventReconstructionPreflightError
):
    """Raised when event output is missing, unsafe, or inconsistent."""


def resolve_photon_files(
    analysis: HermesTpx3AnalysisState,
) -> list[FileReference]:
    """Return the photon Parquet files event reconstruction should run over.

    ``photon_parquet_files == "auto"`` gathers every ``*.parquet`` under the
    photon stage's ``photons`` directory, skipping the photon stage's diagnostic
    photon-pixels files (which are not photon_events inputs); an explicit list is
    used as-is.
    """
    event_reconstruction = _require_event_reconstruction(analysis)
    if event_reconstruction.photon_parquet_files != "auto":
        return list(event_reconstruction.photon_parquet_files)

    photon_directory = analysis.analysis_directory / "photons"
    if not photon_directory.is_dir():
        return []
    return [
        FileReference(path=path)
        for path in sorted(photon_directory.glob("*.parquet"))
        if not path.name.endswith(_PHOTON_PIXELS_SUFFIX)
    ]


def derive_output_path(
    event_reconstruction: Tpx3EventReconstruction,
    input_file: FileReference,
) -> Path:
    """Return the event file path for one photon file (input basename kept)."""
    assert event_reconstruction.output_directory is not None  # derived on state
    return (
        event_reconstruction.output_directory / f"{input_file.path.stem}.parquet"
    )


def derive_summary_path(output_file: Path) -> Path:
    """Return the reconstruction-summary JSON file path written by the binary.

    The binary writes the summary to a ``logs/events`` directory beside the event
    output directory (the photon stage writes to ``logs/photons``), so it is a log
    artifact rather than sitting next to the event files themselves.
    """
    logs_directory = output_file.parent.parent / "logs" / "events"
    return logs_directory / f"{output_file.stem}-reconstruction-summary.json"


def derive_event_reconstruction_command(
    event_reconstruction: Tpx3EventReconstruction,
    input_file: FileReference,
    output_file: Path,
    settings_file: Path,
    *,
    overwrite: bool = False,
) -> list[str]:
    """Build the command line that launches the event reconstruction binary."""
    command = [
        str(event_reconstruction.program.executable_path),
        "--input",
        str(input_file.path),
        "--output",
        str(output_file),
        "--settings",
        str(settings_file),
    ]
    if overwrite:
        command.append("--overwrite")
    return command


def plan_event_reconstruction(
    analysis: HermesTpx3AnalysisState,
    *,
    overwrite: bool = False,
) -> EventReconstructionPlan:
    """Decide, per photon file, whether to "run" event reconstruction or "skip".

    With overwrite every file runs. Otherwise a file is skipped only when its
    reconstruction summary already exists, which the binary writes on every
    success (including zero-event runs that produce no event parquet).
    """
    event_reconstruction = _require_event_reconstruction(analysis)
    _validate_program_and_algorithm(event_reconstruction)

    plan: EventReconstructionPlan = []
    for input_file in resolve_photon_files(analysis):
        summary_path = derive_summary_path(
            derive_output_path(event_reconstruction, input_file)
        )
        if not overwrite and summary_path.exists():
            plan.append((input_file, "skip"))
        else:
            plan.append((input_file, "run"))
    return plan


def execute_event_reconstruction(
    analysis: HermesTpx3AnalysisState,
    input_file: FileReference,
    *,
    overwrite: bool = False,
) -> HermesTpx3EventReconstructionResult:
    """Run the binary on one photon file and return its per-file result.

    Raises a HermesEventReconstructionError if the binary fails to launch, exits
    with an error, or leaves no readable summary.
    """
    event_reconstruction = _require_event_reconstruction(analysis)
    output_file = derive_output_path(event_reconstruction, input_file)
    summary_path = derive_summary_path(output_file)
    started = perf_counter()

    # The complete event settings go to the binary in a temporary JSON file; the
    # field names match the binary's settings keys.
    settings_json = event_reconstruction.settings.model_dump(mode="json")
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=f"{input_file.path.stem}-event-settings-",
        delete=False,
    ) as settings_stream:
        json.dump(settings_json, settings_stream)
        settings_file = Path(settings_stream.name)

    command = derive_event_reconstruction_command(
        event_reconstruction,
        input_file,
        output_file,
        settings_file,
        overwrite=overwrite,
    )
    _ANALYSIS_LOGGER.info(
        "Reconstructing events from {photon_file}",
        event_type="analysis.tpx3_event_reconstruction.started",
        photon_file=str(input_file.path),
        output_file=str(output_file),
        summary_json_file=str(summary_path),
        executable_path=str(event_reconstruction.program.executable_path),
        executable_version=event_reconstruction.program.version,
        clustering_algorithm=event_reconstruction.clustering_algorithm,
        command=command,
    )

    try:
        try:
            process = subprocess.run(
                command,
                shell=False,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            elapsed_seconds = perf_counter() - started
            _log_process_failure(
                input_file,
                command,
                elapsed_seconds,
                error=str(exc),
            )
            raise HermesEventReconstructionExecutionError(
                f"failed to launch event reconstructor for {input_file.path}: "
                f"{exc}"
            ) from exc

        elapsed_seconds = perf_counter() - started
        stdout_excerpt = _bounded_text(process.stdout)
        stderr_excerpt = _bounded_text(process.stderr)
        if process.returncode != 0:
            _log_process_failure(
                input_file,
                command,
                elapsed_seconds,
                error=f"event reconstructor exited with code {process.returncode}",
                exit_code=process.returncode,
                stdout_excerpt=stdout_excerpt,
                stderr_excerpt=stderr_excerpt,
            )
            raise HermesEventReconstructionExecutionError(
                f"event reconstructor exited with code {process.returncode} for "
                f"{input_file.path}"
            )

        summary = _load_summary(summary_path)
    finally:
        settings_file.unlink(missing_ok=True)

    _ANALYSIS_LOGGER.info(
        "Reconstructed events from {photon_file} in {elapsed_seconds:.2f}s: "
        "{event_count} events",
        event_type="analysis.tpx3_event_reconstruction.completed",
        photon_file=str(input_file.path),
        output_file=str(output_file),
        summary_json_file=str(summary_path),
        command=command,
        exit_code=process.returncode,
        elapsed_seconds=elapsed_seconds,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        event_count=summary.reconstruction.event_count,
        photons_read=summary.reconstruction.photons_read,
    )
    return HermesTpx3EventReconstructionResult(
        input_file=input_file,
        output_file=output_file,
        status="completed",
        counts=summary.reconstruction,
    )


def log_skipped_input(
    input_file: FileReference,
    output_file: Path,
) -> None:
    """Log that one photon file was skipped because its summary already exists."""
    _ANALYSIS_LOGGER.warning(
        "Skipped {photon_file}: valid outputs already exist",
        event_type="analysis.tpx3_event_reconstruction.skipped",
        photon_file=str(input_file.path),
        output_file=str(output_file),
        reason="valid reconstruction summary already exists",
    )


def log_overall_completion(
    *,
    photon_file_count: int,
    reconstructed_file_count: int,
) -> None:
    """Log a summary line once every photon file has been handled."""
    _ANALYSIS_LOGGER.info(
        "Event reconstruction finished: {reconstructed_file_count} "
        "reconstructed, {skipped_file_count} skipped of {photon_file_count} "
        "photon files",
        event_type="analysis.tpx3_event_reconstruction.completed",
        scope="all_photon_files",
        photon_file_count=photon_file_count,
        reconstructed_file_count=reconstructed_file_count,
        skipped_file_count=photon_file_count - reconstructed_file_count,
    )


def log_overall_failure(error: Exception) -> None:
    """Log that the overall event reconstruction run failed."""
    _ANALYSIS_LOGGER.error(
        "Event reconstruction failed: {error}",
        event_type="analysis.tpx3_event_reconstruction.failed",
        scope="all_photon_files",
        error=str(error),
    )


def _require_event_reconstruction(
    analysis: HermesTpx3AnalysisState,
) -> Tpx3EventReconstruction:
    """Return the event reconstruction config, or raise if it is not set up."""
    event_reconstruction = analysis.event_reconstruction
    if event_reconstruction is None:
        raise HermesEventReconstructionPreflightError(
            "event reconstruction is not configured in the analysis state"
        )
    return event_reconstruction


def _validate_program_and_algorithm(
    event_reconstruction: Tpx3EventReconstruction,
) -> None:
    """Check the algorithm is supported and the binary exists before running."""
    if event_reconstruction.clustering_algorithm != "connected_components":
        raise HermesEventReconstructionPreflightError(
            f"clustering_algorithm={event_reconstruction.clustering_algorithm!r} "
            "is not implemented; only 'connected_components' is available"
        )
    executable = event_reconstruction.program.executable_path
    if not executable.is_file():
        raise HermesEventReconstructionPreflightError(
            f"event reconstructor executable does not exist: {executable}"
        )


def _load_summary(summary_path: Path) -> Tpx3EventReconstructionSummary:
    """Read and parse a reconstruction-summary JSON file into a model object."""
    if not summary_path.is_file():
        raise HermesEventReconstructionOutputError(
            f"reconstruction summary is missing: {summary_path}"
        )
    try:
        return Tpx3EventReconstructionSummary.model_validate_json(
            summary_path.read_bytes()
        )
    except OSError as exc:
        raise HermesEventReconstructionOutputError(
            f"cannot read summary JSON file: {summary_path}"
        ) from exc
    except ValidationError as exc:
        raise HermesEventReconstructionOutputError(
            f"invalid summary JSON file: {summary_path}"
        ) from exc


def _bounded_text(text: str) -> str:
    """Trim text so a single log entry cannot grow without bound."""
    return text[:_LOG_TEXT_LIMIT]


def _log_process_failure(
    input_file: FileReference,
    command: list[str],
    elapsed_seconds: float,
    *,
    error: str,
    exit_code: int | None = None,
    stdout_excerpt: str = "",
    stderr_excerpt: str = "",
) -> None:
    """Log a failure for one photon file with the command output for debugging."""
    message = "Reconstructing events from {photon_file} failed: {error}"
    if stderr_excerpt:
        message += "\nstderr: {stderr_excerpt}"
    _ANALYSIS_LOGGER.error(
        message,
        event_type="analysis.tpx3_event_reconstruction.failed",
        photon_file=str(input_file.path),
        command=command,
        exit_code=exit_code,
        elapsed_seconds=elapsed_seconds,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        error=error,
    )
