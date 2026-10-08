"""The bundled HERMES MCP server.

One local MCP server (standard input/output, no network) that ships inside the
HERMES package so any MCP-speaking LLM tool can help a user configure and run a
HERMES analysis. Its tools write a workflow config and a runnable script for the
``.tpx3`` files in a folder, check a config, check the installation, and
describe a run's Parquet output files.
"""

from __future__ import annotations

import json
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

# HERMES always writes its full, structured logs to JSON-lines files on disk.
# This level only sets how much a run prints to the terminal, so keep runs quiet
# by showing errors and worse on screen while the log files keep everything.
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

    unpacking = {**_UNPACKING, "tpx3_files": [{"path": name} for name in raw_files]}
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
            "log_level": _QUIET_LOG_LEVEL,
        },
        "analysis": analysis,
    }

    # Validate against the installed HERMES's real rules before writing. The
    # working directory is written into the config so the .tpx3 file list
    # resolves no matter which directory the run script is launched from.
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
        "empty when the files have no timestamp_canonical column.",
    )
    last_timestamp_canonical: int | float | None
    time_span_seconds: float | None
    example_file: str
    example_rows: list[dict[str, Any]]
    problems: list[str] = Field(
        description="Files that could not be read, for example one still "
        "being written; they are left out of the counts.",
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
    """Read the timestamp_canonical range from the column statistics."""
    names = metadata.schema.names
    if "timestamp_canonical" not in names:
        return None
    column = names.index("timestamp_canonical")
    lows: list[int | float] = []
    highs: list[int | float] = []
    for group in range(metadata.num_row_groups):
        statistics = metadata.row_group(group).column(column).statistics
        if statistics is not None and statistics.has_min_max:
            lows.append(statistics.min)
            highs.append(statistics.max)
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
    for path, metadata in readable:
        total_bytes += path.stat().st_size
        row_count += metadata.num_rows
        time_range = _timestamp_range(metadata)
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

    first = min(lows) if lows else None
    last = max(highs) if highs else None
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
    unreadable = sum(len(summary.problems) for summary in folders)
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
        f"directly; multiply by tick_seconds to get seconds."
    )
    if unreadable:
        message += (
            f" {unreadable} file(s) could not be read and are left out; see "
            f"each folder's problems."
        )
    return OutputFilesResult(
        analysis_directory=directory,
        tick_seconds=_TICK_SECONDS,
        folders=folders,
        message=message,
    )


def main() -> None:
    mcp_server.run()
