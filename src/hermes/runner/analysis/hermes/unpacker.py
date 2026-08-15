from __future__ import annotations

import os
import re
import subprocess
from time import perf_counter
from pathlib import Path

import pyarrow.parquet as pq
from loguru import logger
from pydantic import ValidationError

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3SpidrSummary,
)
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import FileReference
from hermes.runner.analysis.executables import resolve_executable

# Each Parquet category directory and the filename label the unpacker uses in it.
# Pixel files are named "<stem>_chip_<chip>_pixels_<part>.parquet"; every other
# category is named "<stem>_<label>_<part>.parquet".
_PARQUET_DIRECTORY_LABELS = {
    "pixel_hits": None,
    "tdc_triggers": "tdc_triggers",
    "global_timestamps": "global_timestamps",
    "control_packets": "control_packets",
    "unknownPackets": "unrecognized_packets",
}
_PARQUET_DIRECTORIES = tuple(_PARQUET_DIRECTORY_LABELS)
# TDC triggers are written one file per channel+edge that occurs, so the
# tdc_triggers directory holds up to four differently labeled filenames.
_TDC_TRIGGER_LABELS = (
    "tdc1_rising_triggers",
    "tdc1_falling_triggers",
    "tdc2_rising_triggers",
    "tdc2_falling_triggers",
)
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
) -> None:
    _ANALYSIS_LOGGER.info(
        "Unpacking finished: {unpacked_file_count} unpacked, "
        "{skipped_file_count} skipped of {raw_file_count} raw files",
        event_type="analysis.tpx3_unpacking.completed",
        scope="all_raw_tpx3_files",
        raw_file_count=raw_file_count,
        unpacked_file_count=unpacked_file_count,
        skipped_file_count=raw_file_count - unpacked_file_count,
    )


def log_overall_failure(error: Exception) -> None:
    _ANALYSIS_LOGGER.error(
        "Unpacking failed: {error}",
        event_type="analysis.tpx3_unpacking.failed",
        scope="all_raw_tpx3_files",
        error=str(error),
    )


def validate_program_and_inputs(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
) -> None:
    executable = analysis.unpacking.program.executable_path
    try:
        resolve_executable(executable)
    except (FileNotFoundError, PermissionError) as exc:
        raise HermesTpx3PreflightError(
            f"unpacker executable does not exist: {executable}; build the "
            "binary (e.g. via pixi) and set unpacking.program.executable_path"
        ) from exc

    for raw_file in analysis.unpacking.tpx3_files:
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
        ("unknownPackets", summary.output_parquet.unrecognized_packets, False),
    )
    listed_files: set[Path] = set()
    # The binary names pixel files "<stem>_chip_<chip>_pixels_<part>.parquet"
    # and every other category "<stem>_<label>_<part>.parquet". TDC triggers
    # use one of several per-channel/edge labels within the tdc_triggers
    # directory, so they match any of _TDC_TRIGGER_LABELS.
    filename_pattern_with_chip = re.compile(
        rf"^{re.escape(raw_file_stem)}_chip_(\d+)_pixels_(\d{{5}})\.parquet$"
    )
    tdc_label_alternatives = "|".join(
        re.escape(label) for label in _TDC_TRIGGER_LABELS
    )
    filename_pattern_tdc = re.compile(
        rf"^{re.escape(raw_file_stem)}_({tdc_label_alternatives})_"
        rf"(\d{{5}})\.parquet$"
    )
    for expected_directory, category, has_chip_id in categories:
        observed_rows = 0
        parts_by_group: dict[int | str, list[int]] = {}
        if has_chip_id:
            filename_pattern = filename_pattern_with_chip
        elif expected_directory == "tdc_triggers":
            filename_pattern = filename_pattern_tdc
        else:
            label = _PARQUET_DIRECTORY_LABELS[expected_directory]
            filename_pattern = re.compile(
                rf"^{re.escape(raw_file_stem)}_{re.escape(label)}_"
                rf"(\d{{5}})\.parquet$"
            )

        for parquet_path in category.files:
            filename_match = filename_pattern.fullmatch(parquet_path.name)
            if (
                parquet_path.parent.name != expected_directory
                or filename_match is None
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
                group_key: object = int(filename_match.group(1))
                part_index = int(filename_match.group(2))
            elif expected_directory == "tdc_triggers":
                # Each channel+edge label has its own part sequence.
                group_key = filename_match.group(1)
                part_index = int(filename_match.group(2))
            else:
                group_key = 0  # Single label; one part sequence.
                part_index = int(filename_match.group(1))

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
            try:
                observed_rows += pq.read_metadata(resolved_path).num_rows
            except Exception as exc:
                raise HermesTpx3OutputError(
                    f"cannot read Parquet metadata: {resolved_path}"
                ) from exc
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

        if observed_rows != category.row_count:
            raise HermesTpx3OutputError(
                f"Parquet row count mismatch for {expected_directory}: "
                f"summary={category.row_count}, files={observed_rows}"
            )

    matching_files = {
        path.resolve()
        for path in _matching_parquet_files(
            analysis_directory,
            raw_file_stem,
        )
    }
    listed_resolved = {path.resolve() for path in listed_files}
    if matching_files != listed_resolved:
        unexpected = sorted(str(path) for path in matching_files - listed_resolved)
        missing = sorted(str(path) for path in listed_resolved - matching_files)
        raise HermesTpx3OutputError(
            f"summary Parquet file list does not match files for "
            f"{raw_file_stem}; unexpected={unexpected}, missing={missing}"
        )


def _matching_parquet_files(
    analysis_directory: Path,
    raw_file_stem: str,
) -> list[Path]:
    matches: list[Path] = []
    pattern = f"{raw_file_stem}_*.parquet"
    for directory in _PARQUET_DIRECTORIES:
        category_directory = analysis_directory / directory
        if category_directory.is_dir():
            matches.extend(category_directory.glob(pattern))
    return sorted(matches)


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
