from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes.state.models.environment import DirectoryState, RuntimeEnvironment


def test_runtime_environment_defaults_working_directory_to_current_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    environment = RuntimeEnvironment()

    assert environment.working_directory.required
    assert environment.working_directory.path == tmp_path
    assert environment.working_directory.resolved_path == tmp_path.resolve()


def test_runtime_environment_only_requires_working_directory_by_default(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-001"

    environment = RuntimeEnvironment(working_directory=DirectoryState(path=run_dir))

    assert environment.working_directory.required
    assert environment.working_directory.path == run_dir
    assert environment.working_directory.resolved_path == run_dir.resolve()
    assert environment.raw_data_directory.required is False
    assert environment.raw_data_directory.resolved_path is None
    assert environment.preview_directory.required is False
    assert environment.preview_directory.resolved_path is None
    assert not (run_dir / "data").exists()


def test_runtime_environment_resolves_explicit_relative_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-001"

    environment = RuntimeEnvironment(
        working_directory=run_dir,
        preview_directory="fast-preview",
        raw_data_directory={"path": "data/tpx3", "required": True},
    )

    assert environment.preview_directory.path == Path("fast-preview")
    assert environment.preview_directory.resolved_path == (run_dir / "fast-preview").resolve()
    assert environment.raw_data_directory.required
    assert environment.raw_data_directory.path == Path("data/tpx3")
    assert environment.raw_data_directory.resolved_path == (run_dir / "data" / "tpx3").resolve()


def test_runtime_environment_resolves_relative_paths_against_cwd_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # With working_directory omitted it defaults to the current directory, and a
    # relative sub-directory must still resolve against that default rather than
    # being left unresolved.
    monkeypatch.chdir(tmp_path)

    environment = RuntimeEnvironment(analysis_directory="analysis")

    assert environment.working_directory.resolved_path == tmp_path.resolve()
    assert environment.analysis_directory.path == Path("analysis")
    assert environment.analysis_directory.resolved_path == (tmp_path / "analysis").resolve()


def test_runtime_environment_keeps_explicit_absolute_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-001"
    raw_dir = tmp_path / "external-fast-disk" / "tpx3"

    environment = RuntimeEnvironment(
        working_directory=run_dir,
        raw_data_directory=raw_dir,
    )

    assert environment.raw_data_directory.path == raw_dir
    assert environment.raw_data_directory.resolved_path == raw_dir.resolve()


def test_runtime_environment_required_directory_can_be_unresolved_until_checked(
    tmp_path: Path,
) -> None:
    environment = RuntimeEnvironment(
        working_directory=tmp_path,
        raw_data_directory=DirectoryState(required=True),
    )

    assert environment.raw_data_directory.required
    assert environment.raw_data_directory.resolved_path is None
    with pytest.raises(ValueError, match="required directories are unresolved: raw_data_directory"):
        environment.require_required_directories_resolved()


def test_runtime_environment_workflow_required_directory_must_be_resolved(
    tmp_path: Path,
) -> None:
    environment = RuntimeEnvironment(working_directory=tmp_path)

    with pytest.raises(ValueError, match="raw_data_directory must have a resolved_path"):
        environment.require_directories_resolved(["raw_data_directory"])


def test_runtime_environment_rejects_overlapping_output_dirs(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="preview_directory must not overlap"):
        RuntimeEnvironment(
            working_directory=tmp_path,
            raw_data_directory="outputs",
            preview_directory="outputs",
        )


def test_runtime_environment_can_explicitly_allow_overlapping_dirs(tmp_path: Path) -> None:
    environment = RuntimeEnvironment(
        working_directory=tmp_path,
        raw_data_directory="outputs",
        preview_directory="outputs",
        allow_overlapping_output_dirs=True,
    )

    assert environment.raw_data_directory.resolved_path == environment.preview_directory.resolved_path
