from __future__ import annotations

import os
import re
import subprocess
import tempfile
from time import perf_counter
from pathlib import Path

from loguru import logger
from pydantic import ValidationError

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3SpidrSummary,
)
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import FileReference
from hermes.runner.analysis.executables import (
    newer_source_than_binary,
    resolve_executable,
    single_thread_environment,
)

# The unpacker's C++ source in a source checkout (repo/src/backends/...). An
# editable install compiles the deployed binary from here, so the preflight
# compares the binary against these files to catch a binary that was not rebuilt
# after an edit. A wheel install has no source here and the check is skipped.
_UNPACKER_CPP_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "backends"
    / "unpackers"
    / "tpx3-spidr"
    / "cpp"
)

# Each Parquet category directory and the filename label the unpacker uses in it.
# Pixel files are named "<stem>_chip_<chip>_pixels_<part>.parquet"; every other
# category is named "<stem>_<label>_<part>.parquet".
_PARQUET_DIRECTORY_LABELS = {
    "pixel_hits": None,
    "tdc_triggers": "tdc_triggers",
    "global_timestamps": "global_timestamps",
    "control_packets": "control_packets",
    "unrecognized_packets": "unrecognized_packets",
}
# TDC triggers are written one file per channel+edge that occurs, so the
# tdc_triggers directory holds up to four differently labeled filenames.
_TDC_TRIGGER_LABELS = (
    "tdc1_rising_triggers",
    "tdc1_falling_triggers",
    "tdc2_rising_triggers",
    "tdc2_falling_triggers",
)
# Filename patterns matched against the part of each Parquet filename that
# follows the "<stem>_" prefix. The raw file stem varies from file to file, so
# it is checked as a literal prefix and stripped off, which lets these patterns
# be compiled once here instead of once per file. Validation runs over tens of
# thousands of files, and recompiling these patterns per file otherwise
# dominated its cost.
_PIXEL_SUFFIX_PATTERN = re.compile(r"^chip_(\d+)_pixels_(\d{5})\.parquet$")
_TDC_SUFFIX_PATTERN = re.compile(
    r"^("
    + "|".join(re.escape(label) for label in _TDC_TRIGGER_LABELS)
    + r")_(\d{5})\.parquet$"
)
_LABEL_SUFFIX_PATTERNS = {
    directory: re.compile(rf"^{re.escape(label)}_(\d{{5}})\.parquet$")
    for directory, label in _PARQUET_DIRECTORY_LABELS.items()
    if label is not None and directory != "tdc_triggers"
}
_LOG_TEXT_LIMIT = 4_000
_ANALYSIS_LOGGER = logger.bind(
    domain="analysis",
    mode="hermes",
    step="tpx3_spidr_unpacking",
)


class HermesTpx3Error(Exception):
    """Base exception for HERMES TPX3 SPIDR unpacking failures."""


class HermesTpx3PreflightError(HermesTpx3Error):
    """Raised when HERMES cannot safely start or continue unpacking."""


class HermesTpx3ExecutionError(HermesTpx3Error):
    """Raised when the unpacker process cannot complete successfully."""


class HermesTpx3OutputError(HermesTpx3PreflightError):
    """Raised when unpacker output is missing, unsafe, or inconsistent."""


def resolve_tpx3_files(
    analysis: HermesTpx3AnalysisState,
    raw_data_directory: Path | None,
) -> list[FileReference]:
    """Return the raw TPX3 files unpacking should run over.

    ``tpx3_files == "auto"`` gathers every ``*.tpx3`` in the run's raw data
    directory; an explicit list is used as-is.
    """
    tpx3_files = analysis.unpacking.tpx3_files
    if tpx3_files != "auto":
        return list(tpx3_files)
    if raw_data_directory is None or not raw_data_directory.is_dir():
        return []
    return [
        FileReference(path=path)
        for path in sorted(raw_data_directory.glob("*.tpx3"))
    ]


def derive_summary_path(
    analysis_root: Path,
    raw_file: FileReference,
) -> Path:
    return (
        analysis_root
        / "logs"
        / "unpacking"
        / f"{raw_file.path.stem}_unpacker_summary.json"
    )


def check_previous_unpacked_file(
    analysis_root: Path,
    raw_file: FileReference,
) -> bool:
    """Return True when this raw file was already unpacked with valid outputs."""
    summary_path = derive_summary_path(analysis_root, raw_file)
    if not summary_path.is_file():
        return False
    summary = _load_summary(summary_path)
    _validate_completed_files(summary, summary_path, analysis_root, raw_file.path.stem)
    return True

def derive_unpacker_command(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
    raw_file: FileReference,
    measurement_info: MeasurementInfo,
    *,
    overwrite: bool = False,
) -> list[str]:
    command = [
        str(analysis.unpacking.program.executable_path),
        "--input",
        str(raw_file.path),
        "--output",
        str(analysis_root),
        "--measurement-id",
        measurement_info.measurement_id,
        "--run",
        measurement_info.run,
    ]
    if overwrite:
        command.append("--overwrite")
    if not analysis.unpacking.runtime_options.time_sort:
        command.extend(["--time-sort", "false"])
    return command

def execute_unpacker(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
    raw_file: FileReference,
    measurement_info: MeasurementInfo,
    *,
    overwrite: bool = False,
) -> Tpx3SpidrSummary:
    command = derive_unpacker_command(
        analysis, analysis_root, raw_file, measurement_info, overwrite=overwrite
    )
    summary_path = derive_summary_path(analysis_root, raw_file)
    resolved_executable_path = resolve_executable(
        analysis.unpacking.program.executable_path
    )
    started = perf_counter()
    _ANALYSIS_LOGGER.info(
        "Unpacking {raw_tpx3_file} (time_sort={time_sort})",
        event_type="analysis.tpx3_unpacking.started",
        raw_tpx3_file=str(raw_file.path),
        raw_tpx3_size_bytes=raw_file.path.stat().st_size,
        analysis_directory=str(analysis_root),
        summary_json_file=str(summary_path),
        executable_path=str(analysis.unpacking.program.executable_path),
        resolved_executable_path=str(resolved_executable_path),
        executable_version=analysis.unpacking.program.version,
        time_sort=analysis.unpacking.runtime_options.time_sort,
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
        _log_process_failure(
            raw_file,
            command,
            elapsed_seconds,
            error=str(exc),
        )
        raise HermesTpx3ExecutionError(
            f"failed to launch unpacker for {raw_file.path}: {exc}"
        ) from exc

    elapsed_seconds = perf_counter() - started
    stdout_excerpt = _bounded_text(process.stdout)
    stderr_excerpt = _bounded_text(process.stderr)
    if process.returncode != 0:
        _log_process_failure(
            raw_file,
            command,
            elapsed_seconds,
            error=f"unpacker exited with code {process.returncode}",
            exit_code=process.returncode,
            stdout_excerpt=stdout_excerpt,
            stderr_excerpt=stderr_excerpt,
        )
        raise HermesTpx3ExecutionError(
            f"unpacker exited with code {process.returncode} for {raw_file.path}"
        )

    summary: Tpx3SpidrSummary | None = None
    try:
        summary = _load_summary(summary_path)
        _validate_completed_files(
            summary,
            summary_path,
            analysis_root,
            raw_file.path.stem,
        )
    except HermesTpx3Error as exc:
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

    _warn_if_timestamps_unanchored(raw_file, summary)
    _ANALYSIS_LOGGER.info(
        "Unpacked {raw_tpx3_file} in {elapsed_seconds:.2f}s",
        event_type="analysis.tpx3_unpacking.completed",
        raw_tpx3_file=str(raw_file.path),
        analysis_directory=str(analysis_root),
        summary_json_file=str(summary_path),
        command=command,
        exit_code=process.returncode,
        elapsed_seconds=elapsed_seconds,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        summary=summary.model_dump(mode="json"),
    )
    return summary


def derive_batch_unpacker_command(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
    list_path: Path,
    measurement_info: MeasurementInfo,
    *,
    overwrite: bool = False,
) -> list[str]:
    """Command that unpacks every raw file listed in ``list_path`` in one run.

    Identical to ``derive_unpacker_command`` except it passes ``--input-list``
    instead of ``--input``; every other option is per-run, not per-file, so it
    is the same for the whole group.
    """
    command = [
        str(analysis.unpacking.program.executable_path),
        "--input-list",
        str(list_path),
        "--output",
        str(analysis_root),
        "--measurement-id",
        measurement_info.measurement_id,
        "--run",
        measurement_info.run,
    ]
    if overwrite:
        command.append("--overwrite")
    if not analysis.unpacking.runtime_options.time_sort:
        command.extend(["--time-sort", "false"])
    return command


def execute_unpacker_batch(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
    raw_files: list[FileReference],
    measurement_info: MeasurementInfo,
    *,
    overwrite: bool = False,
) -> list[Tpx3SpidrSummary | None]:
    """Unpack a group of raw files in one subprocess; report each file's result.

    The binary reads the group's paths from a temporary list file and unpacks
    them in sequence, so the cost of starting the process and loading its
    Arrow/Parquet libraries is paid once for the whole group instead of once per
    file. Each file's success is decided from its own summary JSON, never the
    process exit code: a file whose summary is present and lists valid Parquet
    output is unpacked; any other file — missing or invalid summary, including a
    file the process never reached because it died partway — is failed, and a
    resume re-runs it. Returns one entry per input file, in the given order: its
    summary when unpacked, or ``None`` when failed.
    """
    resolved_executable_path = resolve_executable(
        analysis.unpacking.program.executable_path
    )
    list_file = tempfile.NamedTemporaryFile(
        "w",
        suffix=".txt",
        prefix="hermes_unpack_batch_",
        delete=False,
    )
    try:
        list_file.write(
            "\n".join(str(raw_file.path) for raw_file in raw_files)
        )
        list_file.close()
        command = derive_batch_unpacker_command(
            analysis,
            analysis_root,
            Path(list_file.name),
            measurement_info,
            overwrite=overwrite,
        )
        started = perf_counter()
        _ANALYSIS_LOGGER.info(
            "Unpacking {file_count} raw TPX3 file(s) in one process "
            "(time_sort={time_sort})",
            event_type="analysis.tpx3_unpacking.batch_started",
            file_count=len(raw_files),
            analysis_directory=str(analysis_root),
            executable_path=str(analysis.unpacking.program.executable_path),
            resolved_executable_path=str(resolved_executable_path),
            time_sort=analysis.unpacking.runtime_options.time_sort,
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
            for raw_file in raw_files:
                _log_process_failure(
                    raw_file,
                    command,
                    elapsed_seconds,
                    error=f"failed to launch unpacker: {exc}",
                )
            return [None] * len(raw_files)

        elapsed_seconds = perf_counter() - started
        stderr_excerpt = _bounded_text(process.stderr)
        return [
            _confirm_unpacked_file(
                analysis_root,
                raw_file,
                command,
                elapsed_seconds,
                exit_code=process.returncode,
                stderr_excerpt=stderr_excerpt,
            )
            for raw_file in raw_files
        ]
    finally:
        Path(list_file.name).unlink(missing_ok=True)


def _confirm_unpacked_file(
    analysis_root: Path,
    raw_file: FileReference,
    command: list[str],
    elapsed_seconds: float,
    *,
    exit_code: int | None,
    stderr_excerpt: str,
) -> Tpx3SpidrSummary | None:
    """Return a file's summary if it unpacked cleanly, else ``None``, and log it.

    Called once per file after its batch process finishes, to decide that file's
    result from its own summary rather than the process's shared exit code.
    """
    summary_path = derive_summary_path(analysis_root, raw_file)
    try:
        summary = _load_summary(summary_path)
        _validate_completed_files(
            summary,
            summary_path,
            analysis_root,
            raw_file.path.stem,
        )
    except HermesTpx3Error as exc:
        _log_process_failure(
            raw_file,
            command,
            elapsed_seconds,
            error=str(exc),
            exit_code=exit_code,
            stderr_excerpt=stderr_excerpt,
        )
        return None

    _warn_if_timestamps_unanchored(raw_file, summary)
    _ANALYSIS_LOGGER.info(
        "Unpacked {raw_tpx3_file}",
        event_type="analysis.tpx3_unpacking.completed",
        raw_tpx3_file=str(raw_file.path),
        analysis_directory=str(analysis_root),
        summary_json_file=str(summary_path),
        exit_code=exit_code,
        summary=summary.model_dump(mode="json"),
    )
    return summary


def log_skipped_input(
    analysis_root: Path,
    raw_file: FileReference,
) -> None:
    _ANALYSIS_LOGGER.warning(
        "Skipped {raw_tpx3_file}: valid outputs already exist",
        event_type="analysis.tpx3_unpacking.skipped",
        raw_tpx3_file=str(raw_file.path),
        analysis_directory=str(analysis_root),
        summary_json_file=str(derive_summary_path(analysis_root, raw_file)),
        reason="valid summary and listed Parquet files already exist",
    )


def log_overall_completion(
    *,
    raw_file_count: int,
    unpacked_file_count: int,
    failed_file_count: int,
) -> None:
    _ANALYSIS_LOGGER.info(
        "Unpacking finished: {unpacked_file_count} unpacked, "
        "{skipped_file_count} skipped, {failed_file_count} failed of "
        "{raw_file_count} raw files",
        event_type="analysis.tpx3_unpacking.completed",
        scope="all_raw_tpx3_files",
        raw_file_count=raw_file_count,
        unpacked_file_count=unpacked_file_count,
        failed_file_count=failed_file_count,
        skipped_file_count=(
            raw_file_count - unpacked_file_count - failed_file_count
        ),
    )


def log_overall_failure(error: Exception) -> None:
    _ANALYSIS_LOGGER.error(
        "Unpacking failed: {error}",
        event_type="analysis.tpx3_unpacking.failed",
        scope="all_raw_tpx3_files",
        error=str(error),
    )


def _warn_if_timestamps_unanchored(
    raw_file: FileReference,
    summary: Tpx3SpidrSummary,
) -> None:
    """Warn when a file's timestamps had no global timestamps to anchor to.

    Unpacking recovers each clock counter's missing high bits by comparing it to
    the run's global timestamps, which are matched to each chip on its own.
    ``failed`` counts the counters that found no global timestamp to anchor to,
    so they are left folded near zero and no longer share one comparable axis
    with the rest. When the file has no global timestamps at all this almost
    always means GlobalTimestampInterval was not enabled during acquisition;
    when it has some but not for every chip, only the chips without one of their
    own are affected.
    """
    failed = summary.timestamp_processing.time_adjustments.failed
    if failed == 0:
        return
    beats = summary.timestamp_processing.heartbeat_pairs.number_of_beats
    if beats == 0:
        hint = "Check that GlobalTimestampInterval was enabled during acquisition."
    else:
        hint = (
            "This file has global timestamps but not for every chip, so the "
            "chips without one of their own could not be anchored."
        )
    _ANALYSIS_LOGGER.warning(
        "{raw_tpx3_file}: {failed} timestamps had no global timestamps to anchor "
        "to ({beats} in this file); pixel, TDC, and event times may be off by "
        "whole clock wraps and are not comparable for time-of-flight. {hint}",
        event_type="analysis.tpx3_unpacking.timestamps_unanchored",
        raw_tpx3_file=str(raw_file.path),
        failed=failed,
        beats=beats,
        hint=hint,
    )


def validate_program_and_inputs(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
    raw_files: list[FileReference],
) -> None:
    executable = analysis.unpacking.program.executable_path
    try:
        resolved_executable_path = resolve_executable(executable)
    except (FileNotFoundError, PermissionError) as exc:
        raise HermesTpx3PreflightError(
            f"unpacker executable does not exist: {executable}; build the "
            "binary (e.g. via pixi) and set unpacking.program.executable_path"
        ) from exc

    stale_source = newer_source_than_binary(
        resolved_executable_path, _UNPACKER_CPP_SOURCE
    )
    if stale_source is not None:
        _ANALYSIS_LOGGER.warning(
            "Unpacker binary {binary} is older than its source file {source}; it "
            "was not rebuilt after the source changed and is running stale code. "
            "Rebuild it with `pixi reinstall hermes` before trusting the output.",
            event_type="analysis.tpx3_unpacking.binary_stale",
            binary=str(resolved_executable_path),
            source=str(stale_source),
        )

    for raw_file in raw_files:
        if not raw_file.path.is_file():
            raise HermesTpx3PreflightError(
                f"raw TPX3 file does not exist: {raw_file.path}"
            )

    analysis_directory = analysis_root
    if analysis_directory.exists():
        if not analysis_directory.is_dir():
            raise HermesTpx3PreflightError(
                f"analysis directory is not a directory: {analysis_directory}"
            )
        writable_directory = analysis_directory
    else:
        writable_directory = analysis_directory.parent
        while not writable_directory.exists():
            if writable_directory == writable_directory.parent:
                break
            writable_directory = writable_directory.parent

    if not writable_directory.is_dir() or not os.access(
        writable_directory,
        os.W_OK,
    ):
        raise HermesTpx3PreflightError(
            f"analysis directory cannot be created or written: "
            f"{analysis_directory}"
        )


def _load_summary(summary_path: Path) -> Tpx3SpidrSummary:
    if not summary_path.is_file():
        raise HermesTpx3PreflightError(
            f"summary path is not a regular file: {summary_path}"
        )
    try:
        return Tpx3SpidrSummary.model_validate_json(summary_path.read_bytes())
    except OSError as exc:
        raise HermesTpx3PreflightError(
            f"cannot read summary JSON file: {summary_path}"
        ) from exc
    except ValidationError as exc:
        raise HermesTpx3PreflightError(
            f"invalid summary JSON file: {summary_path}"
        ) from exc


def _validate_completed_files(
    summary: Tpx3SpidrSummary,
    summary_path: Path,
    analysis_directory: Path,
    raw_file_stem: str,
) -> None:
    """Confirm a summary's listed Parquet files are present and well formed.

    Checks that every Parquet file the summary lists exists inside the analysis
    directory, has the filename the unpacker gives it, is listed only once, and
    that each group's part numbers form a gap-free sequence. The files are not
    opened: the summary is written only after every Parquet file closes, so its
    presence already means the outputs are complete, and its row counts are
    trusted rather than re-read. Skipping the per-file footer read keeps this
    validation fast on runs with tens of thousands of files.
    """
    if summary.unpacking.errors or summary.output_parquet.errors:
        raise HermesTpx3OutputError(
            f"summary reports unpacking or Parquet errors: {summary_path}"
        )

    analysis_root = analysis_directory.resolve()
    categories = (
        ("pixel_hits", summary.output_parquet.pixel_data, True),  # chip in name
        ("tdc_triggers", summary.output_parquet.tdc_timestamps, False),
        ("global_timestamps", summary.output_parquet.heartbeat_packets, False),
        ("control_packets", summary.output_parquet.control_packets, False),
        ("unrecognized_packets", summary.output_parquet.unrecognized_packets, False),
    )
    listed_files: set[Path] = set()
    # The binary names pixel files "<stem>_chip_<chip>_pixels_<part>.parquet"
    # and every other category "<stem>_<label>_<part>.parquet". TDC triggers use
    # one of several per-channel/edge labels within the tdc_triggers directory.
    # The stem is a literal prefix here; the module-level patterns match the
    # rest of the filename after it.
    stem_prefix = f"{raw_file_stem}_"
    for expected_directory, category, has_chip_id in categories:
        parts_by_group: dict[int | str, list[int]] = {}
        if has_chip_id:
            suffix_pattern = _PIXEL_SUFFIX_PATTERN
        elif expected_directory == "tdc_triggers":
            suffix_pattern = _TDC_SUFFIX_PATTERN
        else:
            suffix_pattern = _LABEL_SUFFIX_PATTERNS[expected_directory]

        for parquet_path in category.files:
            filename = parquet_path.name
            suffix_match = (
                suffix_pattern.fullmatch(filename[len(stem_prefix):])
                if filename.startswith(stem_prefix)
                else None
            )
            if (
                parquet_path.parent.name != expected_directory
                or suffix_match is None
            ):
                raise HermesTpx3OutputError(
                    f"unexpected Parquet filename for {raw_file_stem}: "
                    f"{parquet_path}"
                )
            if parquet_path in listed_files:
                raise HermesTpx3OutputError(
                    f"summary lists the same Parquet file more than once: "
                    f"{parquet_path}"
                )

            if has_chip_id:
                group_key: object = int(suffix_match.group(1))
                part_index = int(suffix_match.group(2))
            elif expected_directory == "tdc_triggers":
                # Each channel+edge label has its own part sequence.
                group_key = suffix_match.group(1)
                part_index = int(suffix_match.group(2))
            else:
                group_key = 0  # Single label; one part sequence.
                part_index = int(suffix_match.group(1))

            parts_by_group.setdefault(group_key, []).append(part_index)
            resolved_path = parquet_path.resolve()
            if not resolved_path.is_relative_to(analysis_root):
                raise HermesTpx3OutputError(
                    f"summary lists a Parquet file outside the analysis "
                    f"directory: {parquet_path}"
                )
            if not resolved_path.is_file():
                raise HermesTpx3OutputError(
                    f"summary lists a missing Parquet file: {resolved_path}"
                )
            listed_files.add(parquet_path)

        for group_key, part_indexes in parts_by_group.items():
            if sorted(part_indexes) != list(range(len(part_indexes))):
                if has_chip_id:
                    group_info = f" chip {group_key}"
                elif expected_directory == "tdc_triggers":
                    group_info = f" {group_key}"
                else:
                    group_info = ""
                raise HermesTpx3OutputError(
                    f"unexpected Parquet part numbers for {expected_directory}"
                    f"{group_info}: {sorted(part_indexes)}"
                )


def _bounded_text(text: str) -> str:
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
    message = "Unpacking {raw_tpx3_file} failed: {error}"
    if stderr_excerpt:
        message += "\nstderr: {stderr_excerpt}"
    _ANALYSIS_LOGGER.error(
        message,
        event_type="analysis.tpx3_unpacking.failed",
        raw_tpx3_file=str(raw_file.path),
        command=command,
        exit_code=exit_code,
        elapsed_seconds=elapsed_seconds,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        summary=summary,
        error=error,
    )
