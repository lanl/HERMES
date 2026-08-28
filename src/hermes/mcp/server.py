"""The bundled HERMES MCP server.

One local MCP server (standard input/output, no network) that ships inside the
HERMES package so any MCP-speaking LLM tool can help a user configure and run a
HERMES analysis. The first slice exposes a single analysis tool that writes a
workflow config and a runnable script for the ``.tpx3`` files in a folder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from loguru import logger
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field, ValidationError

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
            "analysis_directory": "analysis",
            "log_level": _QUIET_LOG_LEVEL,
        },
        "analysis": analysis,
    }

    # Validate against the installed HERMES's real rules before writing. The
    # working directory is pinned here only so the .tpx3 file list resolves; the
    # file written to disk keeps the minimal, portable form (relative paths, no
    # resolved machine paths).
    HermesRecord.model_validate(
        {
            **config,
            "environment": {
                "working_directory": str(directory),
                "analysis_directory": "analysis",
                "log_level": _QUIET_LOG_LEVEL,
            },
        }
    )

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


def main() -> None:
    mcp_server.run()
