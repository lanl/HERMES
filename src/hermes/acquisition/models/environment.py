"""
Environment configuration models for HERMES acquisitions.

These models describe the static workspace layout used when acquiring data with
TPX3Cams. They remain declarative and do not perform filesystem I/O; controllers
can rely on them to build paths before creating directories on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator, model_validator

from .tpx_serval.common import HermesBaseModel, HermesImmutableModel, JsonPath

_RUN_ID_PATTERN = r"run_\d{3}"


def _coerce_path(value: object) -> Path:
    if isinstance(value, JsonPath):
        return value.path
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    raise TypeError("Expected str, Path, or JsonPath instance.")


class NetworkEndpoint(HermesBaseModel):
    """Connectivity metadata for a host that should be reachable during runs."""

    name: str = Field(..., alias="Name", min_length=1, description="Human-readable label (e.g., 'camera').")
    host: str = Field(..., alias="Host", min_length=1, description="Hostname or IP address to reach.")
    reachable: bool = Field(..., alias="Reachable", description="True when the endpoint responded to the latest probe.")
    latency_ms: Optional[float] = Field(
        None,
        alias="LatencyMs",
        ge=0.0,
        description="Last measured round-trip latency in milliseconds, if known.",
    )


class ServalDeployment(HermesImmutableModel):
    """Location of the Serval control application and its resources."""

    host: str = Field(..., alias="Host", min_length=1, description="Hostname/IP where Serval runs.")
    install_dir: JsonPath = Field(..., alias="InstallDir", description="Path to the Serval installation root.")
    virtualenv_dir: Optional[JsonPath] = Field(
        None,
        alias="VirtualEnvDir",
        description="Optional Python virtual environment used for Serval dependencies.",
    )
    binary_path: Optional[JsonPath] = Field(
        None,
        alias="BinaryPath",
        description="Explicit path to the Serval executable if not under InstallDir/bin.",
    )
    config_dir: Optional[JsonPath] = Field(
        None,
        alias="ConfigDir",
        description="Directory containing Serval configuration templates.",
    )


class RunDirectoryLayout(HermesImmutableModel):
    """Derived directory layout for a single acquisition run (e.g., ``run_001``)."""

    run_id: str = Field(
        ..., alias="RunId", pattern=_RUN_ID_PATTERN, description="Run identifier formatted as run_###."
    )
    workspace_dir: JsonPath = Field(..., alias="WorkspaceDir", description="Absolute path to the workspace root.")
    run_dir: JsonPath = Field(..., alias="RunDir", description="Path to the run directory (workspace/run_id).")
    tpx3_data_dir: JsonPath = Field(..., alias="Tpx3DataDir", description="Directory for raw TPX3 data files.")
    config_files_dir: JsonPath = Field(..., alias="ConfigFilesDir", description="Directory for acquisition configuration files.")
    logs_dir: JsonPath = Field(..., alias="LogsDir", description="Directory where loguru emits run logs.")
    images_dir: Optional[JsonPath] = Field(
        None,
        alias="ImagesDir",
        description="Optional directory for preview and image exports.",
    )
    include_images: bool = Field(True, alias="IncludeImages", description="Create the images/ sub-directory when true.")

    @model_validator(mode="before")
    @classmethod
    def _populate_paths(cls, values: object) -> object:
        data = dict(values) if isinstance(values, dict) else values
        if not isinstance(data, dict):
            return data

        workspace_value = data.get("WorkspaceDir") or data.get("workspace_dir")
        if workspace_value is None:
            raise ValueError("WorkspaceDir is required to derive run paths.")
        workspace_path = _coerce_path(workspace_value)

        run_id = data.get("RunId") or data.get("run_id")
        if run_id is None:
            raise ValueError("RunId is required to derive run paths.")

        run_path = workspace_path / run_id
        data.setdefault("RunDir", run_path)
        data.setdefault("Tpx3DataDir", run_path / "tpx3Data")
        data.setdefault("ConfigFilesDir", run_path / "configFiles")
        data.setdefault("LogsDir", run_path / "logs")

        include_images = data.get("IncludeImages")
        if include_images is None:
            include_images = True
            data["IncludeImages"] = include_images

        if include_images:
            data.setdefault("ImagesDir", run_path / "images")
        else:
            data.setdefault("ImagesDir", None)

        return data

    @model_validator(mode="after")
    def _validate_consistency(self) -> RunDirectoryLayout:  # type: ignore[override]
        workspace_path = self.workspace_dir.path
        expected_run_dir = workspace_path / self.run_id
        if self.run_dir.path != expected_run_dir:
            raise ValueError(
                f"RunDir must resolve to {expected_run_dir.as_posix()} (got {self.run_dir.path.as_posix()})."
            )

        expected_layout = {
            "tpx3_data_dir": expected_run_dir / "tpx3Data",
            "config_files_dir": expected_run_dir / "configFiles",
            "logs_dir": expected_run_dir / "logs",
        }
        if self.include_images and self.images_dir is not None:
            expected_layout["images_dir"] = expected_run_dir / "images"

        for attr, expected_path in expected_layout.items():
            actual = getattr(self, attr)
            if actual is None:
                raise ValueError(f"{attr} may not be None when IncludeImages=True.")
            if actual.path != expected_path:
                raise ValueError(
                    f"{attr} must resolve to {expected_path.as_posix()} (got {actual.path.as_posix()})."
                )

        if not self.include_images and self.images_dir is not None:
            raise ValueError("ImagesDir should be omitted when IncludeImages=False.")

        return self

    @property
    def required_directories(self) -> List[Path]:
        """Return the directories that must exist for this run."""

        dirs = [
            self.tpx3_data_dir.path,
            self.config_files_dir.path,
            self.logs_dir.path,
        ]
        if self.include_images and self.images_dir is not None:
            dirs.append(self.images_dir.path)
        return dirs


class WorkspaceLayout(HermesImmutableModel):
    """Workspace template used to generate run directories on demand."""

    name: str = Field(..., alias="Name", min_length=1, description="Workspace label (e.g., 'beamline_a').")
    base_dir: Optional[JsonPath] = Field(
        None,
        alias="BaseDir",
        description="Parent directory under which the workspace folder is created. Defaults to CWD when omitted.",
    )
    include_images: bool = Field(
        True,
        alias="IncludeImages",
        description="Create images/ for runs by default unless overridden per run.",
    )

    @property
    def workspace_dir(self) -> Path:
        """Absolute path to the workspace directory (base_dir / name)."""

        base = self.base_dir.path if self.base_dir is not None else Path.cwd()
        return base / self.name

    @staticmethod
    def format_run_id(run_number: int) -> str:
        if run_number < 0:
            raise ValueError("Run number must be non-negative.")
        return f"run_{run_number:03d}"

    def make_run_layout(self, run_number: int, *, include_images: Optional[bool] = None) -> RunDirectoryLayout:
        """Create a run directory layout for the given numeric run identifier."""

        run_id = self.format_run_id(run_number)
        images_flag = self.include_images if include_images is None else include_images
        return RunDirectoryLayout(
            run_id=run_id,
            workspace_dir=self.workspace_dir,
            include_images=images_flag,
        )


class AcquisitionEnvironment(HermesImmutableModel):
    """Top-level environment definition combining workspace and connectivity state."""

    name: str = Field(..., alias="Name", min_length=1, description="Environment identifier (e.g., 'lab-tpx3').")
    workspace: WorkspaceLayout = Field(..., alias="Workspace", description="Workspace directory template.")
    camera_endpoint: NetworkEndpoint = Field(
        ..., alias="CameraEndpoint", description="Primary TPX3 camera network target."
    )
    network_checks: List[NetworkEndpoint] = Field(
        default_factory=list,
        alias="NetworkChecks",
        description="Additional hosts (DAQ server, storage, etc.) to verify before acquisition.",
    )
    serval: ServalDeployment = Field(..., alias="Serval", description="Serval deployment metadata.")

    @field_validator("network_checks")
    @classmethod
    def _deduplicate_checks(cls, checks: List[NetworkEndpoint]) -> List[NetworkEndpoint]:
        seen = set[str]()
        unique: List[NetworkEndpoint] = []
        for check in checks:
            key = check.host.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(check)
        return unique

    @property
    def all_endpoints(self) -> List[NetworkEndpoint]:
        """Return the camera plus any additional network checks (camera first)."""

        return [self.camera_endpoint, *self.network_checks]