"""Runs the C++ photon reconstruction binary over unpacked pixel data.

Reconstruction is 1:1: each pixel Parquet file produces one photon file at the
matching path (input basename kept). plan_reconstruction decides which files
still need work, execute_reconstruction runs the binary on one file and reads
its sidecar summary for the per-file counts.
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
    HermesTpx3ReconstructionResult,
    Tpx3PhotonReconstruction,
    Tpx3PhotonReconstructionSummary,
)
from hermes.state.models.shared_models import FileReference, utc_now

ContinuationAction: TypeAlias = Literal["run", "skip"]
ReconstructionPlan: TypeAlias = list[tuple[FileReference, ContinuationAction]]

_LOG_TEXT_LIMIT = 4_000
_ANALYSIS_LOGGER = logger.bind(
    domain="analysis",
    mode="hermes",
    step="tpx3_spidr_reconstruction",
)


class HermesReconstructionError(Exception):
    """Base exception for HERMES photon reconstruction failures."""


class HermesReconstructionPreflightError(HermesReconstructionError):
    """Raised when HERMES cannot safely start or continue reconstruction."""


class HermesReconstructionExecutionError(HermesReconstructionError):
    """Raised when the clustering process cannot complete successfully."""


class HermesReconstructionOutputError(HermesReconstructionPreflightError):
    """Raised when reconstruction output is missing, unsafe, or inconsistent."""


def resolve_pixel_files(
    analysis: HermesTpx3AnalysisState,
) -> list[FileReference]:
    """Return the pixel Parquet files reconstruction should run over.

    ``pixel_parquet_files == "auto"`` gathers every ``*.parquet`` under the
    unpacking stage's ``pixelHits`` directory; an explicit list is used as-is.
    """
    reconstruction = _require_reconstruction(analysis)
    if reconstruction.pixel_parquet_files != "auto":
        return list(reconstruction.pixel_parquet_files)

    pixel_directory = analysis.analysis_directory / "pixelHits"
    if not pixel_directory.is_dir():
        return []
    return [
        FileReference(path=path)
        for path in sorted(pixel_directory.glob("*.parquet"))
    ]


def derive_output_path(
    reconstruction: Tpx3PhotonReconstruction,
    input_file: FileReference,
) -> Path:
    """Return the photon file path for one pixel file (input basename kept)."""
    assert reconstruction.output_directory is not None  # derived on the state
    return reconstruction.output_directory / f"{input_file.path.stem}.parquet"


def derive_summary_path(output_file: Path) -> Path:
    """Return the reconstruction-summary sidecar the binary writes."""
    return output_file.parent / f"{output_file.stem}-reconstruction-summary.json"


def derive_reconstruction_command(
    reconstruction: Tpx3PhotonReconstruction,
    input_file: FileReference,
    output_file: Path,
    settings_file: Path,
    *,
    overwrite: bool = False,
) -> list[str]:
    """Build the command line that launches the reconstruction binary."""
    command = [
        str(reconstruction.program.executable_path),
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


def plan_reconstruction(
    analysis: HermesTpx3AnalysisState,
    *,
    overwrite: bool = False,
) -> ReconstructionPlan:
    """Decide, per pixel file, whether to "run" reconstruction or "skip" it.

    With overwrite every file runs. Otherwise a file is skipped only when its
    photon output file already exists.
    """
    reconstruction = _require_reconstruction(analysis)
    _validate_program_and_algorithm(reconstruction)

    plan: ReconstructionPlan = []
    for input_file in resolve_pixel_files(analysis):
        if not overwrite and derive_output_path(
            reconstruction, input_file
        ).exists():
            plan.append((input_file, "skip"))
        else:
            plan.append((input_file, "run"))
    return plan


def execute_reconstruction(
    analysis: HermesTpx3AnalysisState,
    input_file: FileReference,
    *,
    overwrite: bool = False,
) -> HermesTpx3ReconstructionResult:
    """Run the binary on one pixel file and return its per-file result.

    Raises a HermesReconstructionError if the binary fails to launch, exits with
    an error, or leaves no readable summary.
    """
    reconstruction = _require_reconstruction(analysis)
    output_file = derive_output_path(reconstruction, input_file)
    summary_path = derive_summary_path(output_file)
    started_at = utc_now()
    started = perf_counter()

    # The complete clustering settings go to the binary in a temporary JSON
    # file; the field names match the binary's settings keys.
    settings_json = reconstruction.settings.model_dump(mode="json")
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=f"{input_file.path.stem}-clustering-settings-",
        delete=False,
    ) as settings_stream:
        json.dump(settings_json, settings_stream)
        settings_file = Path(settings_stream.name)

    command = derive_reconstruction_command(
        reconstruction,
        input_file,
        output_file,
        settings_file,
        overwrite=overwrite,
    )
    _ANALYSIS_LOGGER.info(
        "analysis.tpx3_reconstruction.started",
        event_type="analysis.tpx3_reconstruction.started",
        pixel_file=str(input_file.path),
        output_file=str(output_file),
        summary_json_file=str(summary_path),
        executable_path=str(reconstruction.program.executable_path),
        executable_version=reconstruction.program.version,
        clustering_algorithm=reconstruction.clustering_algorithm,
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
            raise HermesReconstructionExecutionError(
                f"failed to launch clusterer for {input_file.path}: {exc}"
            ) from exc

        elapsed_seconds = perf_counter() - started
        stdout_excerpt = _bounded_text(process.stdout)
        stderr_excerpt = _bounded_text(process.stderr)
        if process.returncode != 0:
            _log_process_failure(
                input_file,
                command,
                elapsed_seconds,
                error=f"clusterer exited with code {process.returncode}",
                exit_code=process.returncode,
                stdout_excerpt=stdout_excerpt,
                stderr_excerpt=stderr_excerpt,
            )
            raise HermesReconstructionExecutionError(
                f"clusterer exited with code {process.returncode} for "
                f"{input_file.path}"
            )

        summary = _load_summary(summary_path)
    finally:
        settings_file.unlink(missing_ok=True)

    _ANALYSIS_LOGGER.info(
        "analysis.tpx3_reconstruction.completed",
        event_type="analysis.tpx3_reconstruction.completed",
        pixel_file=str(input_file.path),
        output_file=str(output_file),
        summary_json_file=str(summary_path),
        command=command,
        exit_code=process.returncode,
        elapsed_seconds=elapsed_seconds,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        photon_count=summary.reconstruction.photon_count,
        rejected_component_count=summary.reconstruction.rejected_component_count,
    )
    return HermesTpx3ReconstructionResult(
        input_file=input_file,
        output_file=output_file,
        status="completed",
        started_at=started_at,
        completed_at=utc_now(),
        counts=summary.reconstruction,
    )


def log_skipped_input(
    input_file: FileReference,
    output_file: Path,
) -> None:
    """Log that one pixel file was skipped because its photon file exists."""
    _ANALYSIS_LOGGER.info(
        "analysis.tpx3_reconstruction.skipped",
        event_type="analysis.tpx3_reconstruction.skipped",
        pixel_file=str(input_file.path),
        output_file=str(output_file),
        reason="photon output file already exists",
    )


def log_overall_completion(
    *,
    pixel_file_count: int,
    reconstructed_file_count: int,
) -> None:
    """Log a summary line once every pixel file has been handled."""
    _ANALYSIS_LOGGER.info(
        "analysis.tpx3_reconstruction.completed",
        event_type="analysis.tpx3_reconstruction.completed",
        scope="all_pixel_files",
        pixel_file_count=pixel_file_count,
        reconstructed_file_count=reconstructed_file_count,
        skipped_file_count=pixel_file_count - reconstructed_file_count,
    )


def log_overall_failure(error: Exception) -> None:
    """Log that the overall reconstruction run failed."""
    _ANALYSIS_LOGGER.error(
        "analysis.tpx3_reconstruction.failed",
        event_type="analysis.tpx3_reconstruction.failed",
        scope="all_pixel_files",
        error=str(error),
    )


def _require_reconstruction(
    analysis: HermesTpx3AnalysisState,
) -> Tpx3PhotonReconstruction:
    """Return the reconstruction config, or raise if it is not set up."""
    reconstruction = analysis.photon_reconstruction
    if reconstruction is None:
        raise HermesReconstructionPreflightError(
            "photon reconstruction is not configured in the analysis state"
        )
    return reconstruction


def _validate_program_and_algorithm(
    reconstruction: Tpx3PhotonReconstruction,
) -> None:
    """Check the algorithm is supported and the binary exists before running."""
    if reconstruction.clustering_algorithm != "connected_components":
        raise HermesReconstructionPreflightError(
            f"clustering_algorithm={reconstruction.clustering_algorithm!r} is "
            "not implemented; only 'connected_components' is available"
        )
    executable = reconstruction.program.executable_path
    if not executable.is_file():
        raise HermesReconstructionPreflightError(
            f"clusterer executable does not exist: {executable}"
        )


def _load_summary(summary_path: Path) -> Tpx3PhotonReconstructionSummary:
    """Read and parse a reconstruction-summary sidecar into a model object."""
    if not summary_path.is_file():
        raise HermesReconstructionOutputError(
            f"reconstruction summary is missing: {summary_path}"
        )
    try:
        return Tpx3PhotonReconstructionSummary.model_validate_json(
            summary_path.read_bytes()
        )
    except OSError as exc:
        raise HermesReconstructionOutputError(
            f"cannot read summary JSON file: {summary_path}"
        ) from exc
    except ValidationError as exc:
        raise HermesReconstructionOutputError(
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
    """Log a failure for one pixel file with the command output for debugging."""
    _ANALYSIS_LOGGER.error(
        "analysis.tpx3_reconstruction.failed",
        event_type="analysis.tpx3_reconstruction.failed",
        pixel_file=str(input_file.path),
        command=command,
        exit_code=exit_code,
        elapsed_seconds=elapsed_seconds,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        error=error,
    )
