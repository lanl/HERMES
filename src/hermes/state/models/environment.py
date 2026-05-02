from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from hermes.state.models.shared_models import StrictBaseModel

DIRECTORY_FIELDS = (
    "working_dir",
    "data_dir",
    "raw_data_dir",
    "analyzed_data_dir",
    "log_dir",
    "preview_dir",
    "config_dir",
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

    working_dir: DirectoryState = Field(default_factory=_default_working_dir)
    data_dir: DirectoryState = Field(default_factory=_directory_state)
    raw_data_dir: DirectoryState = Field(default_factory=_directory_state)
    analyzed_data_dir: DirectoryState = Field(default_factory=_directory_state)
    log_dir: DirectoryState = Field(default_factory=_directory_state)
    preview_dir: DirectoryState = Field(default_factory=_directory_state)
    config_dir: DirectoryState = Field(default_factory=_directory_state)
    empir_path: Path | None = None
    empir_version: str | None = None
    hermes_tpx3_spidr_binary: Path | None = None
    hermes_tpx3_spidr_version: str | None = None
    hermes_version: str | None = None
    python_version: str | None = None
    platform: str | None = None
    allow_overlapping_output_dirs: bool = Field(default=False)

    @model_validator(mode="before")
    @classmethod
    def resolve_directory_paths(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("working_dir") is None:
            return data

        resolved = dict(data)
        working_dir_base = _working_dir_base(resolved["working_dir"])
        resolved["working_dir"] = _normalize_directory_input(
            resolved["working_dir"],
            base=None,
            required_default=True,
        )
        resolved["working_dir"]["required"] = True

        for key in DIRECTORY_FIELDS[1:]:
            if resolved.get(key) is not None:
                resolved[key] = _normalize_directory_input(
                    resolved[key],
                    base=working_dir_base,
                    required_default=False,
                )

        for key in ("config_dir", "empir_path", "hermes_tpx3_spidr_binary"):
            if key not in DIRECTORY_FIELDS and resolved.get(key) is not None:
                resolved[key] = _resolve_path(resolved[key], working_dir_base)

        return resolved

    @model_validator(mode="after")
    def validate_working_dir(self) -> RuntimeEnvironment:
        if not self.working_dir.required:
            msg = "working_dir is intrinsically required"
            raise ValueError(msg)
        if self.working_dir.resolved_path is None:
            msg = "working_dir must have a resolved_path"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def reject_overlapping_output_dirs(self) -> RuntimeEnvironment:
        if self.allow_overlapping_output_dirs:
            return self

        output_dirs = {
            "raw_data_dir": self.raw_data_dir.resolved_path,
            "analyzed_data_dir": self.analyzed_data_dir.resolved_path,
            "preview_dir": self.preview_dir.resolved_path,
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
