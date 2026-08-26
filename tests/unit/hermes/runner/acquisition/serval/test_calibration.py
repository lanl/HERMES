from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from hermes.runner.acquisition.serval.calibration import (
    ServalCalibrationError,
    load_calibration,
)
from hermes.state.models.acquisition.serval import CalibrationFiles


class _FakeCalibrationClient:
    """Answers config loads with 200 and records the paths it was asked for."""

    def __init__(self) -> None:
        self.loaded: list[tuple[str, str]] = []

    def load_pixel_config(self, server_file_path: str) -> httpx.Response:
        self.loaded.append(("pixelconfig", server_file_path))
        return httpx.Response(200, text="Config loaded")

    def load_dacs(self, server_file_path: str) -> httpx.Response:
        self.loaded.append(("dacs", server_file_path))
        return httpx.Response(200, text="Config loaded")


def _write_calibration_files(source_dir: Path) -> CalibrationFiles:
    source_dir.mkdir(parents=True, exist_ok=True)
    bpc = source_dir / "settings.bpc"
    dacs = source_dir / "settings.bpc.dacs"
    bpc.write_bytes(b"pixel-config-bytes")
    dacs.write_text("dac-values")
    return CalibrationFiles(pixel_config_file=bpc, dacs_file=dacs)


def test_load_calibration_saves_hashes_and_loads(tmp_path: Path) -> None:
    calibration_files = _write_calibration_files(tmp_path / "sophy")
    run_dir = tmp_path / "run"
    config_dir = run_dir / "config"
    client = _FakeCalibrationClient()

    state = load_calibration(client, calibration_files, config_dir, run_dir)

    # Files were copied into the run's config directory.
    assert (config_dir / "settings.bpc").is_file()
    assert (config_dir / "settings.bpc.dacs").is_file()

    # Saved paths are recorded relative to the run directory, with real hashes.
    assert state.pixel_config_file.path == Path("config/settings.bpc")
    assert state.dacs_file.path == Path("config/settings.bpc.dacs")
    expected_hash = hashlib.sha256(b"pixel-config-bytes").hexdigest()
    assert state.pixel_config_file.file_hash == expected_hash

    # Both were loaded into SERVAL from their absolute saved paths.
    assert client.loaded == [
        ("pixelconfig", str(config_dir / "settings.bpc")),
        ("dacs", str(config_dir / "settings.bpc.dacs")),
    ]
    assert state.pixel_config_load.http_status_code == 200
    assert state.pixel_config_load.status == "loaded"
    assert state.dacs_load.server_response_body == "Config loaded"


def test_load_calibration_raises_when_file_missing(tmp_path: Path) -> None:
    calibration_files = _write_calibration_files(tmp_path / "sophy")
    calibration_files.pixel_config_file.unlink()
    run_dir = tmp_path / "run"
    client = _FakeCalibrationClient()

    with pytest.raises(ServalCalibrationError, match="not found"):
        load_calibration(client, calibration_files, run_dir / "config", run_dir)
