"""Tests for resolving configured HERMES backend executables."""

from pathlib import Path

import pytest

from hermes.runner.analysis.executables import resolve_executable


def _write_executable(path: Path) -> None:
    """Create a small executable file for resolver tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def test_resolve_executable_accepts_explicit_path(tmp_path: Path) -> None:
    """Resolve an explicit relative or absolute executable path."""
    executable = tmp_path / "bin/hermes-tpx3-spidr"
    _write_executable(executable)

    assert resolve_executable(executable) == executable.resolve()


def test_resolve_executable_finds_bare_name_on_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use PATH lookup when configuration contains only a program name."""
    executable = tmp_path / "bin/hermes-photon-clusterer"
    _write_executable(executable)
    monkeypatch.setenv("PATH", str(executable.parent))

    assert resolve_executable(Path(executable.name)) == executable.resolve()


def test_resolve_executable_prefers_local_file_over_path_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve a bare name locally when it names a file in the current directory."""
    executable = tmp_path / "hermes-tpx3-spidr"
    _write_executable(executable)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    assert resolve_executable(Path(executable.name)) == executable.resolve()


def test_resolve_executable_rejects_bare_name_not_on_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a bare program name that is not found on PATH."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    with pytest.raises(FileNotFoundError, match="was not found on PATH"):
        resolve_executable(Path("hermes-tpx3-spidr"))


def test_resolve_executable_rejects_missing_program(tmp_path: Path) -> None:
    """Report an explicit executable path that does not exist."""
    missing_path = tmp_path / "bin/hermes-event-reconstructor"

    with pytest.raises(FileNotFoundError, match="is not a file"):
        resolve_executable(missing_path)


def test_resolve_executable_rejects_non_executable_file(tmp_path: Path) -> None:
    """Report a configured program file without execute permission."""
    executable = tmp_path / "bin/hermes-tpx3-spidr"
    executable.parent.mkdir(parents=True)
    executable.write_text("not executable", encoding="utf-8")

    with pytest.raises(PermissionError, match="is not executable"):
        resolve_executable(executable)
