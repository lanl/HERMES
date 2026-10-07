from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from hermes.runner.acquisition.serval.calibration import (
    ServalCalibrationError,
    load_calibration,
)
from hermes.runner.acquisition.serval.client import ServalClientError
from hermes.state.models.acquisition.serval import CalibrationFiles


class _FakeCalibrationClient:
    """Answers config loads with 200 and records the paths it was asked for.

    A format named in `refuse` is refused the way the real client does it: by
    raising `ServalClientError` that keeps SERVAL's non-200 answer.
    """

    def __init__(self, refuse: dict[str, ServalClientError] | None = None) -> None:
        self.loaded: list[tuple[str, str]] = []
        self._refuse = refuse or {}

    def _answer(self, label: str, server_file_path: str) -> httpx.Response:
        self.loaded.append((label, server_file_path))
        if label in self._refuse:
            raise self._refuse[label]
        return httpx.Response(200, text="Config loaded")

    def load_pixel_config(self, server_file_path: str) -> httpx.Response:
        return self._answer("pixelconfig", server_file_path)

    def load_dacs(self, server_file_path: str) -> httpx.Response:
        return self._answer("dacs", server_file_path)


def _refused(status_code: int, text: str) -> ServalClientError:
    return ServalClientError(
        f"SERVAL GET /config/load returned {status_code}: {text}",
        response=httpx.Response(status_code, text=text),
    )


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


def test_a_refused_pixel_config_is_recorded_and_the_dacs_are_not_loaded(
    tmp_path: Path,
) -> None:
    calibration_files = _write_calibration_files(tmp_path / "sophy")
    run_dir = tmp_path / "run"
    client = _FakeCalibrationClient(
        refuse={"pixelconfig": _refused(400, "File does not start with [chip")}
    )

    state = load_calibration(client, calibration_files, run_dir / "config", run_dir)

    assert state.pixel_config_load.status == "failed"
    assert state.pixel_config_load.http_status_code == 400
    assert state.pixel_config_load.server_response_body == (
        "File does not start with [chip"
    )
    assert state.pixel_config_load.applied_at is None
    # With no pixel config, HERMES does not go on to load the DACs.
    assert [label for label, _path in client.loaded] == ["pixelconfig"]
    assert state.dacs_load is None
    # Both files were still saved under the run.
    assert state.dacs_file.path == Path("config/settings.bpc.dacs")


def test_refused_dacs_after_a_loaded_pixel_config_are_both_recorded(
    tmp_path: Path,
) -> None:
    calibration_files = _write_calibration_files(tmp_path / "sophy")
    run_dir = tmp_path / "run"
    client = _FakeCalibrationClient(
        refuse={"dacs": _refused(400, "Too many chips in the DACs file.")}
    )

    state = load_calibration(client, calibration_files, run_dir / "config", run_dir)

    assert state.pixel_config_load.status == "loaded"
    assert state.dacs_load.status == "failed"
    assert state.dacs_load.http_status_code == 400
    assert state.dacs_load.server_response_body == "Too many chips in the DACs file."


def test_a_load_with_no_answer_is_recorded_as_failed(tmp_path: Path) -> None:
    calibration_files = _write_calibration_files(tmp_path / "sophy")
    run_dir = tmp_path / "run"
    no_answer = ServalClientError("SERVAL GET /config/load could not be sent")
    client = _FakeCalibrationClient(refuse={"pixelconfig": no_answer})

    state = load_calibration(client, calibration_files, run_dir / "config", run_dir)

    assert state.pixel_config_load.status == "failed"
    assert state.pixel_config_load.http_status_code is None
    assert state.pixel_config_load.server_response_body is None
