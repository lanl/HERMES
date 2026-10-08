"""The bundled HERMES MCP server.

One local MCP server (standard input/output, no network) that ships inside the
HERMES package so any MCP-speaking LLM tool can help a user configure and run a
HERMES analysis. Its tools write a workflow config and a runnable script for the
``.tpx3`` files in a folder, check a config, check the installation, describe
a run's Parquet output files, and report how far a run got and why anything
failed.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from importlib.metadata import PackageNotFoundError, distribution, version
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from loguru import logger
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field, ValidationError

from hermes.runner.analysis.executables import (
    newer_source_than_binary,
    resolve_executable,
)
from hermes.shipped_files import default_timewalk_calibration
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateIOError
from hermes.state_service.state_io import load_hermes_record_from_yaml

mcp_server = MCPServer("hermes")

FurthestStage = Literal[
    "unpacking",
    "photon_reconstruction",
    "event_reconstruction",
]

# The three analysis stages, each with the fixed program and the standard
# defaults the example configs use. tpx3_files is filled in from the files found
# in the folder; the photon and event stages read their input from the previous
# stage with "auto".
_UNPACKING: dict = {
    "program": {
        "name": "tpx3-spidr-cpp",
        "executable_path": "hermes-tpx3-spidr",
    },
}
_PHOTON_RECONSTRUCTION: dict = {
    "program": {
        "name": "photon-clusterer-cpp",
        "executable_path": "hermes-photon-clusterer",
    },
    "pixel_files": "auto",
    "clustering_algorithm": {
        "name": "connected_components",
        "save_photon_pixels": True,
        "settings": {
            "max_time_spread_ticks": 491520,
            "min_cluster_size": 2,
            "max_cluster_size": 64,
            "min_pixel_tot_raw": 1,
            "min_cluster_tot_raw": 2,
            "max_cluster_tot_raw": 65472,
            "max_aspect_ratio": 3.0,
            "min_filled_fraction": 0.5,
            "adjacency": 8,
            "position_averaging": "arithmetic",
            "photon_time_estimator": "leading_edge",
            "timewalk_calibration_file": "default",
        },
    },
}
_EVENT_RECONSTRUCTION: dict = {
    "program": {
        "name": "event-reconstructor-cpp",
        "executable_path": "hermes-event-reconstructor",
    },
    "photon_parquet_files": "auto",
    "clustering_algorithm": "connected_components",
    "settings": {
        "spatial_link_radius_pixels": 10.0,
        "spatial_cells_per_axis": 5,
        "max_time_difference_ticks": 4915200.0,
        "max_event_duration_ticks": 14745600.0,
        "min_photon_count": 1,
        "save_event_photons": False,
    },
}

# The config keeps HERMES's full, structured logs in JSON-lines files in the
# run's logs/ folder. This level only sets how much a run prints to the
# terminal, so keep runs quiet by showing errors and worse on screen while the
# log files keep everything.
_LOG_DIRECTORY = "logs"
_QUIET_LOG_LEVEL = "ERROR"

_RUN_SCRIPT = '''from pathlib import Path

from hermes.state_service.state_io import load_hermes_record_from_yaml
from hermes.workflows.workflow import Workflow


def main() -> None:
    config = Path(__file__).parent / "hermes-config.yaml"
    record = load_hermes_record_from_yaml(config)
    Workflow(record).run()


if __name__ == "__main__":
    main()
'''


class AnalysisConfigRequest(BaseModel):
    working_directory: Path = Field(
        description="Folder that holds the .tpx3 files; the config and run "
        "script are written here.",
    )
    measurement_id: str = Field(min_length=1)
    run: str = Field(min_length=1)
    furthest_stage: FurthestStage = Field(
        description="How far to run: 'unpacking' (raw .tpx3 into pixel and TDC "
        "Parquet), 'photon_reconstruction' (also cluster pixels into photons), "
        "or 'event_reconstruction' (also group photons into events). Ask the "
        "user how far they want to go.",
    )


class AnalysisConfigResult(BaseModel):
    config_file: Path
    run_script: Path
    tpx3_files: list[str]
    stages: list[str]
    message: str


@mcp_server.tool()
def create_analysis_config(request: AnalysisConfigRequest) -> AnalysisConfigResult:
    """Write a HERMES config and a runnable script for the .tpx3 files in a
    folder, running through the chosen stage with HERMES's standard defaults."""
    directory = request.working_directory.expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f"working directory does not exist: {directory}")

    raw_files = sorted(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*.tpx3")
    )
    if not raw_files:
        raise ValueError(f"no .tpx3 files found under {directory}")

    # HERMES opens each listed .tpx3 path as written, from whatever folder the
    # run script is launched in, so write full paths.
    unpacking = {
        **_UNPACKING,
        "tpx3_files": [{"path": str(directory / name)} for name in raw_files],
    }
    analysis: dict = {"mode": "hermes", "unpacking": unpacking}
    stages = ["unpacking"]
    if request.furthest_stage in ("photon_reconstruction", "event_reconstruction"):
        analysis["photon_reconstruction"] = _PHOTON_RECONSTRUCTION
        stages.append("photon_reconstruction")
    if request.furthest_stage == "event_reconstruction":
        analysis["event_reconstruction"] = _EVENT_RECONSTRUCTION
        stages.append("event_reconstruction")

    config = {
        "measurement_info": {
            "measurement_id": request.measurement_id,
            "run": request.run,
        },
        "environment": {
            "working_directory": str(directory),
            "analysis_directory": "analysis",
            "log_directory": _LOG_DIRECTORY,
            "log_level": _QUIET_LOG_LEVEL,
        },
        "analysis": analysis,
    }

    # Validate against the installed HERMES's real rules before writing.
    HermesRecord.model_validate(config)

    config_path = directory / "hermes-config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    script_path = directory / "run_hermes.py"
    script_path.write_text(_RUN_SCRIPT, encoding="utf-8")

    logger.bind(domain="analysis").info(
        "wrote HERMES config through {stage} for {count} raw file(s) to {path}",
        stage=request.furthest_stage,
        count=len(raw_files),
        path=str(config_path),
    )
    return AnalysisConfigResult(
        config_file=config_path,
        run_script=script_path,
        tpx3_files=raw_files,
        stages=stages,
        message=(
            f"Wrote a config running through {request.furthest_stage} for "
            f"{len(raw_files)} .tpx3 file(s). Run it with: "
            f"pixi run python {script_path.name}"
        ),
    )


class ConfigValidationRequest(BaseModel):
    config_file: Path = Field(
        description="Path to the HERMES config YAML to check, for example the "
        "hermes-config.yaml written by create_analysis_config.",
    )


class ConfigValidationResult(BaseModel):
    valid: bool
    config_file: Path
    stages: list[str]
    problems: list[str]
    message: str


def _format_validation_problems(error: ValidationError) -> list[str]:
    problems: list[str] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "(top level)"
        problems.append(f"{location}: {item['msg']}")
    return problems


def _configured_stages(record: HermesRecord) -> list[str]:
    analysis = record.analysis
    if analysis is None or analysis.mode != "hermes":
        return []
    named = (
        ("unpacking", analysis.unpacking),
        ("photon_reconstruction", analysis.photon_reconstruction),
        ("event_reconstruction", analysis.event_reconstruction),
    )
    return [name for name, value in named if value is not None]


@mcp_server.tool()
def validate_config(request: ConfigValidationRequest) -> ConfigValidationResult:
    """Check whether a HERMES config YAML loads and validates against the
    installed HERMES's rules, reporting each problem when it does not."""
    path = request.config_file.expanduser().resolve()

    if not path.is_file():
        problem = f"config file not found: {path}"
        return ConfigValidationResult(
            valid=False,
            config_file=path,
            stages=[],
            problems=[problem],
            message=problem,
        )

    try:
        record = load_hermes_record_from_yaml(path)
    except StateIOError as exc:
        cause = exc.__cause__
        if isinstance(cause, ValidationError):
            problems = _format_validation_problems(cause)
        else:
            problems = [str(exc)]
            if cause is not None:
                problems.append(str(cause))
        logger.bind(domain="analysis").info(
            "config {path} is not valid: {count} problem(s)",
            path=str(path),
            count=len(problems),
        )
        return ConfigValidationResult(
            valid=False,
            config_file=path,
            stages=[],
            problems=problems,
            message=f"Config is not valid: {len(problems)} problem(s).",
        )

    stages = _configured_stages(record)
    logger.bind(domain="analysis").info(
        "config {path} is valid; stages: {stages}",
        path=str(path),
        stages=stages or ["none"],
    )
    stage_text = ", ".join(stages) if stages else "no HERMES analysis stages"
    return ConfigValidationResult(
        valid=True,
        config_file=path,
        stages=stages,
        problems=[],
        message=f"Config is valid ({stage_text}).",
    )


# The three C++ programs HERMES builds, each with the source folders under
# src/backends/ it is compiled from.
_HERMES_PROGRAMS: dict[str, tuple[str, ...]] = {
    "hermes-tpx3-spidr": ("unpackers/tpx3-spidr/cpp",),
    "hermes-photon-clusterer": ("reconstruction/photons/cpp",),
    "hermes-event-reconstructor": (
        "reconstruction/events/connected-components/cpp",
        "reconstruction/events/common/cpp",
    ),
}
# HERMES can drive EMPIR but does not install it.
_EMPIR_PROGRAMS = (
    "empir_pixel2photon_tpx3spidr",
    "empir_photon2event",
    "empir_event2image",
)
_PYTHON_PACKAGES = ("pydantic", "pyarrow", "numpy", "mcp")
# The C++ source in a clone. An editable install builds each program from here
# once and does not rebuild it when the source changes. A wheel install has no
# source here, so the check for an out-of-date program is skipped.
_CPP_SOURCE = Path(__file__).resolve().parents[2] / "backends"


class ProgramCheck(BaseModel):
    name: str
    path: Path | None = Field(
        default=None,
        description="Where the program was found; empty when it was not found.",
    )
    built: datetime | None = Field(
        default=None,
        description="When the program file was last written. For a C++ "
        "program this is when it was built.",
    )
    newer_source_file: Path | None = Field(
        default=None,
        description="A C++ source file that changed after the program was "
        "built, so the program runs old code until it is rebuilt.",
    )
    problem: str | None = None


class InstallationCheckResult(BaseModel):
    hermes_version: str
    installed_from: str | None = Field(
        description="Where HERMES was installed from: a git URL or a folder. "
        "Empty when it was installed from a package index.",
    )
    editable: bool = Field(
        description="True when HERMES runs straight from a clone's source.",
    )
    git_commit: str | None = Field(
        description="The commit HERMES was installed from, when it was "
        "installed from git.",
    )
    programs: list[ProgramCheck]
    timewalk_calibration: Path | None = Field(
        description="The default time-walk calibration HERMES ships; empty "
        "when it is missing.",
    )
    empir_programs: list[ProgramCheck]
    python_packages: dict[str, str]
    message: str


def _check_program(name: str, source_folders: tuple[str, ...] = ()) -> ProgramCheck:
    try:
        path = resolve_executable(Path(name))
    except (FileNotFoundError, PermissionError) as exc:
        return ProgramCheck(name=name, problem=str(exc))
    built = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    newer_source_file = None
    for folder in source_folders:
        newer_source_file = newer_source_than_binary(path, _CPP_SOURCE / folder)
        if newer_source_file is not None:
            break
    return ProgramCheck(
        name=name, path=path, built=built, newer_source_file=newer_source_file
    )


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not installed"


@mcp_server.tool()
def check_installation() -> InstallationCheckResult:
    """Report which HERMES is installed and whether everything it needs is
    present: the three C++ programs, the default time-walk calibration, EMPIR,
    and the main Python packages. Run this first when something does not work."""
    hermes = distribution("hermes")
    # pip and uv record where a package came from in direct_url.json.
    direct_url = json.loads(hermes.read_text("direct_url.json") or "{}")

    programs = [
        _check_program(name, folders) for name, folders in _HERMES_PROGRAMS.items()
    ]
    empir_programs = [_check_program(name) for name in _EMPIR_PROGRAMS]
    try:
        timewalk_calibration = default_timewalk_calibration()
    except FileNotFoundError:
        timewalk_calibration = None
    python_packages = {name: _package_version(name) for name in _PYTHON_PACKAGES}

    notes: list[str] = []
    for program in programs:
        if program.path is None:
            notes.append(
                f"{program.name} cannot be used ({program.problem}). Either the "
                f"pixi environment is not active or the install did not build "
                f"it; reinstall with `pixi reinstall hermes` and check its "
                f"build output."
            )
        elif program.newer_source_file is not None:
            notes.append(
                f"{program.name} was built before {program.newer_source_file} "
                f"changed, so it runs old code. Rebuild it with `pixi reinstall "
                f"hermes`."
            )
    if timewalk_calibration is None:
        notes.append(
            "The default time-walk calibration is missing, so "
            "`timewalk_calibration_file: default` will fail."
        )
    missing_packages = [
        name for name, found in python_packages.items() if found == "not installed"
    ]
    if missing_packages:
        notes.append(
            f"These Python packages are not installed: "
            f"{', '.join(missing_packages)}. Reinstall with `pixi reinstall "
            f"hermes`."
        )
    if not notes:
        notes.append(
            "The three C++ programs and the default time-walk calibration "
            "are present."
        )
    missing_empir = [p.name for p in empir_programs if p.path is None]
    if not missing_empir:
        notes.append("EMPIR is installed.")
    elif len(missing_empir) == len(empir_programs):
        notes.append(
            "EMPIR is not on PATH. HERMES does not install it and needs it only "
            "for EMPIR analysis."
        )
    else:
        notes.append(
            f"Some EMPIR programs are not on PATH: {', '.join(missing_empir)}."
        )

    logger.bind(domain="mcp").info(
        "checked the HERMES {version} installation: {programs} of 3 C++ "
        "programs found",
        version=hermes.version,
        programs=sum(p.path is not None for p in programs),
    )
    return InstallationCheckResult(
        hermes_version=hermes.version,
        installed_from=direct_url.get("url"),
        editable=direct_url.get("dir_info", {}).get("editable", False),
        git_commit=direct_url.get("vcs_info", {}).get("commit_id"),
        programs=programs,
        timewalk_calibration=timewalk_calibration,
        empir_programs=empir_programs,
        python_packages=python_packages,
        message=f"HERMES {hermes.version}. " + " ".join(notes),
    )


# Every timestamp_canonical column counts ticks of 25 ns / 12288.
_TICK_SECONDS = 25e-9 / 12_288
_EXAMPLE_ROW_COUNT = 3


class OutputFilesRequest(BaseModel):
    analysis_directory: Path = Field(
        description="The run's analysis folder, which holds one folder per "
        "kind of output, such as pixel_hits/, tdc_triggers/, photons/ and "
        "events/.",
    )


class OutputFolderSummary(BaseModel):
    folder: str
    file_count: int
    total_bytes: int
    row_count: int
    columns: dict[str, str] = Field(
        description="Column names and types, from the first file's schema.",
    )
    first_timestamp_canonical: int | float | None = Field(
        description="The earliest timestamp_canonical in the folder, in ticks; "
        "empty when the files have no timestamp_canonical column, or when a "
        "file has no statistics for it.",
    )
    last_timestamp_canonical: int | float | None
    time_span_seconds: float | None
    example_file: str
    example_rows: list[dict[str, Any]]
    problems: list[str] = Field(
        description="Files that could not be read, for example one still "
        "being written, which are left out of the counts; and files with no "
        "timestamp_canonical statistics, which leave out the time range.",
    )


class OutputFilesResult(BaseModel):
    analysis_directory: Path
    tick_seconds: float = Field(
        description="Seconds per timestamp_canonical tick.",
    )
    folders: list[OutputFolderSummary]
    message: str


def _timestamp_range(
    metadata: pq.FileMetaData,
) -> tuple[int | float, int | float] | None:
    """Read the timestamp_canonical range from the column statistics.

    Returns None when the file has no timestamp_canonical column or no values
    in it. Raises ValueError when part of the column has values but no
    statistics, because the range would then be incomplete.
    """
    names = metadata.schema.names
    if "timestamp_canonical" not in names:
        return None
    column = names.index("timestamp_canonical")
    lows: list[int | float] = []
    highs: list[int | float] = []
    for index in range(metadata.num_row_groups):
        group = metadata.row_group(index)
        statistics = group.column(column).statistics
        if statistics is not None and statistics.has_min_max:
            lows.append(statistics.min)
            highs.append(statistics.max)
        elif not (
            statistics is not None
            and statistics.has_null_count
            and statistics.null_count == group.num_rows
        ):
            raise ValueError("timestamp_canonical has no statistics")
    if not lows:
        return None
    return min(lows), max(highs)


def _describe_folder(folder: Path, files: list[Path]) -> OutputFolderSummary:
    # Read only each file's footer. A run can have thousands of files, so each
    # one is closed straight away rather than kept open.
    readable: list[tuple[Path, pq.FileMetaData]] = []
    problems: list[str] = []
    for path in files:
        try:
            readable.append((path, pq.read_metadata(path)))
        except (OSError, pa.ArrowException) as exc:
            problems.append(f"could not read {path.name}: {exc}")

    total_bytes = 0
    row_count = 0
    lows: list[int | float] = []
    highs: list[int | float] = []
    range_is_complete = True
    for path, metadata in readable:
        total_bytes += path.stat().st_size
        row_count += metadata.num_rows
        try:
            time_range = _timestamp_range(metadata)
        except ValueError:
            range_is_complete = False
            problems.append(
                f"{path.name} has no timestamp_canonical statistics, so the "
                f"folder's time range is left out"
            )
            continue
        if time_range is not None:
            lows.append(time_range[0])
            highs.append(time_range[1])

    columns: dict[str, str] = {}
    example_file = ""
    example_rows: list[dict[str, Any]] = []
    if readable:
        # Take the example rows from the first file that has any.
        path = next(
            (path for path, metadata in readable if metadata.num_rows > 0),
            readable[0][0],
        )
        with pq.ParquetFile(path) as parquet_file:
            columns = {
                field.name: str(field.type) for field in parquet_file.schema_arrow
            }
            for batch in parquet_file.iter_batches(batch_size=_EXAMPLE_ROW_COUNT):
                example_rows = batch.to_pylist()
                break
        example_file = path.name

    first = min(lows) if lows and range_is_complete else None
    last = max(highs) if highs and range_is_complete else None
    return OutputFolderSummary(
        folder=folder.name,
        file_count=len(readable),
        total_bytes=total_bytes,
        row_count=row_count,
        columns=columns,
        first_timestamp_canonical=first,
        last_timestamp_canonical=last,
        time_span_seconds=(
            (last - first) * _TICK_SECONDS if first is not None else None
        ),
        example_file=example_file,
        example_rows=example_rows,
        problems=problems,
    )


@mcp_server.tool()
def describe_output_files(request: OutputFilesRequest) -> OutputFilesResult:
    """Describe the Parquet files in a run's analysis folder: for each output
    folder, the file count and size, the columns and their types, the row
    count, the timestamp_canonical range, and a few example rows. Reads only
    the file footers and a few rows, so it is quick on runs of any size. Use it
    before writing pandas or matplotlib code for a run's output."""
    directory = request.analysis_directory.expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f"analysis folder does not exist: {directory}")

    folders: list[OutputFolderSummary] = []
    for folder in sorted(path for path in directory.iterdir() if path.is_dir()):
        files = sorted(folder.glob("*.parquet"))
        if files:
            folders.append(_describe_folder(folder, files))
    if not folders:
        raise ValueError(
            f"no folders with Parquet files under {directory}; give the run's "
            f"analysis folder, for example <run folder>/analysis"
        )

    file_count = sum(summary.file_count for summary in folders)
    problem_count = sum(len(summary.problems) for summary in folders)
    logger.bind(domain="analysis").info(
        "described {files} Parquet file(s) in {folders} folder(s) under {path}",
        files=file_count,
        folders=len(folders),
        path=str(directory),
    )
    message = (
        f"Found {file_count} Parquet file(s) in {len(folders)} folder(s): "
        f"{', '.join(summary.folder for summary in folders)}. Every "
        f"timestamp_canonical column counts ticks of 25 ns / 12288 (about "
        f"2.03 ps), so times from different folders can be subtracted "
        f"directly; multiply by tick_seconds to get seconds. If the "
        f"hermes-config-and-files skill is installed, its output_files.md "
        f"says what each column means and lists known timing limits."
    )
    if problem_count:
        message += (
            f" {problem_count} file(s) had problems; see each folder's "
            f"problems."
        )
    return OutputFilesResult(
        analysis_directory=directory,
        tick_seconds=_TICK_SECONDS,
        folders=folders,
        message=message,
    )


_STAGES = ("unpacking", "photon_reconstruction", "event_reconstruction")
# The workflow log calls photon reconstruction just "reconstruction".
_WORKFLOW_LOG_STAGES = {"reconstruction": "photon_reconstruction"}
_STAGE_OUTPUT_FOLDERS = {
    "unpacking": (
        "pixel_hits",
        "tdc_triggers",
        "global_timestamps",
        "control_packets",
        "unrecognized_packets",
    ),
    "photon_reconstruction": ("photons", "pixel_clusters"),
    "event_reconstruction": ("events", "event_photons"),
}
_OUTCOMES = {
    "workflow_completed": "completed",
    "workflow_failed": "failed",
    "workflow_stopped": "stopped",
}
_MEASUREMENT_EVENTS = (
    "acquisition.serval.measurement_progress",
    "acquisition.serval.measurement_done",
)
# Show at most this many problem files and kinds of message, and this many
# errors for each file, so the answer stays short even when hundreds of files
# failed.
_SHOWN = 20
_ERRORS_PER_FILE = 3
# state.jsonl holds the whole record and can grow to tens of megabytes, so
# only its last megabyte is read.
_TAIL_BYTES = 1_000_000


class RunStatusRequest(BaseModel):
    run_directory: Path = Field(
        description="The run folder, which holds HERMES_record.yaml, analysis/ "
        "and logs/.",
    )


class AcquisitionStatus(BaseModel):
    status: str | None = Field(
        description="Once the run has ended, the status saved in "
        "HERMES_record.yaml: completed, failed, stopped, configured, planned "
        "or unknown. While the run is going, 'running', or 'measurement "
        "finished' once the camera has stopped, from the acquisition log.",
    )
    stop_reason: str | None
    frames: int | None
    dropped_frames: int | None
    warnings: list[str]
    errors: list[str]


class StageStatus(BaseModel):
    stage: str
    succeeded: int
    skipped: int = Field(
        description="Files left as they were because valid outputs already "
        "existed.",
    )
    failed: int
    not_run: int = Field(
        description="Raw files this stage has no result for although the "
        "stage before finished them, for example when that stage passed on "
        "nothing to work on. While a run is going, this also counts .tpx3 "
        "files in the run folder still waiting to be unpacked.",
    )
    parquet_files: int = Field(
        description="Parquet files in this stage's output folders.",
    )


class ProblemFile(BaseModel):
    stage: str
    file: str
    status: str = Field(
        description="failed; 'not run' for a file the stage has no result "
        "for although the stage before finished it; or the saved status of a "
        "file that logged errors anyway.",
    )
    errors: list[str] = Field(
        description=f"The first {_ERRORS_PER_FILE} error messages.",
    )
    error_count: int


class LoggedMessage(BaseModel):
    source: str = Field(
        description="The log file it came from, or the stage whose summary "
        "files it came from.",
    )
    text: str = Field(description="The first message of this kind.")
    count: int = Field(
        description="How many messages of this kind there were; messages that "
        "differ only in their numbers count as one kind.",
    )


class RunStatusResult(BaseModel):
    run_directory: Path
    outcome: str = Field(
        description="How the run ended, from the workflow log HERMES writes "
        "when a run ends: completed, failed, or stopped (by Ctrl-C). 'not "
        "finished' when there is no workflow log yet.",
    )
    acquisition: AcquisitionStatus | None
    stages: list[StageStatus]
    problem_files: list[ProblemFile] = Field(
        description="Only files that failed, that a stage has no result for, "
        f"or that logged errors; at most {_SHOWN}.",
    )
    errors: list[LoggedMessage] = Field(
        description=f"Each kind of error once, most common first; at most "
        f"{_SHOWN}. Errors about one file are in problem_files instead.",
    )
    warnings: list[LoggedMessage] = Field(
        description=f"Each kind of warning once, most common first; at most "
        f"{_SHOWN}.",
    )
    message: str


def _parse_log_line(line: str) -> dict | None:
    try:
        return json.loads(line)["record"]
    except (ValueError, KeyError, TypeError):
        # For example the last line of a log file HERMES is still writing.
        return None


def _tail_records(path: Path) -> list[dict]:
    """The log lines in the last megabyte of a log file."""
    with path.open("rb") as handle:
        size = handle.seek(0, 2)
        handle.seek(max(0, size - _TAIL_BYTES))
        lines = handle.read().decode("utf-8", errors="replace").splitlines()
    if size > _TAIL_BYTES:
        lines = lines[1:]  # only the end of a line
    return [record for record in map(_parse_log_line, lines) if record]


def _last_run_records(files: list[Path], *, read_all: bool) -> list[dict]:
    """The warning, error and measurement lines the last run logged.

    `files` are one log file and its older, rotated parts, oldest first. Every
    run appends to the same log files, so only lines from the process that
    wrote the newest line are kept. With `read_all` False only the end of the
    newest file is read.
    """
    if not files:
        return []
    records = _tail_records(files[-1])
    if not records:
        return []
    process = records[-1]["process"]["id"]
    if read_all:
        records = []
        for path in files:
            with path.open(encoding="utf-8", errors="replace") as handle:
                # Decode only the lines that can matter; a long run logs
                # hundreds of megabytes.
                records += [
                    record
                    for line in handle
                    if '"WARNING"' in line
                    or '"ERROR"' in line
                    or '"CRITICAL"' in line
                    or "acquisition.serval.measurement_" in line
                    if (record := _parse_log_line(line))
                ]
    return [
        record
        for record in records
        if record["process"]["id"] == process
        and (
            record["level"]["no"] >= 30
            or record["extra"].get("event_type") in _MEASUREMENT_EVENTS
        )
    ]


def _new_run_started(workflow_log: Path, logs: Path) -> bool:
    """Whether a new run has started since the workflow log was written.

    HERMES writes the workflow log when a run ends, and every run appends to
    the same log files, so a newer log line from another process means a new
    run in this folder is going, or ended before it could write its own.
    """
    written = workflow_log.stat().st_mtime
    for name in ("state.jsonl", "analysis.jsonl", "acquisition.serval.jsonl"):
        path = logs / name
        records = _tail_records(path) if path.is_file() else []
        if not records or records[-1]["time"]["timestamp"] <= written:
            continue
        before = [
            record for record in records if record["time"]["timestamp"] <= written
        ]
        newest = records[-1]["process"]["id"]
        if not before or before[-1]["process"]["id"] != newest:
            return True
    return False


def _count_message(
    groups: dict[tuple[str, ...], LoggedMessage],
    source: str,
    text: str,
    event_type: str = "",
    file: str | None = None,
) -> None:
    """Count a message, treating ones of the same event type that differ only
    in their numbers, or in the file they name, as one kind."""
    kind = text.replace(file, "FILE") if file else text
    key = (source, event_type, re.sub(r"\d+", "N", kind))
    if key in groups:
        groups[key].count += 1
    else:
        groups[key] = LoggedMessage(source=source, text=text, count=1)


def _file_named_in(extra: dict) -> tuple[str, str, str] | None:
    """The stage and file name a log line is about, if it is about one file,
    and the file as the line gives it."""
    if "raw_tpx3_file" in extra:
        value = str(extra["raw_tpx3_file"])
        return "unpacking", Path(value).name, value
    if "pixel_file" in extra:
        value = str(extra["pixel_file"])
        return "photon_reconstruction", Path(value).name, value
    if "raw_file_stem" in extra:
        value = str(extra["raw_file_stem"])
        return "event_reconstruction", f"{value}_event_candidates.parquet", value
    return None


def _file_for_summary(stage: str, summary_name: str) -> str:
    """The name of the file a stage worked on, from its summary's name.

    These are the names the workflow log and the log lines use.
    """
    if stage == "unpacking":
        return summary_name.replace("_unpacker_summary.json", ".tpx3")
    if stage == "photon_reconstruction":
        return summary_name.replace(
            "_photon_reconstruction_summary_", "_pixels_"
        ).replace(".json", ".parquet")
    return summary_name.replace(
        "_event_reconstruction_summary.json", "_event_candidates.parquet"
    )


def _raw_name(file_name: str) -> str:
    """The raw file's name without .tpx3, which every stage's file names
    start with."""
    return re.sub(r"(_chip_.*|_event_candidates)?\.(tpx3|parquet)$", "", file_name)


def _read_summaries(
    analysis: Path,
    warnings: dict[tuple[str, ...], LoggedMessage],
    file_errors: dict[tuple[str, str], list[str]],
) -> dict[str, dict[str, str]]:
    """Each stage's file statuses from the summaries under analysis/logs/.

    A stage writes one summary per file it finishes. A summary with errors
    means the file failed. The warnings and errors are added to `warnings` and
    `file_errors`.
    """
    statuses: dict[str, dict[str, str]] = {}
    for stage in _STAGES:
        folder = analysis / "logs" / stage
        if not folder.is_dir():
            continue
        files = statuses.setdefault(stage, {})
        for path in sorted(folder.glob("*.json")):
            try:
                summary = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # still being written
            name = _file_for_summary(stage, path.name)
            found: list[str] = []
            for section in ("unpacking", "output_parquet", "reconstruction"):
                part = summary.get(section) or {}
                for text in part.get("warnings") or []:
                    _count_message(warnings, f"{stage} summaries", str(text))
                found += [str(text) for text in part.get("errors") or []]
            if found:
                file_errors.setdefault((stage, name), []).extend(found)
            files[name] = "failed" if found else "success"
    return statuses


def _read_workflow_log(path: Path) -> tuple[dict[str, dict[str, str]], dict]:
    """Each stage's file statuses from the workflow log, and its closing line."""
    lines = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    statuses: dict[str, dict[str, str]] = {}
    for line in lines:
        if line.get("event") == "workflow_initialized":
            # A stage the run configured but never reached has no lines.
            for stage in line.get("stages", []):
                if stage != "acquisition":
                    statuses[_WORKFLOW_LOG_STAGES.get(stage, stage)] = {}
        elif line.get("event") == "stage_completed" and "file" in line:
            stage = _WORKFLOW_LOG_STAGES.get(line["stage"], line["stage"])
            statuses.setdefault(stage, {})[Path(line["file"]).name] = line["status"]
    return statuses, (lines[-1] if lines else {})


def _saved_acquisition(record_file: Path) -> AcquisitionStatus | None:
    """The acquisition as HERMES_record.yaml saved it, if the run had one."""
    if not record_file.is_file():
        return None
    record = yaml.safe_load(record_file.read_text(encoding="utf-8"))
    acquisition = record.get("acquisition") if isinstance(record, dict) else None
    if not isinstance(acquisition, dict):
        return None
    result = acquisition.get("result") or {}
    return AcquisitionStatus(
        status=acquisition.get("status"),
        stop_reason=result.get("stop_reason"),
        frames=result.get("frames"),
        dropped_frames=result.get("dropped_frames"),
        warnings=result.get("warnings") or [],
        errors=result.get("errors") or [],
    )


def _logged_acquisition(line: dict | None) -> AcquisitionStatus | None:
    """The acquisition so far, from its newest measurement log line."""
    if line is None:
        return None
    finished = line.get("event_type") == "acquisition.serval.measurement_done"
    return AcquisitionStatus(
        status="measurement finished" if finished else "running",
        stop_reason=line.get("stop_reason"),
        frames=line.get("frames"),
        # The measurement-finished line calls it "dropped".
        dropped_frames=line.get("dropped_frames", line.get("dropped")),
        warnings=[],
        errors=[],
    )


def _count_stages(
    statuses: dict[str, dict[str, str]],
    file_errors: dict[tuple[str, str], list[str]],
    waiting: set[str] | None,
    analysis: Path,
) -> tuple[list[StageStatus], list[ProblemFile]]:
    """Count each stage's files, and list the failed or missing ones.

    A raw file a stage has no result for is "not run" when the stage before
    finished it. While a run is going, `waiting` holds the names of the .tpx3
    files in the run folder, which are waiting to be unpacked; nothing is
    listed as a problem file for not having run yet. Once the run has ended,
    `waiting` is None.
    """
    stages: list[StageStatus] = []
    problems: list[ProblemFile] = []
    earlier = waiting or set()
    for stage in (stage for stage in _STAGES if stage in statuses):
        files = statuses[stage]
        not_run = sorted(earlier - {_raw_name(name) for name in files})
        earlier = {
            _raw_name(name)
            for name, status in files.items()
            if status in ("success", "skipped")
        }
        counts = Counter(files.values())
        stages.append(
            StageStatus(
                stage=stage,
                succeeded=counts["success"],
                skipped=counts["skipped"],
                failed=counts["failed"],
                not_run=len(not_run),
                parquet_files=sum(
                    len(list((analysis / folder).glob("*.parquet")))
                    for folder in _STAGE_OUTPUT_FOLDERS[stage]
                ),
            )
        )
        for name, status in sorted(files.items()):
            found = file_errors.get((stage, name), [])
            if status == "failed" or found:
                problems.append(
                    ProblemFile(
                        stage=stage,
                        file=name,
                        status=status,
                        errors=found[:_ERRORS_PER_FILE],
                        error_count=len(found),
                    )
                )
        if waiting is None:
            problems += [
                ProblemFile(
                    stage=stage,
                    file=f"{raw}.tpx3",
                    status="not run",
                    errors=[],
                    error_count=0,
                )
                for raw in not_run
            ]
    return stages, problems


@mcp_server.tool()
def report_run_status(request: RunStatusRequest) -> RunStatusResult:
    """Report how far a HERMES run got and why anything failed: how it ended,
    the acquisition's status and frame counts, how many files each stage
    finished, skipped, failed or has not run, the failed or missing files with
    their error text, and each kind of warning and error once with a count.
    Works on a run that has ended and on one still going."""
    run = request.run_directory.expanduser().resolve()
    if not run.is_dir():
        raise ValueError(f"run folder does not exist: {run}")
    logs = run / "logs"
    analysis = run / "analysis"
    record_file = run / "HERMES_record.yaml"
    workflow_log = next(
        (
            path
            for path in (logs / "HERMES-workflow.jsonl", run / "HERMES-workflow.jsonl")
            if path.is_file()
        ),
        None,
    )
    if workflow_log is None and not (
        record_file.is_file() or analysis.is_dir() or logs.is_dir()
    ):
        raise ValueError(
            f"no HERMES run found in {run}; give the run folder, which holds "
            f"HERMES_record.yaml, analysis/ and logs/"
        )
    # A workflow log and record left by an earlier run in this folder say
    # nothing about the run going now.
    finished = workflow_log is not None and not _new_run_started(workflow_log, logs)

    errors: dict[tuple[str, ...], LoggedMessage] = {}
    warnings: dict[tuple[str, ...], LoggedMessage] = {}
    file_errors: dict[tuple[str, str], list[str]] = {}
    skipped: set[tuple[str, str]] = set()
    measurement: dict | None = None
    for source, files, read_all in (
        ("analysis.jsonl", sorted(logs.glob("analysis*.jsonl")), True),
        (
            "acquisition.serval.jsonl",
            sorted(logs.glob("acquisition.serval*.jsonl")),
            True,
        ),
        ("state.jsonl", sorted(logs.glob("state.jsonl")), False),
    ):
        for record in _last_run_records(files, read_all=read_all):
            extra = record["extra"]
            event_type = extra.get("event_type") or ""
            if event_type in _MEASUREMENT_EVENTS:
                measurement = extra
                continue
            is_error = record["level"]["no"] >= 40
            named = _file_named_in(extra)
            if named and is_error:
                file_errors.setdefault(named[:2], []).append(record["message"])
                continue
            if named and event_type.endswith(".skipped"):
                skipped.add(named[:2])
            _count_message(
                errors if is_error else warnings,
                source,
                record["message"],
                event_type,
                named[2] if named else None,
            )

    statuses = _read_summaries(analysis, warnings, file_errors)
    if finished:
        statuses, closing = _read_workflow_log(workflow_log)
        outcome = _OUTCOMES.get(closing.get("event"), "unknown")
        if closing.get("error"):
            _count_message(errors, workflow_log.name, closing["error"])
        acquisition = _saved_acquisition(record_file)
    else:
        for stage, name in skipped:
            statuses.setdefault(stage, {})[name] = "skipped"
        outcome = "not finished"
        acquisition = _logged_acquisition(measurement)
    # A file that failed before it wrote a summary is known only from its log
    # line.
    for stage, name in file_errors:
        statuses.setdefault(stage, {}).setdefault(name, "failed")
    stages, problems = _count_stages(
        statuses,
        file_errors,
        None if finished else {path.stem for path in run.rglob("*.tpx3")},
        analysis,
    )

    if finished:
        parts = [f"The run ended: {outcome}."]
    else:
        parts = [
            "The run has not finished, or it ended before HERMES could write "
            "its workflow log, so this comes from the summary and log files "
            "written so far."
        ]
    if acquisition is not None:
        text = f"Acquisition: {acquisition.status}"
        if acquisition.stop_reason:
            text += f" ({acquisition.stop_reason})"
        if acquisition.frames is not None:
            text += (
                f", {acquisition.frames} frame(s), "
                f"{acquisition.dropped_frames} dropped"
            )
        parts.append(text + ".")
    for stage in stages:
        counts = [
            f"{count} {label}"
            for count, label in (
                (stage.succeeded, "succeeded"),
                (stage.skipped, "skipped"),
                (stage.failed, "failed"),
                (stage.not_run, "not run"),
            )
            if count
        ]
        parts.append(f"{stage.stage}: {', '.join(counts) or 'no files'}.")
    if not stages:
        parts.append("No analysis stage has written any results yet.")
    if problems:
        text = (
            f"{len(problems)} file(s) failed, have no result in a stage, or "
            f"logged errors; see problem_files"
        )
        if len(problems) > _SHOWN:
            text += f", which lists the first {_SHOWN}"
        parts.append(text + ".")
    if errors or warnings:
        parts.append(
            f"Found {len(errors)} kind(s) of error and {len(warnings)} kind(s) "
            f"of warning, each listed once with a count."
        )
    if not logs.is_dir():
        parts.append(
            "There is no logs/ folder, so the error text of a file that failed "
            "before writing a summary is not available."
        )

    logger.bind(domain="analysis").info(
        "reported the status of the run in {path}: {outcome}",
        path=str(run),
        outcome=outcome,
    )
    return RunStatusResult(
        run_directory=run,
        outcome=outcome,
        acquisition=acquisition,
        stages=stages,
        problem_files=problems[:_SHOWN],
        errors=sorted(errors.values(), key=lambda m: -m.count)[:_SHOWN],
        warnings=sorted(warnings.values(), key=lambda m: -m.count)[:_SHOWN],
        message=" ".join(parts),
    )


def main() -> None:
    mcp_server.run()
