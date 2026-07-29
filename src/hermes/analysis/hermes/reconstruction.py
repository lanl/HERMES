"""Runs the C++ photon reconstruction binary over unpacked pixel data.

The flow is: plan_reconstruction decides which raw files still need work,
execute_reconstruction runs the binary on one file and checks its output, and
the helpers below validate that the files it produced are complete and safe.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Literal, TypeAlias

import pyarrow.parquet as pq
from loguru import logger
from pydantic import ValidationError

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3PhotonReconstructionConfiguration,
    Tpx3PhotonReconstructionSummary,
)
from hermes.state.models.shared_models import FileReference

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


def derive_summary_path(
    analysis: HermesTpx3AnalysisState,
    raw_file: FileReference,
) -> Path:
    """Return the path of the summary JSON the binary writes for one raw file."""
    # The file is named after the raw file (without its extension), under logs/.
    return (
        analysis.analysis_directory
        / "logs"
        / f"{raw_file.path.stem}-reconstruction-summary.json"
    )


def derive_reconstruction_command(
    reconstruction: Tpx3PhotonReconstructionConfiguration,
    analysis_directory: Path,
    raw_file_stem: str,
    settings_file: Path,
    *,
    overwrite: bool = False,
) -> list[str]:
    """Build the command line that launches the reconstruction binary."""
    # Reads pixel data from and writes results to the same analysis directory.
    # --overwrite lets it replace files from a previous run; without it the
    # binary refuses and stops.
    command = [
        str(reconstruction.program.executable_path),
        "--input",
        str(analysis_directory),
        "--base-file-name",
        raw_file_stem,
        "--output",
        str(analysis_directory),
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
    """Decide, per raw file, whether to "run" reconstruction or "skip" it.

    A file is skipped when valid results already exist. This runs before any
    binary is launched, so problems are caught up front.
    """
    reconstruction = _require_reconstruction(analysis)
    _validate_program_and_algorithm(reconstruction)

    # With overwrite, redo every file regardless of existing output.
    if overwrite:
        return [(raw_file, "run") for raw_file in analysis.tpx3_files]

    plan: ReconstructionPlan = []
    for raw_file in analysis.tpx3_files:
        summary_path = derive_summary_path(analysis, raw_file)
        # Photon files already sitting in the output directory for this file.
        matching_photon_files = _matching_photon_files(
            reconstruction.photon_output_directory,
            raw_file.path.stem,
        )

        # A summary exists: only skip if it matches the requested settings and
        # its files check out. A mismatch means the existing results are stale.
        if summary_path.exists():
            summary = _load_summary(summary_path)
            if (
                summary.clustering.algorithm != reconstruction.clustering_algorithm
                or summary.clustering.settings != reconstruction.settings
            ):
                raise HermesReconstructionOutputError(
                    "reconstruction summary settings do not match the requested settings: "
                    f"{summary_path}"
                )
            _validate_completed_files(
                summary,
                summary_path,
                analysis.analysis_directory,
                raw_file.path.stem,
            )
            plan.append((raw_file, "skip"))
        # Photon files but no summary means a half-finished or corrupt run; stop
        # rather than silently overwrite or trust them.
        elif matching_photon_files:
            raise HermesReconstructionPreflightError(
                f"photon files exist without a valid summary for "
                f"{raw_file.path}: {matching_photon_files[0]}"
            )
        # Nothing on disk yet: this file needs reconstruction.
        else:
            plan.append((raw_file, "run"))

    return plan


def execute_reconstruction(
    analysis: HermesTpx3AnalysisState,
    raw_file: FileReference,
    *,
    overwrite: bool = False,
) -> Tpx3PhotonReconstructionSummary:
    """Run the binary on one raw file and return its validated summary.

    Raises a HermesReconstructionError if the binary fails to launch, exits with
    an error, or produces output that does not pass validation.
    """
    reconstruction = _require_reconstruction(analysis)
    summary_path = derive_summary_path(analysis, raw_file)
    started = perf_counter()

    # HERMES delivers the complete clustering settings to the binary in a
    # temporary JSON file and removes it after the process exits. The field
    # names match the binary's settings keys.
    settings_json = reconstruction.settings.model_dump(mode="json")
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=f"{raw_file.path.stem}-clustering-settings-",
        delete=False,
    ) as settings_stream:
        json.dump(settings_json, settings_stream)
        settings_file = Path(settings_stream.name)

    command = derive_reconstruction_command(
        reconstruction,
        analysis.analysis_directory,
        raw_file.path.stem,
        settings_file,
        overwrite=overwrite,
    )
    _ANALYSIS_LOGGER.info(
        "analysis.tpx3_reconstruction.started",
        event_type="analysis.tpx3_reconstruction.started",
        raw_tpx3_file=str(raw_file.path),
        raw_file_stem=raw_file.path.stem,
        analysis_directory=str(analysis.analysis_directory),
        summary_json_file=str(summary_path),
        executable_path=str(reconstruction.program.executable_path),
        executable_version=reconstruction.program.version,
        clustering_algorithm=reconstruction.clustering_algorithm,
        command=command,
    )

    try:
        # Launch the binary and wait for it. shell=False avoids shell parsing;
        # check=False lets us inspect the exit code ourselves below.
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
                raw_file,
                command,
                elapsed_seconds,
                error=str(exc),
            )
            raise HermesReconstructionExecutionError(
                f"failed to launch clusterer for {raw_file.path}: {exc}"
            ) from exc

        elapsed_seconds = perf_counter() - started
        stdout_excerpt = _bounded_text(process.stdout)
        stderr_excerpt = _bounded_text(process.stderr)
        if process.returncode != 0:
            _log_process_failure(
                raw_file,
                command,
                elapsed_seconds,
                error=f"clusterer exited with code {process.returncode}",
                exit_code=process.returncode,
                stdout_excerpt=stdout_excerpt,
                stderr_excerpt=stderr_excerpt,
            )
            raise HermesReconstructionExecutionError(
                f"clusterer exited with code {process.returncode} for "
                f"{raw_file.path}"
            )

        # The binary exited cleanly; now confirm the output it left behind is
        # complete and matches what we asked for before trusting it.
        summary: Tpx3PhotonReconstructionSummary | None = None
        try:
            summary = _load_summary(summary_path)
            if (
                summary.clustering.algorithm != reconstruction.clustering_algorithm
                or summary.clustering.settings != reconstruction.settings
            ):
                raise HermesReconstructionOutputError(
                    "reconstruction summary settings do not match the requested settings: "
                    f"{summary_path}"
                )
            _validate_completed_files(
                summary,
                summary_path,
                analysis.analysis_directory,
                raw_file.path.stem,
            )
        except HermesReconstructionError as exc:
            _log_process_failure(
                raw_file,
                command,
                elapsed_seconds,
                error=str(exc),
                exit_code=process.returncode,
                stdout_excerpt=stdout_excerpt,
                stderr_excerpt=stderr_excerpt,
                summary=(
                    summary.model_dump(mode="json")
                    if summary is not None
                    else None
                ),
            )
            raise
    finally:
        # Always remove the temporary settings file, even if the run failed.
        settings_file.unlink(missing_ok=True)

    _ANALYSIS_LOGGER.info(
        "analysis.tpx3_reconstruction.completed",
        event_type="analysis.tpx3_reconstruction.completed",
        raw_tpx3_file=str(raw_file.path),
        analysis_directory=str(analysis.analysis_directory),
        summary_json_file=str(summary_path),
        command=command,
        exit_code=process.returncode,
        elapsed_seconds=elapsed_seconds,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        photon_count=summary.reconstruction.photon_count,
        rejected_component_count=summary.reconstruction.rejected_component_count,
    )
    return summary


def log_skipped_input(
    analysis: HermesTpx3AnalysisState,
    raw_file: FileReference,
) -> None:
    """Log that one raw file was skipped because valid results already exist."""
    _ANALYSIS_LOGGER.info(
        "analysis.tpx3_reconstruction.skipped",
        event_type="analysis.tpx3_reconstruction.skipped",
        raw_tpx3_file=str(raw_file.path),
        analysis_directory=str(analysis.analysis_directory),
        summary_json_file=str(derive_summary_path(analysis, raw_file)),
        reason="valid summary and photon files already exist",
    )


def log_overall_completion(
    *,
    raw_file_count: int,
    reconstructed_file_count: int,
) -> None:
    """Log a summary line once every raw file has been handled."""
    _ANALYSIS_LOGGER.info(
        "analysis.tpx3_reconstruction.completed",
        event_type="analysis.tpx3_reconstruction.completed",
        scope="all_raw_tpx3_files",
        raw_file_count=raw_file_count,
        reconstructed_file_count=reconstructed_file_count,
        skipped_file_count=raw_file_count - reconstructed_file_count,
    )


def log_overall_failure(error: Exception) -> None:
    """Log that the overall reconstruction run failed."""
    _ANALYSIS_LOGGER.error(
        "analysis.tpx3_reconstruction.failed",
        event_type="analysis.tpx3_reconstruction.failed",
        scope="all_raw_tpx3_files",
        error=str(error),
    )


def _require_reconstruction(
    analysis: HermesTpx3AnalysisState,
) -> Tpx3PhotonReconstructionConfiguration:
    """Return the reconstruction config, or raise if it is not set up."""
    reconstruction = analysis.photon_reconstruction
    if reconstruction is None:
        raise HermesReconstructionPreflightError(
            "photon reconstruction is not configured in the analysis state"
        )
    return reconstruction


def _validate_program_and_algorithm(
    reconstruction: Tpx3PhotonReconstructionConfiguration,
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
    """Read and parse a summary JSON file into a validated model object."""
    if not summary_path.is_file():
        raise HermesReconstructionPreflightError(
            f"summary path is not a regular file: {summary_path}"
        )
    try:
        return Tpx3PhotonReconstructionSummary.model_validate_json(
            summary_path.read_bytes()
        )
    except OSError as exc:
        raise HermesReconstructionPreflightError(
            f"cannot read summary JSON file: {summary_path}"
        ) from exc
    except ValidationError as exc:
        raise HermesReconstructionPreflightError(
            f"invalid summary JSON file: {summary_path}"
        ) from exc


def _validate_completed_files(
    summary: Tpx3PhotonReconstructionSummary,
    summary_path: Path,
    analysis_directory: Path,
    raw_file_stem: str,
) -> None:
    """Confirm the files the summary claims to have produced are real and sane.

    Guards against a summary that reports errors, lists files that are missing,
    misnamed, duplicated, or point outside the analysis directory, has row
    counts that disagree with the files, or leaves stray files on disk. Any of
    these raises HermesReconstructionOutputError.
    """
    if summary.reconstruction.errors:
        raise HermesReconstructionOutputError(
            f"summary reports reconstruction errors: {summary_path}"
        )

    # Used below to make sure no listed file escapes the analysis directory.
    analysis_root = analysis_directory.resolve()

    # photon_events is always written; photon_pixels only when it was requested.
    file_groups = [
        ("photon-events", summary.parquet.photon_events, True),
    ]
    if summary.parquet.photon_pixels.requested:
        file_groups.append(
            ("photon-pixels", summary.parquet.photon_pixels, True)
        )
    elif (
        summary.parquet.photon_pixels.files
        or summary.parquet.photon_pixels.row_count
    ):
        raise HermesReconstructionOutputError(
            f"summary lists photon_pixels output that was not requested: "
            f"{summary_path}"
        )

    listed_files: set[Path] = set()
    filename_pattern = re.compile(
        rf"^{re.escape(raw_file_stem)}-chip-(\d+)-(photon-events|photon-pixels)"
        rf"-part-(\d{{5}})\.parquet$"
    )
    # Check every file the summary lists: correct name, no duplicates, inside
    # the directory, and actually present on disk.
    for filename_marker, category, _always in file_groups:
        parts_by_chip: dict[int, list[int]] = {}
        for relative_path in category.files:
            filename_match = filename_pattern.fullmatch(relative_path.name)
            if (
                len(relative_path.parts) != 2
                or relative_path.parts[0] != "photons"
                or filename_match is None
                or filename_match.group(2) != filename_marker
            ):
                raise HermesReconstructionOutputError(
                    f"unexpected photon filename for {raw_file_stem}: "
                    f"{relative_path}"
                )
            if relative_path in listed_files:
                raise HermesReconstructionOutputError(
                    f"summary lists the same photon file more than once: "
                    f"{relative_path}"
                )

            chip_index = int(filename_match.group(1))
            part_index = int(filename_match.group(3))
            parts_by_chip.setdefault(chip_index, []).append(part_index)

            photon_path = analysis_directory / relative_path
            resolved_path = photon_path.resolve()
            if not resolved_path.is_relative_to(analysis_root):
                raise HermesReconstructionOutputError(
                    f"summary lists a photon file outside the analysis "
                    f"directory: {relative_path}"
                )
            if not photon_path.is_file():
                raise HermesReconstructionOutputError(
                    f"summary lists a missing photon file: {photon_path}"
                )
            listed_files.add(relative_path)

        # Each chip's parts must be numbered 0, 1, 2, ... with no gaps.
        for chip_index, part_indexes in parts_by_chip.items():
            if sorted(part_indexes) != list(range(len(part_indexes))):
                raise HermesReconstructionOutputError(
                    f"unexpected photon part numbers for {filename_marker} "
                    f"chip {chip_index}: {sorted(part_indexes)}"
                )

    # The photon_events row count must equal the recorded photon count.
    observed_events = 0
    for relative_path in summary.parquet.photon_events.files:
        photon_path = analysis_directory / relative_path
        try:
            observed_events += pq.read_metadata(photon_path).num_rows
        except Exception as exc:
            raise HermesReconstructionOutputError(
                f"cannot read photon Parquet metadata: {photon_path}"
            ) from exc
    if observed_events != summary.parquet.photon_events.row_count:
        raise HermesReconstructionOutputError(
            f"photon_events row count mismatch: "
            f"summary={summary.parquet.photon_events.row_count}, "
            f"files={observed_events}"
        )

    # Every photon file on disk for this stem must be listed in the summary.
    matching_files = {
        path.relative_to(analysis_directory)
        for path in _matching_photon_files(
            analysis_directory / "photons",
            raw_file_stem,
        )
    }
    if matching_files != listed_files:
        unexpected = sorted(str(path) for path in matching_files - listed_files)
        missing = sorted(str(path) for path in listed_files - matching_files)
        raise HermesReconstructionOutputError(
            f"summary photon file list does not match files for "
            f"{raw_file_stem}; unexpected={unexpected}, missing={missing}"
        )


def _matching_photon_files(
    photon_output_directory: Path,
    raw_file_stem: str,
) -> list[Path]:
    """List the photon files on disk that belong to one raw file."""
    if not photon_output_directory.is_dir():
        return []
    pattern = f"{raw_file_stem}-*.parquet"
    return sorted(photon_output_directory.glob(pattern))


def _bounded_text(text: str) -> str:
    """Trim text so a single log entry cannot grow without bound."""
    return text[:_LOG_TEXT_LIMIT]


def _log_process_failure(
    raw_file: FileReference,
    command: list[str],
    elapsed_seconds: float,
    *,
    error: str,
    exit_code: int | None = None,
    stdout_excerpt: str = "",
    stderr_excerpt: str = "",
    summary: dict[str, object] | None = None,
) -> None:
    """Log a failure for one raw file with the command output for debugging."""
    _ANALYSIS_LOGGER.error(
        "analysis.tpx3_reconstruction.failed",
        event_type="analysis.tpx3_reconstruction.failed",
        raw_tpx3_file=str(raw_file.path),
        command=command,
        exit_code=exit_code,
        elapsed_seconds=elapsed_seconds,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        summary=summary,
        error=error,
    )
