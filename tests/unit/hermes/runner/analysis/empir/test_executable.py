"""Tests for resolving configured EMPIR executables."""

from pathlib import Path

import pytest

from hermes.runner.analysis.empir._executable import resolve_executable


def _write_executable(path: Path) -> None:
    """Create a small executable file for resolver tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def test_resolve_executable_accepts_explicit_path(tmp_path: Path) -> None:
    """Resolve an explicit relative or absolute executable path."""
    executable = tmp_path / "bin/empir_photon2event"
    _write_executable(executable)

    assert resolve_executable(executable) == executable.resolve()


def test_resolve_executable_finds_bare_name_on_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use PATH lookup when configuration contains only a program name."""
    executable = tmp_path / "bin/empir_event2image"
    _write_executable(executable)
    monkeypatch.setenv("PATH", str(executable.parent))

    assert resolve_executable(Path(executable.name)) == executable.resolve()


def test_resolve_executable_rejects_missing_program(tmp_path: Path) -> None:
    """Report an explicit executable path that does not exist."""
    missing_path = tmp_path / "bin/empir_pixel2photon_tpx3spidr"

    with pytest.raises(FileNotFoundError, match="is not a file"):
        resolve_executable(missing_path)


def test_resolve_executable_rejects_non_executable_file(tmp_path: Path) -> None:
    """Report a configured program file without execute permission."""
    executable = tmp_path / "bin/empir_photon2event"
    executable.parent.mkdir(parents=True)
    executable.write_text("not executable", encoding="utf-8")

    with pytest.raises(PermissionError, match="is not executable"):
        resolve_executable(executable)
