from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes.state.models.environment import DirectoryState, RuntimeEnvironment


def test_runtime_environment_defaults_working_dir_to_current_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    environment = RuntimeEnvironment()

    assert environment.working_dir.required
    assert environment.working_dir.path == tmp_path
    assert environment.working_dir.resolved_path == tmp_path.resolve()


def test_runtime_environment_only_requires_working_dir_by_default(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-001"

    environment = RuntimeEnvironment(working_dir=DirectoryState(path=run_dir))

    assert environment.working_dir.required
    assert environment.working_dir.path == run_dir
    assert environment.working_dir.resolved_path == run_dir.resolve()
    assert environment.raw_data_dir.required is False
    assert environment.raw_data_dir.resolved_path is None
    assert environment.preview_dir.required is False
    assert environment.preview_dir.resolved_path is None
    assert not (run_dir / "data").exists()


def test_runtime_environment_resolves_explicit_relative_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-001"

    environment = RuntimeEnvironment(
        working_dir=run_dir,
        preview_dir="fast-preview",
        raw_data_dir={"path": "data/tpx3", "required": True},
        hermes_tpx3_spidr_binary="bin/hermes-tpx3-spidr",
    )

    assert environment.preview_dir.path == Path("fast-preview")
    assert environment.preview_dir.resolved_path == (run_dir / "fast-preview").resolve()
    assert environment.raw_data_dir.required
    assert environment.raw_data_dir.path == Path("data/tpx3")
    assert environment.raw_data_dir.resolved_path == (run_dir / "data" / "tpx3").resolve()
    assert environment.hermes_tpx3_spidr_binary == (run_dir / "bin/hermes-tpx3-spidr").resolve()


def test_runtime_environment_keeps_explicit_absolute_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-001"
    raw_dir = tmp_path / "external-fast-disk" / "tpx3"

    environment = RuntimeEnvironment(
        working_dir=run_dir,
        raw_data_dir=raw_dir,
    )

    assert environment.raw_data_dir.path == raw_dir
    assert environment.raw_data_dir.resolved_path == raw_dir.resolve()


def test_runtime_environment_required_directory_can_be_unresolved_until_checked(
    tmp_path: Path,
) -> None:
    environment = RuntimeEnvironment(
        working_dir=tmp_path,
        raw_data_dir=DirectoryState(required=True),
    )

    assert environment.raw_data_dir.required
    assert environment.raw_data_dir.resolved_path is None
    with pytest.raises(ValueError, match="required directories are unresolved: raw_data_dir"):
        environment.require_required_directories_resolved()


def test_runtime_environment_workflow_required_directory_must_be_resolved(
    tmp_path: Path,
) -> None:
    environment = RuntimeEnvironment(working_dir=tmp_path)

    with pytest.raises(ValueError, match="raw_data_dir must have a resolved_path"):
        environment.require_directories_resolved(["raw_data_dir"])


def test_runtime_environment_rejects_overlapping_output_dirs(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="preview_dir must not overlap"):
        RuntimeEnvironment(
            working_dir=tmp_path,
            raw_data_dir="outputs",
            preview_dir="outputs",
        )


def test_runtime_environment_can_explicitly_allow_overlapping_dirs(tmp_path: Path) -> None:
    environment = RuntimeEnvironment(
        working_dir=tmp_path,
        raw_data_dir="outputs",
        preview_dir="outputs",
        allow_overlapping_output_dirs=True,
    )

    assert environment.raw_data_dir.resolved_path == environment.preview_dir.resolved_path
