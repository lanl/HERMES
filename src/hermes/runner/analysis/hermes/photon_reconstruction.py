"""Runs the C++ photon reconstruction binary over unpacked pixel data.

Reconstruction is 1:1: each pixel Parquet file produces one photon file at the
matching path (input basename kept). execute_reconstruction runs the binary on
one file and reads its summary JSON for the per-file counts.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter

from loguru import logger
from pydantic import ValidationError

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3PhotonReconstructionResult,
    HermesTpx3PhotonReconstruction,
    HermesTpx3PhotonReconstructionSummary,
)
from hermes.state.models.shared_models import FileReference

_LOG_TEXT_LIMIT = 4_000
_ANALYSIS_LOGGER = logger.bind(
    domain="analysis",
    mode="hermes",
    step="tpx3_spidr_reconstruction",
)


class HermesPhotonReconstructionError(Exception):
    """Base exception for HERMES photon reconstruction failures."""


class HermesPhotonReconstructionPreflightError(HermesPhotonReconstructionError):
    """Raised when HERMES cannot safely start or continue reconstruction."""


class HermesPhotonReconstructionExecutionError(HermesPhotonReconstructionError):
    """Raised when the clustering process cannot complete successfully."""


class HermesPhotonReconstructionOutputError(HermesPhotonReconstructionPreflightError):
    """Raised when reconstruction output is missing, unsafe, or inconsistent."""


def resolve_pixel_files(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
) -> list[FileReference]:
    """Return the pixel Parquet files reconstruction should run over.

    ``pixel_files == "auto"`` gathers every ``*.parquet`` under the
    unpacking stage's ``pixel_hits`` directory; an explicit list is used as-is.
    """
    reconstruction = _require_reconstruction(analysis)
    if reconstruction.pixel_files != "auto":
        return list(reconstruction.pixel_files)

    pixel_directory = analysis_root / "pixel_hits"
    if not pixel_directory.is_dir():
        return []
    return [
        FileReference(path=path)
        for path in sorted(pixel_directory.glob("*.parquet"))
    ]


def derive_output_path(
    analysis_root: Path,
    input_file: FileReference,
) -> Path:
    """Return the photon file path for one pixel file (input basename kept).

    Photon files go in a ``photons`` directory the reconstruction stage makes
    under the analysis directory.
    """
    return analysis_root / "photons" / f"{input_file.path.stem}.parquet"


def check_previous_reconstructed_file(
    analysis_root: Path,
    input_file: FileReference,
) -> bool:
    """Return True when this pixel file was already reconstructed before.

    The binary writes a per-file reconstruction summary on every success
    (including zero-photon runs that produce no photon parquet), so its presence
    means the file is already done.
    """
    output_file = derive_output_path(analysis_root, input_file)
    return derive_summary_path(output_file).is_file()


def derive_summary_path(output_file: Path) -> Path:
    """Return the reconstruction-summary JSON file path written by the binary.

    The binary writes the summary to a ``logs/photons`` directory beside the
    photon output directory (the unpacker writes to ``logs/unpacker``), so it is
    a log artifact rather than sitting next to the photon files themselves.
    """
    logs_directory = output_file.parent.parent / "logs" / "photons"
    return logs_directory / f"{output_file.stem}-reconstruction-summary.json"


def derive_reconstruction_command(
    reconstruction: HermesTpx3PhotonReconstruction,
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


def execute_reconstruction(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
    input_file: FileReference,
    *,
    overwrite: bool = False,
) -> HermesTpx3PhotonReconstructionResult:
    """Run the binary on one pixel file and return its per-file result.

    Raises a HermesPhotonReconstructionError if the binary fails to launch, exits with
    an error, or leaves no readable summary.
    """
    reconstruction = _require_reconstruction(analysis)
    output_file = derive_output_path(analysis_root, input_file)
    summary_path = derive_summary_path(output_file)
    started = perf_counter()

    # The complete clustering settings go to the binary in a temporary JSON
    # file; the field names match the binary's settings keys. save_photon_pixels
    # lives beside the settings in the model, so add it back into the JSON the
    # binary reads.
    clustering = reconstruction.clustering_algorithm
    settings_json = clustering.settings.model_dump(mode="json")
    settings_json["save_photon_pixels"] = clustering.save_photon_pixels
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
        "Reconstructing {pixel_file}",
        event_type="analysis.tpx3_reconstruction.started",
        pixel_file=str(input_file.path),
        output_file=str(output_file),
        summary_json_file=str(summary_path),
        executable_path=str(reconstruction.program.executable_path),
        executable_version=reconstruction.program.version,
        clustering_algorithm=reconstruction.clustering_algorithm.name,
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
            raise HermesPhotonReconstructionExecutionError(
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
            raise HermesPhotonReconstructionExecutionError(
                f"clusterer exited with code {process.returncode} for "
                f"{input_file.path}"
            )

        summary = _load_summary(summary_path)
    finally:
        settings_file.unlink(missing_ok=True)

    _ANALYSIS_LOGGER.info(
        "Reconstructed {pixel_file} in {elapsed_seconds:.2f}s: "
        "{photon_count} photons",
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
    return HermesTpx3PhotonReconstructionResult(
        input_file=input_file,
        output_file=output_file,
        status="completed",
        counts=summary.reconstruction,
    )


def log_skipped_input(
    input_file: FileReference,
    output_file: Path,
) -> None:
    """Log that one pixel file was skipped because its summary already exists."""
    _ANALYSIS_LOGGER.warning(
        "Skipped {pixel_file}: valid outputs already exist",
        event_type="analysis.tpx3_reconstruction.skipped",
        pixel_file=str(input_file.path),
        output_file=str(output_file),
        reason="valid reconstruction summary already exists",
    )


def log_overall_completion(
    *,
    pixel_file_count: int,
    reconstructed_file_count: int,
) -> None:
    """Log a summary line once every pixel file has been handled."""
    _ANALYSIS_LOGGER.info(
        "Reconstruction finished: {reconstructed_file_count} reconstructed, "
        "{skipped_file_count} skipped of {pixel_file_count} pixel files",
        event_type="analysis.tpx3_reconstruction.completed",
        scope="all_pixel_files",
        pixel_file_count=pixel_file_count,
        reconstructed_file_count=reconstructed_file_count,
        skipped_file_count=pixel_file_count - reconstructed_file_count,
    )


def log_overall_failure(error: Exception) -> None:
    """Log that the overall reconstruction run failed."""
    _ANALYSIS_LOGGER.error(
        "Reconstruction failed: {error}",
        event_type="analysis.tpx3_reconstruction.failed",
        scope="all_pixel_files",
        error=str(error),
    )


def _require_reconstruction(
    analysis: HermesTpx3AnalysisState,
) -> HermesTpx3PhotonReconstruction:
    """Return the reconstruction config, or raise if it is not set up."""
    reconstruction = analysis.photon_reconstruction
    if reconstruction is None:
        raise HermesPhotonReconstructionPreflightError(
            "photon reconstruction is not configured in the analysis state"
        )
    return reconstruction


def validate_program_and_algorithm(
    reconstruction: HermesTpx3PhotonReconstruction,
) -> None:
    """Check the algorithm is supported and the binary exists before running."""
    if reconstruction.clustering_algorithm.name != "connected_components":
        raise HermesPhotonReconstructionPreflightError(
            f"clustering_algorithm={reconstruction.clustering_algorithm.name!r} "
            "is not implemented; only 'connected_components' is available"
        )
    executable = reconstruction.program.executable_path
    if not executable.is_file():
        raise HermesPhotonReconstructionPreflightError(
            f"clusterer executable does not exist: {executable}"
        )


def _load_summary(summary_path: Path) -> HermesTpx3PhotonReconstructionSummary:
    """Read and parse a reconstruction-summary JSON file into a model object."""
    if not summary_path.is_file():
        raise HermesPhotonReconstructionOutputError(
            f"reconstruction summary is missing: {summary_path}"
        )
    try:
        return HermesTpx3PhotonReconstructionSummary.model_validate_json(
            summary_path.read_bytes()
        )
    except OSError as exc:
        raise HermesPhotonReconstructionOutputError(
            f"cannot read summary JSON file: {summary_path}"
        ) from exc
    except ValidationError as exc:
        raise HermesPhotonReconstructionOutputError(
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
    message = "Reconstructing {pixel_file} failed: {error}"
    if stderr_excerpt:
        message += "\nstderr: {stderr_excerpt}"
    _ANALYSIS_LOGGER.error(
        message,
        event_type="analysis.tpx3_reconstruction.failed",
        pixel_file=str(input_file.path),
        command=command,
        exit_code=exit_code,
        elapsed_seconds=elapsed_seconds,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        error=error,
    )
