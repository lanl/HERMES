"""The bundled HERMES MCP server.

One local MCP server (standard input/output, no network) that ships inside the
HERMES package so any MCP-speaking LLM tool can help a user configure and run a
HERMES analysis. Its tools write a workflow config and a runnable script for the
``.tpx3`` files in a folder, check a config, and check the installation.
"""

from __future__ import annotations

import json
from datetime import datetime
from importlib.metadata import PackageNotFoundError, distribution, version
from pathlib import Path
from typing import Literal

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
        description="Where HERMES was installed from: a git URL or a folder.",
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
        python_packages={name: _package_version(name) for name in _PYTHON_PACKAGES},
        message=f"HERMES {hermes.version}. " + " ".join(notes),
    )


def main() -> None:
    mcp_server.run()
