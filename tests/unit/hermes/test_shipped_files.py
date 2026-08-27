from __future__ import annotations

from pathlib import Path

import pytest

from hermes import shipped_files
from hermes.shipped_files import default_timewalk_calibration, shipped_file

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_shipped_file_falls_back_to_the_repository_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Point the environment prefix at an empty folder so there is no installed
    # copy and the lookup has to fall back to the repository root.
    monkeypatch.setattr(shipped_files.sys, "prefix", str(tmp_path))

    found = shipped_file("calibrations/tpx3/time-walk_example.json")

    assert found == _REPO_ROOT / "calibrations" / "tpx3" / "time-walk_example.json"
    assert found.is_file()


def test_default_timewalk_calibration_points_at_the_shipped_file() -> None:
    found = default_timewalk_calibration()

    assert found.name == "time-walk_example.json"
    assert found.is_file()


def test_shipped_file_prefers_the_installed_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = tmp_path / "share" / "hermes" / "calibrations" / "example.json"
    installed.parent.mkdir(parents=True)
    installed.write_text("{}")
    monkeypatch.setattr(shipped_files.sys, "prefix", str(tmp_path))

    assert shipped_file("calibrations/example.json") == installed


def test_shipped_file_raises_when_missing() -> None:
    with pytest.raises(FileNotFoundError, match="does/not/exist.json"):
        shipped_file("does/not/exist.json")
