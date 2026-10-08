from __future__ import annotations

import os
from pathlib import Path

import pytest

import hermes.mcp.server as server
from hermes.mcp.server import check_installation

_HERMES_PROGRAMS = (
    "hermes-tpx3-spidr",
    "hermes-photon-clusterer",
    "hermes-event-reconstructor",
)
_EMPIR_PROGRAMS = (
    "empir_pixel2photon_tpx3spidr",
    "empir_photon2event",
    "empir_event2image",
)


def _write_programs(folder: Path, names: tuple[str, ...]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = folder / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)


@pytest.fixture
def bin_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty folder that is the only one on PATH, with no C++ source."""
    folder = tmp_path / "bin"
    folder.mkdir()
    monkeypatch.setenv("PATH", str(folder))
    monkeypatch.setattr(server, "_CPP_SOURCE", tmp_path / "no-source")
    return folder


def test_everything_present(bin_folder: Path) -> None:
    _write_programs(bin_folder, _HERMES_PROGRAMS + _EMPIR_PROGRAMS)

    result = check_installation()

    assert result.hermes_version
    assert [p.name for p in result.programs] == list(_HERMES_PROGRAMS)
    for program in result.programs + result.empir_programs:
        assert program.path == (bin_folder / program.name).resolve()
        assert program.built is not None
        assert program.problem is None
    assert result.timewalk_calibration is not None
    assert result.timewalk_calibration.is_file()
    assert set(result.python_packages) == {"pydantic", "pyarrow", "numpy", "mcp"}
    assert "are present" in result.message
    assert "EMPIR is installed" in result.message


def test_a_cpp_program_missing_from_path(bin_folder: Path) -> None:
    _write_programs(bin_folder, ("hermes-tpx3-spidr", "hermes-event-reconstructor"))

    result = check_installation()

    clusterer = result.programs[1]
    assert clusterer.name == "hermes-photon-clusterer"
    assert clusterer.path is None
    assert clusterer.built is None
    assert "not found on PATH" in (clusterer.problem or "")
    assert "hermes-photon-clusterer cannot be used" in result.message
    assert "pixi reinstall hermes" in result.message


def test_empir_missing_is_reported_but_not_a_problem(bin_folder: Path) -> None:
    _write_programs(bin_folder, _HERMES_PROGRAMS)

    result = check_installation()

    assert all(p.path is None for p in result.empir_programs)
    assert "are present" in result.message
    assert "EMPIR is not on PATH" in result.message


def test_a_program_built_before_its_source_changed(
    bin_folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_programs(bin_folder, _HERMES_PROGRAMS)
    source = tmp_path / "backends" / "unpackers" / "tpx3-spidr" / "cpp" / "src"
    source.mkdir(parents=True)
    edited = source / "unpacker.cpp"
    edited.write_text("// edited\n", encoding="utf-8")
    built = (bin_folder / "hermes-tpx3-spidr").stat().st_mtime
    os.utime(edited, (built + 60, built + 60))
    monkeypatch.setattr(server, "_CPP_SOURCE", tmp_path / "backends")

    result = check_installation()

    assert result.programs[0].newer_source_file == edited
    assert result.programs[1].newer_source_file is None
    assert "hermes-tpx3-spidr was built before" in result.message
