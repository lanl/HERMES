"""Runs the C++ event reconstruction binary over reconstructed photon data.

Event reconstruction is whole-sensor: every chip's photon files for one raw TPX3
filename stem are clustered together in the shared sensor frame, producing one
event set per raw stem. execute_event_reconstruction runs the binary on one raw
stem and reads its summary JSON for that stem's counts.
execute_event_reconstruction_batch runs many stems in one process, handing the
binary the exact photon paths so it never scans the photons directory, and reads
each stem's summary JSON on its own.
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
    HermesTpx3EventReconstructionResult,
    HermesTpx3EventReconstruction,
    HermesTpx3EventReconstructionSummary,
)
from hermes.state.models.shared_models import FileReference
from hermes.runner.analysis.executables import (
    resolve_executable,
    single_thread_environment,
)

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


def _parse_photon_file_name(input_file: FileReference) -> str:
    """Return the raw TPX3 filename stem a photon file belongs to.

    The photon stage names photon files
    ``<raw-file-stem>_chip_<chip>_photon_<part>.parquet``. Whole-sensor event
    reconstruction groups every chip and part of one raw stem together, so only
    the raw stem is needed. This mirrors the photon stage's own filename parsing.
    """
    stem = input_file.path.stem
    chip_position = stem.find("_chip_")
    photon_position = stem.rfind("_photon_")
    if (
        chip_position == -1
        or photon_position == -1
        or photon_position < chip_position
    ):
        raise HermesEventReconstructionPreflightError(
            f"photon filename does not match "
            f"<stem>_chip_<chip>_photon_<part>.parquet: {input_file.path}"
        )
    raw_file_stem = stem[:chip_position]
    chip_label = stem[chip_position + len("_chip_") : photon_position]
    part_index = stem[photon_position + len("_photon_") :]
    if not raw_file_stem or not chip_label or not part_index:
        raise HermesEventReconstructionPreflightError(
            f"photon filename does not match "
            f"<stem>_chip_<chip>_photon_<part>.parquet: {input_file.path}"
        )
    return raw_file_stem


def group_photon_files_by_stem(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
) -> dict[str, list[Path]]:
    """Return each raw TPX3 filename stem mapped to its photon files.

    ``photon_parquet_files == "auto"`` scans the photon stage's ``photons``
    directory once; an explicit list is used as-is. Every photon filename is
    parsed for its raw stem, and each file is grouped under the stem it belongs
    to. Event reconstruction is whole-sensor, so a stem's several chips and parts
    collapse into one group, and each group is sorted so parts are read in a
    stable order. The batch run hands the binary exactly these paths, so it never
    scans the ``photons`` directory itself.
    """
    event_reconstruction = _require_event_reconstruction(analysis)
    if event_reconstruction.photon_parquet_files != "auto":
        photon_files = list(event_reconstruction.photon_parquet_files)
    else:
        photon_directory = analysis_root / "photons"
        if not photon_directory.is_dir():
            return {}
        photon_files = [
            FileReference(path=path)
            for path in photon_directory.glob("*.parquet")
        ]
    grouping: dict[str, list[Path]] = {}
    for photon_file in photon_files:
        raw_file_stem = _parse_photon_file_name(photon_file)
        grouping.setdefault(raw_file_stem, []).append(photon_file.path)
    for photon_paths in grouping.values():
        photon_paths.sort()
    return grouping


def resolve_raw_file_stems(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
) -> list[str]:
    """Return the raw TPX3 filename stems event reconstruction should run over.

    The sorted, unique stems of every photon file, so a stem's several chips and
    parts collapse to one run.
    """
    return sorted(group_photon_files_by_stem(analysis, analysis_root))


def derive_output_path(
    analysis_root: Path,
    raw_file_stem: str,
) -> Path:
    """Return the event_candidates file path for one raw stem.

    The whole sensor is reconstructed together, so there is one file per raw
    stem in an ``events`` directory under the analysis directory, named
    ``<raw-file-stem>_event_candidates.parquet``.
    """
    return analysis_root / "events" / f"{raw_file_stem}_event_candidates.parquet"


def check_previous_reconstructed_file(
    analysis_root: Path,
    raw_file_stem: str,
) -> bool:
    """Return True when this raw stem was already reconstructed before.

    The binary writes a per-stem reconstruction summary on every success
    (including zero-event runs that produce no event parquet), so its presence
    means the stem is already done.
    """
    return derive_summary_path(analysis_root, raw_file_stem).is_file()


def derive_summary_path(
    analysis_root: Path,
    raw_file_stem: str,
) -> Path:
    """Return the reconstruction-summary JSON file path written by the binary.

    The binary writes one summary per raw stem to a
    ``logs/event_reconstruction`` directory under the analysis directory (the
    photon stage writes to ``logs/photon_reconstruction``), named
    ``<raw-file-stem>_event_reconstruction_summary.json``.
    """
    return (
        analysis_root
        / "logs"
        / "event_reconstruction"
        / f"{raw_file_stem}_event_reconstruction_summary.json"
    )


def derive_event_reconstruction_command(
    event_reconstruction: HermesTpx3EventReconstruction,
    analysis_root: Path,
    raw_file_stem: str,
    settings_file: Path,
    *,
    overwrite: bool = False,
) -> list[str]:
    """Build the command line that launches the event reconstruction binary.

    ``--input`` is the analysis directory; the binary gathers that stem's photon
    files, clusters them in the shared sensor frame, and writes events/,
    event_photons/, and logs/event_reconstruction/ beneath it.
    """
    command = [
        str(event_reconstruction.program.executable_path),
        "--input",
        str(analysis_root),
        "--raw-file-stem",
        raw_file_stem,
        "--settings",
        str(settings_file),
    ]
    if overwrite:
        command.append("--overwrite")
    return command


def execute_event_reconstruction(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
    raw_file_stem: str,
    *,
    overwrite: bool = False,
) -> HermesTpx3EventReconstructionResult:
    """Run the binary on one raw stem and return its whole-sensor result.

    Raises a HermesEventReconstructionError if the binary fails to launch, exits
    with an error, or leaves no readable summary.
    """
    event_reconstruction = _require_event_reconstruction(analysis)
    output_file = derive_output_path(analysis_root, raw_file_stem)
    summary_path = derive_summary_path(analysis_root, raw_file_stem)
    started = perf_counter()

    # The complete event settings go to the binary in a temporary JSON file; the
    # field names match the binary's settings keys. The binary reads the detector
    # layout from the photon files' metadata, so it is not passed here.
    settings_json = event_reconstruction.settings.model_dump(mode="json")
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=f"{raw_file_stem}-event-settings-",
        delete=False,
    ) as settings_stream:
        json.dump(settings_json, settings_stream)
        settings_file = Path(settings_stream.name)

    command = derive_event_reconstruction_command(
        event_reconstruction,
        analysis_root,
        raw_file_stem,
        settings_file,
        overwrite=overwrite,
    )
    _ANALYSIS_LOGGER.info(
        "Reconstructing events for {raw_file_stem}",
        event_type="analysis.tpx3_event_reconstruction.started",
        raw_file_stem=raw_file_stem,
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
                env=single_thread_environment(),
            )
        except OSError as exc:
            elapsed_seconds = perf_counter() - started
            _log_process_failure(
                raw_file_stem,
                command,
                elapsed_seconds,
                error=str(exc),
            )
            raise HermesEventReconstructionExecutionError(
                f"failed to launch event reconstructor for {raw_file_stem}: "
                f"{exc}"
            ) from exc

        elapsed_seconds = perf_counter() - started
        stdout_excerpt = _bounded_text(process.stdout)
        stderr_excerpt = _bounded_text(process.stderr)
        if process.returncode != 0:
            _log_process_failure(
                raw_file_stem,
                command,
                elapsed_seconds,
                error=f"event reconstructor exited with code {process.returncode}",
                exit_code=process.returncode,
                stdout_excerpt=stdout_excerpt,
                stderr_excerpt=stderr_excerpt,
            )
            raise HermesEventReconstructionExecutionError(
                f"event reconstructor exited with code {process.returncode} for "
                f"{raw_file_stem}"
            )

        summary = _load_summary(summary_path)
    finally:
        settings_file.unlink(missing_ok=True)

    _ANALYSIS_LOGGER.info(
        "Reconstructed events for {raw_file_stem} in {elapsed_seconds:.2f}s: "
        "{event_count} events",
        event_type="analysis.tpx3_event_reconstruction.completed",
        raw_file_stem=raw_file_stem,
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
        raw_file_stem=raw_file_stem,
        output_file=output_file,
        status="completed",
        counts=summary.reconstruction,
    )


def derive_batch_event_reconstruction_command(
    event_reconstruction: HermesTpx3EventReconstruction,
    analysis_root: Path,
    list_path: Path,
    settings_file: Path,
    *,
    overwrite: bool = False,
) -> list[str]:
    """Build the command that reconstructs every listed photon file in one run.

    Identical to ``derive_event_reconstruction_command`` except it passes
    ``--input-list`` (a file of photon paths the binary groups back by raw stem)
    instead of ``--raw-file-stem``; ``--input`` is still the analysis directory
    the events/, event_photons/, and logs/event_reconstruction/ outputs go under.
    """
    command = [
        str(event_reconstruction.program.executable_path),
        "--input",
        str(analysis_root),
        "--input-list",
        str(list_path),
        "--settings",
        str(settings_file),
    ]
    if overwrite:
        command.append("--overwrite")
    return command


def execute_event_reconstruction_batch(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
    raw_file_stems: list[str],
    grouping: dict[str, list[Path]],
    *,
    overwrite: bool = False,
) -> list[HermesTpx3EventReconstructionResult | None]:
    """Reconstruct a group of raw stems in one subprocess; report each result.

    The binary reads the group's photon paths from a temporary list file, groups
    them back by raw stem, and reconstructs each stem in sequence, so the cost of
    starting the process and loading its Arrow/Parquet libraries is paid once for
    the whole group instead of once per stem. Each stem's success is decided from
    its own summary JSON, never the process exit code: a stem whose summary is
    present is reconstructed; any other stem — missing summary, including a stem
    the process never reached because it died partway — is failed, and a resume
    re-runs it. Returns one entry per input stem, in the given order: its result
    when reconstructed, or ``None`` when failed.
    """
    event_reconstruction = _require_event_reconstruction(analysis)

    # The complete event settings go to the binary in a temporary JSON file, and
    # the group's photon paths go in a temporary list file; both are removed once
    # the process finishes.
    settings_json = event_reconstruction.settings.model_dump(mode="json")
    settings_stream = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="hermes_event_batch_settings_",
        delete=False,
    )
    list_file = tempfile.NamedTemporaryFile(
        "w",
        suffix=".txt",
        prefix="hermes_event_batch_",
        delete=False,
    )
    try:
        json.dump(settings_json, settings_stream)
        settings_stream.close()
        settings_file = Path(settings_stream.name)

        photon_paths = [
            str(path)
            for raw_file_stem in raw_file_stems
            for path in grouping.get(raw_file_stem, [])
        ]
        list_file.write("\n".join(photon_paths))
        list_file.close()

        command = derive_batch_event_reconstruction_command(
            event_reconstruction,
            analysis_root,
            Path(list_file.name),
            settings_file,
            overwrite=overwrite,
        )
        started = perf_counter()
        _ANALYSIS_LOGGER.info(
            "Reconstructing events for {stem_count} raw stem(s) in one process",
            event_type="analysis.tpx3_event_reconstruction.batch_started",
            stem_count=len(raw_file_stems),
            analysis_directory=str(analysis_root),
            executable_path=str(event_reconstruction.program.executable_path),
            executable_version=event_reconstruction.program.version,
            clustering_algorithm=event_reconstruction.clustering_algorithm,
            command=command,
        )
        try:
            process = subprocess.run(
                command,
                shell=False,
                capture_output=True,
                text=True,
                check=False,
                env=single_thread_environment(),
            )
        except OSError as exc:
            elapsed_seconds = perf_counter() - started
            for raw_file_stem in raw_file_stems:
                _log_process_failure(
                    raw_file_stem,
                    command,
                    elapsed_seconds,
                    error=f"failed to launch event reconstructor: {exc}",
                )
            return [None] * len(raw_file_stems)

        elapsed_seconds = perf_counter() - started
        stderr_excerpt = _bounded_text(process.stderr)
        return [
            _confirm_reconstructed_stem(
                analysis_root,
                raw_file_stem,
                command,
                elapsed_seconds,
                exit_code=process.returncode,
                stderr_excerpt=stderr_excerpt,
            )
            for raw_file_stem in raw_file_stems
        ]
    finally:
        Path(settings_stream.name).unlink(missing_ok=True)
        Path(list_file.name).unlink(missing_ok=True)


def _confirm_reconstructed_stem(
    analysis_root: Path,
    raw_file_stem: str,
    command: list[str],
    elapsed_seconds: float,
    *,
    exit_code: int | None,
    stderr_excerpt: str,
) -> HermesTpx3EventReconstructionResult | None:
    """Return a stem's result if it reconstructed cleanly, else ``None``, logged.

    Called once per stem after its batch process finishes, to decide that stem's
    result from its own summary rather than the process's shared exit code.
    """
    output_file = derive_output_path(analysis_root, raw_file_stem)
    summary_path = derive_summary_path(analysis_root, raw_file_stem)
    try:
        summary = _load_summary(summary_path)
    except HermesEventReconstructionError as exc:
        _log_process_failure(
            raw_file_stem,
            command,
            elapsed_seconds,
            error=str(exc),
            exit_code=exit_code,
            stderr_excerpt=stderr_excerpt,
        )
        return None

    _ANALYSIS_LOGGER.info(
        "Reconstructed events for {raw_file_stem}: {event_count} events",
        event_type="analysis.tpx3_event_reconstruction.completed",
        raw_file_stem=raw_file_stem,
        output_file=str(output_file),
        summary_json_file=str(summary_path),
        exit_code=exit_code,
        event_count=summary.reconstruction.event_count,
        photons_read=summary.reconstruction.photons_read,
    )
    return HermesTpx3EventReconstructionResult(
        raw_file_stem=raw_file_stem,
        output_file=output_file,
        status="completed",
        counts=summary.reconstruction,
    )


def log_skipped_input(
    raw_file_stem: str,
    output_file: Path,
) -> None:
    """Log that one raw stem was skipped because its summary already exists."""
    _ANALYSIS_LOGGER.warning(
        "Skipped {raw_file_stem}: valid outputs already exist",
        event_type="analysis.tpx3_event_reconstruction.skipped",
        raw_file_stem=raw_file_stem,
        output_file=str(output_file),
        reason="valid reconstruction summary already exists",
    )


def log_overall_completion(
    *,
    raw_file_stem_count: int,
    reconstructed_stem_count: int,
    failed_stem_count: int,
) -> None:
    """Log a summary line once every raw stem has been handled."""
    _ANALYSIS_LOGGER.info(
        "Event reconstruction finished: {reconstructed_stem_count} "
        "reconstructed, {skipped_stem_count} skipped, {failed_stem_count} "
        "failed of {raw_file_stem_count} raw file stems",
        event_type="analysis.tpx3_event_reconstruction.completed",
        scope="all_raw_file_stems",
        raw_file_stem_count=raw_file_stem_count,
        reconstructed_stem_count=reconstructed_stem_count,
        failed_stem_count=failed_stem_count,
        skipped_stem_count=(
            raw_file_stem_count - reconstructed_stem_count - failed_stem_count
        ),
    )


def log_overall_failure(error: Exception) -> None:
    """Log that the overall event reconstruction run failed."""
    _ANALYSIS_LOGGER.error(
        "Event reconstruction failed: {error}",
        event_type="analysis.tpx3_event_reconstruction.failed",
        scope="all_raw_file_stems",
        error=str(error),
    )


def _require_event_reconstruction(
    analysis: HermesTpx3AnalysisState,
) -> HermesTpx3EventReconstruction:
    """Return the event reconstruction config, or raise if it is not set up."""
    event_reconstruction = analysis.event_reconstruction
    if event_reconstruction is None:
        raise HermesEventReconstructionPreflightError(
            "event reconstruction is not configured in the analysis state"
        )
    return event_reconstruction


def validate_program_and_algorithm(
    event_reconstruction: HermesTpx3EventReconstruction,
) -> None:
    """Check the algorithm is supported and the binary exists before running."""
    if event_reconstruction.clustering_algorithm != "connected_components":
        raise HermesEventReconstructionPreflightError(
            f"clustering_algorithm={event_reconstruction.clustering_algorithm!r} "
            "is not implemented; only 'connected_components' is available"
        )
    executable = event_reconstruction.program.executable_path
    try:
        resolve_executable(executable)
    except (FileNotFoundError, PermissionError) as exc:
        raise HermesEventReconstructionPreflightError(
            f"event reconstructor executable does not exist: {executable}"
        ) from exc


def _load_summary(summary_path: Path) -> HermesTpx3EventReconstructionSummary:
    """Read and parse a reconstruction-summary JSON file into a model object."""
    if not summary_path.is_file():
        raise HermesEventReconstructionOutputError(
            f"reconstruction summary is missing: {summary_path}"
        )
    try:
        return HermesTpx3EventReconstructionSummary.model_validate_json(
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
    raw_file_stem: str,
    command: list[str],
    elapsed_seconds: float,
    *,
    error: str,
    exit_code: int | None = None,
    stdout_excerpt: str = "",
    stderr_excerpt: str = "",
) -> None:
    """Log a failure for one raw stem with the command output for debugging."""
    message = "Reconstructing events for {raw_file_stem} failed: {error}"
    if stderr_excerpt:
        message += "\nstderr: {stderr_excerpt}"
    _ANALYSIS_LOGGER.error(
        message,
        event_type="analysis.tpx3_event_reconstruction.failed",
        raw_file_stem=raw_file_stem,
        command=command,
        exit_code=exit_code,
        elapsed_seconds=elapsed_seconds,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        error=error,
    )
