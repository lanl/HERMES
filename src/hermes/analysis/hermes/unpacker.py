from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, TypeAlias

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


class HermesTpx3PreflightError(Exception):
    """Raised when HERMES cannot safely start or continue TPX3 unpacking."""


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
) -> None:
    if summary.unpacking.errors or summary.parquet.errors:
        raise HermesTpx3PreflightError(
            f"summary reports unpacking or Parquet errors: {summary_path}"
        )

    analysis_root = analysis_directory.resolve()
    categories = (
        summary.parquet.pixel_hits,
        summary.parquet.tdc_triggers,
        summary.parquet.global_timestamps,
        summary.parquet.control_packets,
        summary.parquet.unknown_packets,
    )
    for category in categories:
        for relative_path in category.files:
            parquet_path = analysis_directory / relative_path
            resolved_path = parquet_path.resolve()
            if not resolved_path.is_relative_to(analysis_root):
                raise HermesTpx3PreflightError(
                    f"summary lists a Parquet file outside the analysis "
                    f"directory: {relative_path}"
                )
            if not parquet_path.is_file():
                raise HermesTpx3PreflightError(
                    f"summary lists a missing Parquet file: {parquet_path}"
                )


def _matching_parquet_files(
    analysis_directory: Path,
    raw_file_stem: str,
) -> list[Path]:
    matches: list[Path] = []
    pattern = f"{raw_file_stem}-chip-*-part-*.parquet"
    for directory in _PARQUET_DIRECTORIES:
        category_directory = analysis_directory / directory
        if category_directory.is_dir():
            matches.extend(category_directory.glob(pattern))
    return sorted(matches)
