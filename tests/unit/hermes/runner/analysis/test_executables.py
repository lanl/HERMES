"""Tests for resolving configured HERMES backend executables."""

import os
from pathlib import Path

import pytest

from hermes.runner.analysis.executables import (
    newer_source_than_binary,
    resolve_executable,
)


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


def _write_cpp_source(source_directory: Path, mtime: float) -> Path:
    """Create a minimal C++ source tree and stamp its files to one time."""
    cmake = source_directory / "CMakeLists.txt"
    header = source_directory / "inc" / "unpacker.h"
    source = source_directory / "src" / "unpacker.cpp"
    for path in (cmake, header, source):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// generated for tests\n", encoding="utf-8")
        os.utime(path, (mtime, mtime))
    return source


def test_newer_source_than_binary_skips_when_source_absent(tmp_path: Path) -> None:
    """A wheel install has no source tree, so freshness cannot be judged."""
    binary = tmp_path / "bin/hermes-tpx3-spidr"
    _write_executable(binary)

    assert newer_source_than_binary(binary, tmp_path / "missing-cpp") is None


def test_newer_source_than_binary_none_when_binary_is_newer(tmp_path: Path) -> None:
    """No stale file when every source predates the binary."""
    source_directory = tmp_path / "cpp"
    _write_cpp_source(source_directory, mtime=1000.0)
    binary = tmp_path / "bin/hermes-tpx3-spidr"
    _write_executable(binary)
    os.utime(binary, (2000.0, 2000.0))

    assert newer_source_than_binary(binary, source_directory) is None


def test_newer_source_than_binary_reports_newer_source(tmp_path: Path) -> None:
    """Return the source file that changed after the binary was built."""
    source_directory = tmp_path / "cpp"
    _write_cpp_source(source_directory, mtime=1000.0)
    binary = tmp_path / "bin/hermes-tpx3-spidr"
    _write_executable(binary)
    os.utime(binary, (2000.0, 2000.0))
    edited = source_directory / "src" / "unpacker.cpp"
    os.utime(edited, (3000.0, 3000.0))

    assert newer_source_than_binary(binary, source_directory) == edited


def test_newer_source_than_binary_ignores_tests_and_notes(tmp_path: Path) -> None:
    """Editing files outside inc/src/CMakeLists does not count as stale."""
    source_directory = tmp_path / "cpp"
    _write_cpp_source(source_directory, mtime=1000.0)
    binary = tmp_path / "bin/hermes-tpx3-spidr"
    _write_executable(binary)
    os.utime(binary, (2000.0, 2000.0))
    notes = source_directory / "Notes.md"
    notes.write_text("newer notes\n", encoding="utf-8")
    os.utime(notes, (3000.0, 3000.0))
    test_file = source_directory / "tests" / "packet_tests.cpp"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("// newer test\n", encoding="utf-8")
    os.utime(test_file, (3000.0, 3000.0))

    assert newer_source_than_binary(binary, source_directory) is None
