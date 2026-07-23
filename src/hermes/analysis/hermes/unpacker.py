from __future__ import annotations

import os
import re
import subprocess
from time import perf_counter
from pathlib import Path
from typing import Literal, TypeAlias

import pyarrow.parquet as pq
from loguru import logger
from pydantic import ValidationError

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3SpidrSummary,
)
from hermes.state.models.shared_models import FileReference

ContinuationAction: TypeAlias = Literal["run", "skip"]
UnpackingPlan: TypeAlias = list[tuple[FileReference, ContinuationAction]]

_PARQUET_DIRECTORIES = (
    "pixelHits",
    "tdcTriggers",
    "globalTimestamps",
    "controlPackets",
    "unknownPackets",
)
_LOG_TEXT_LIMIT = 4_000
_ANALYSIS_LOGGER = logger.bind(
    domain="analysis",
    mode="hermes",
    step="tpx3_spidr_unpacking",
)


class HermesTpx3Error(Exception):
    """Base exception for HERMES TPX3 unpacking failures."""


class HermesTpx3PreflightError(HermesTpx3Error):
    """Raised when HERMES cannot safely start or continue TPX3 unpacking."""


class HermesTpx3ExecutionError(HermesTpx3Error):
    """Raised when the unpacker process cannot complete successfully."""


class HermesTpx3OutputError(HermesTpx3PreflightError):
    """Raised when unpacker output is missing, unsafe, or inconsistent."""


def derive_summary_path(
    analysis: HermesTpx3AnalysisState,
    raw_file: FileReference,
) -> Path:
    return (
        analysis.analysis_directory
        / "logs"
        / f"{raw_file.path.stem}-unpacker-summary.json"
    )


def derive_unpacker_command(
    analysis: HermesTpx3AnalysisState,
    raw_file: FileReference,
) -> list[str]:
    return [
        str(analysis.unpacker_program.executable_path),
        str(raw_file.path),
        str(analysis.analysis_directory),
    ]


def plan_unpacking(analysis: HermesTpx3AnalysisState) -> UnpackingPlan:
    _validate_program_and_inputs(analysis)

    plan: UnpackingPlan = []
    for raw_file in analysis.tpx3_files:
        summary_path = derive_summary_path(analysis, raw_file)
        matching_parquet_files = _matching_parquet_files(
            analysis.analysis_directory,
            raw_file.path.stem,
        )

        if summary_path.exists():
            summary = _load_summary(summary_path)
            _validate_completed_files(
                summary,
                summary_path,
                analysis.analysis_directory,
                raw_file.path.stem,
            )
            plan.append((raw_file, "skip"))
        elif matching_parquet_files:
            raise HermesTpx3PreflightError(
                f"Parquet files exist without a valid summary for "
                f"{raw_file.path}: {matching_parquet_files[0]}"
            )
        else:
            plan.append((raw_file, "run"))

    return plan


def execute_unpacker(
    analysis: HermesTpx3AnalysisState,
    raw_file: FileReference,
) -> Tpx3SpidrSummary:
    command = derive_unpacker_command(analysis, raw_file)
    summary_path = derive_summary_path(analysis, raw_file)
    started = perf_counter()
    _ANALYSIS_LOGGER.info(
        "analysis.tpx3_unpacking.started",
        event_type="analysis.tpx3_unpacking.started",
        raw_tpx3_file=str(raw_file.path),
        raw_tpx3_size_bytes=raw_file.path.stat().st_size,
        analysis_directory=str(analysis.analysis_directory),
        summary_json_file=str(summary_path),
        executable_path=str(analysis.unpacker_program.executable_path),
        executable_version=analysis.unpacker_program.version,
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
            analysis.analysis_directory,
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
        "analysis.tpx3_unpacking.completed",
        event_type="analysis.tpx3_unpacking.completed",
        raw_tpx3_file=str(raw_file.path),
        analysis_directory=str(analysis.analysis_directory),
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
    analysis: HermesTpx3AnalysisState,
    raw_file: FileReference,
) -> None:
    _ANALYSIS_LOGGER.info(
        "analysis.tpx3_unpacking.skipped",
        event_type="analysis.tpx3_unpacking.skipped",
        raw_tpx3_file=str(raw_file.path),
        analysis_directory=str(analysis.analysis_directory),
        summary_json_file=str(derive_summary_path(analysis, raw_file)),
        reason="valid summary and listed Parquet files already exist",
    )


def log_overall_completion(
    *,
    raw_file_count: int,
    unpacked_file_count: int,
) -> None:
    _ANALYSIS_LOGGER.info(
        "analysis.tpx3_unpacking.completed",
        event_type="analysis.tpx3_unpacking.completed",
        scope="all_raw_tpx3_files",
        raw_file_count=raw_file_count,
        unpacked_file_count=unpacked_file_count,
        skipped_file_count=raw_file_count - unpacked_file_count,
    )


def log_overall_failure(error: Exception) -> None:
    _ANALYSIS_LOGGER.error(
        "analysis.tpx3_unpacking.failed",
        event_type="analysis.tpx3_unpacking.failed",
        scope="all_raw_tpx3_files",
        error=str(error),
    )


def _validate_program_and_inputs(analysis: HermesTpx3AnalysisState) -> None:
    executable = analysis.unpacker_program.executable_path
    if not executable.is_file():
        raise HermesTpx3PreflightError(
            f"unpacker executable does not exist: {executable}"
        )

    for raw_file in analysis.tpx3_files:
        if not raw_file.path.is_file():
            raise HermesTpx3PreflightError(
                f"raw TPX3 file does not exist: {raw_file.path}"
            )

    stems = [raw_file.path.stem for raw_file in analysis.tpx3_files]
    if len(stems) != len(set(stems)):
        raise HermesTpx3PreflightError(
            "raw TPX3 filename stems must be unique"
        )

    analysis_directory = analysis.analysis_directory
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
    if summary.unpacking.errors or summary.parquet.errors:
        raise HermesTpx3OutputError(
            f"summary reports unpacking or Parquet errors: {summary_path}"
        )

    analysis_root = analysis_directory.resolve()
    categories = (
        ("pixelHits", summary.parquet.pixel_hits, True),  # includes chip ID
        ("tdcTriggers", summary.parquet.tdc_triggers, False),  # no chip ID
        ("globalTimestamps", summary.parquet.global_timestamps, False),
        ("controlPackets", summary.parquet.control_packets, False),
        ("unknownPackets", summary.parquet.unknown_packets, False),
    )
    listed_files: set[Path] = set()
    filename_pattern_with_chip = re.compile(
        rf"^{re.escape(raw_file_stem)}-chip-(\d+)-part-(\d{{5}})\.parquet$"
    )
    filename_pattern_without_chip = re.compile(
        rf"^{re.escape(raw_file_stem)}-part-(\d{{5}})\.parquet$"
    )
    for expected_directory, category, has_chip_id in categories:
        observed_rows = 0
        parts_by_chip: dict[int, list[int]] = {}
        filename_pattern = filename_pattern_with_chip if has_chip_id else filename_pattern_without_chip

        for relative_path in category.files:
            filename_match = filename_pattern.fullmatch(relative_path.name)
            if (
                len(relative_path.parts) != 2
                or relative_path.parts[0] != expected_directory
                or filename_match is None
            ):
                raise HermesTpx3OutputError(
                    f"unexpected Parquet filename for {raw_file_stem}: "
                    f"{relative_path}"
                )
            if relative_path in listed_files:
                raise HermesTpx3OutputError(
                    f"summary lists the same Parquet file more than once: "
                    f"{relative_path}"
                )

            if has_chip_id:
                chip_index = int(filename_match.group(1))
                part_index = int(filename_match.group(2))
            else:
                chip_index = 0  # No chip ID in filename, use default
                part_index = int(filename_match.group(1))

            parts_by_chip.setdefault(chip_index, []).append(part_index)
            parquet_path = analysis_directory / relative_path
            resolved_path = parquet_path.resolve()
            if not resolved_path.is_relative_to(analysis_root):
                raise HermesTpx3OutputError(
                    f"summary lists a Parquet file outside the analysis "
                    f"directory: {relative_path}"
                )
            if not parquet_path.is_file():
                raise HermesTpx3OutputError(
                    f"summary lists a missing Parquet file: {parquet_path}"
                )
            try:
                observed_rows += pq.read_metadata(parquet_path).num_rows
            except Exception as exc:
                raise HermesTpx3OutputError(
                    f"cannot read Parquet metadata: {parquet_path}"
                ) from exc
            listed_files.add(relative_path)

        for chip_index, part_indexes in parts_by_chip.items():
            if sorted(part_indexes) != list(range(len(part_indexes))):
                chip_info = f" chip {chip_index}" if has_chip_id else ""
                raise HermesTpx3OutputError(
                    f"unexpected Parquet part numbers for {expected_directory}"
                    f"{chip_info}: {sorted(part_indexes)}"
                )

        if observed_rows != category.row_count:
            raise HermesTpx3OutputError(
                f"Parquet row count mismatch for {expected_directory}: "
                f"summary={category.row_count}, files={observed_rows}"
            )

    matching_files = {
        path.relative_to(analysis_directory)
        for path in _matching_parquet_files(
            analysis_directory,
            raw_file_stem,
        )
    }
    if matching_files != listed_files:
        unexpected = sorted(str(path) for path in matching_files - listed_files)
        missing = sorted(str(path) for path in listed_files - matching_files)
        raise HermesTpx3OutputError(
            f"summary Parquet file list does not match files for "
            f"{raw_file_stem}; unexpected={unexpected}, missing={missing}"
        )


def _matching_parquet_files(
    analysis_directory: Path,
    raw_file_stem: str,
) -> list[Path]:
    matches: list[Path] = []
    pattern = f"{raw_file_stem}-*.parquet"
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
    _ANALYSIS_LOGGER.error(
        "analysis.tpx3_unpacking.failed",
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
