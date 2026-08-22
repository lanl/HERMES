from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from hermes.state.models.shared_models import StrictBaseModel

DIRECTORY_FIELDS = (
    "working_directory",
    "run_directory",
    "raw_data_directory",
    "analysis_directory",
    "log_directory",
    "preview_directory",
    "config_file",
)


def _resolve_path(value: object, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if base is not None and not path.is_absolute():
        path = base / path
    return path.resolve(strict=False)


class DirectoryState(StrictBaseModel):
    """User-requested and resolved state for a directory used by HERMES."""

    path: Path | None = None
    required: bool = False
    resolved_path: Path | None = None

    @model_validator(mode="before")
    @classmethod
    def parse_scalar_path(cls, data: Any) -> Any:
        if isinstance(data, str | Path):
            return {"path": data}
        return data

    @property
    def resolved(self) -> bool:
        return self.resolved_path is not None

    def require_resolved(self, name: str) -> None:
        if self.resolved_path is None:
            msg = f"{name} must have a resolved_path before it can be used"
            raise ValueError(msg)


def _directory_state(required: bool = False) -> DirectoryState:
    return DirectoryState(required=required)


def _default_working_dir() -> DirectoryState:
    path = Path.cwd()
    return DirectoryState(
        path=path,
        required=True,
        resolved_path=path.resolve(strict=False),
    )


def _normalize_directory_input(
    value: object,
    *,
    base: Path | None,
    required_default: bool,
) -> dict[str, object]:
    if isinstance(value, DirectoryState):
        data = value.model_dump()
    elif isinstance(value, str | Path):
        data = {"path": value}
    elif isinstance(value, dict):
        data = dict(value)
    else:
        msg = "directory fields must be paths or directory-state mappings"
        raise TypeError(msg)

    data.setdefault("required", required_default)

    if data.get("path") is not None:
        data["path"] = Path(data["path"]).expanduser()

    if data.get("resolved_path") is not None:
        data["resolved_path"] = _resolve_path(data["resolved_path"], base)
    elif data.get("path") is not None:
        data["resolved_path"] = _resolve_path(data["path"], base)

    return data


def _working_dir_base(value: object) -> Path | None:
    if isinstance(value, DirectoryState):
        if value.resolved_path is not None:
            return _resolve_path(value.resolved_path)
        if value.path is not None:
            return _resolve_path(value.path)
        return None

    if isinstance(value, str | Path):
        return _resolve_path(value)

    if isinstance(value, dict):
        if value.get("resolved_path") is not None:
            return _resolve_path(value["resolved_path"])
        if value.get("path") is not None:
            return _resolve_path(value["path"])

    return None


class RuntimeEnvironment(StrictBaseModel):
    """Directory state and tool provenance for a HERMES run."""

    working_directory: DirectoryState = Field(default_factory=_default_working_dir)
    run_directory: DirectoryState = Field(default_factory=_directory_state)
    raw_data_directory: DirectoryState = Field(default_factory=_directory_state)
    analysis_directory: DirectoryState = Field(default_factory=_directory_state)
    log_directory: DirectoryState = Field(default_factory=_directory_state)
    preview_directory: DirectoryState = Field(default_factory=_directory_state)
    config_file: DirectoryState = Field(default_factory=_directory_state)
    hermes_version: str | None = None
    python_version: str | None = None
    platform: str | None = None
    allow_overlapping_output_dirs: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    @model_validator(mode="before")
    @classmethod
    def resolve_directory_paths(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        resolved = dict(data)

        # working_directory defaults to the current directory when omitted, and
        # every relative sub-directory resolves against it. Fill that default in
        # here so the sub-directories still resolve when it is left out.
        if resolved.get("working_directory") is None:
            resolved["working_directory"] = Path.cwd()
        working_dir_base = _working_dir_base(resolved["working_directory"])
        resolved["working_directory"] = _normalize_directory_input(
            resolved["working_directory"],
            base=None,
            required_default=True,
        )
        resolved["working_directory"]["required"] = True

        # The run directory resolves against the working directory. Every other
        # sub-directory then resolves under the run directory when one is set,
        # so a run lays out as
        # <working_directory>/<run_directory>/<sub_directory>. With no run
        # directory, the sub-directories resolve directly under the working
        # directory.
        sub_directory_base = working_dir_base
        if resolved.get("run_directory") is not None:
            resolved["run_directory"] = _normalize_directory_input(
                resolved["run_directory"],
                base=working_dir_base,
                required_default=False,
            )
            sub_directory_base = (
                resolved["run_directory"].get("resolved_path") or working_dir_base
            )

        for key in DIRECTORY_FIELDS[2:]:
            if resolved.get(key) is not None:
                resolved[key] = _normalize_directory_input(
                    resolved[key],
                    base=sub_directory_base,
                    required_default=False,
                )

        return resolved

    @model_validator(mode="after")
    def validate_working_dir(self) -> RuntimeEnvironment:
        if not self.working_directory.required:
            msg = "working_directory is intrinsically required"
            raise ValueError(msg)
        if self.working_directory.resolved_path is None:
            msg = "working_directory must have a resolved_path"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def reject_overlapping_output_dirs(self) -> RuntimeEnvironment:
        if self.allow_overlapping_output_dirs:
            return self

        output_dirs = {
            "raw_data_directory": self.raw_data_directory.resolved_path,
            "analysis_directory": self.analysis_directory.resolved_path,
            "preview_directory": self.preview_directory.resolved_path,
        }
        seen: dict[Path, str] = {}
        for name, path in output_dirs.items():
            if path is None:
                continue
            if path in seen:
                msg = f"{name} must not overlap with {seen[path]} unless explicitly allowed"
                raise ValueError(msg)
            seen[path] = name
        return self

    def unresolved_required_directories(self) -> list[str]:
        return [
            name
            for name in DIRECTORY_FIELDS
            if getattr(self, name).required and not getattr(self, name).resolved
        ]

    def require_required_directories_resolved(self) -> None:
        missing = self.unresolved_required_directories()
        if missing:
            msg = "required directories are unresolved: " + ", ".join(missing)
            raise ValueError(msg)

    def require_directories_resolved(self, names: Iterable[str]) -> None:
        for name in names:
            if name not in DIRECTORY_FIELDS:
                msg = f"unknown directory field: {name}"
                raise ValueError(msg)
            getattr(self, name).require_resolved(name)
