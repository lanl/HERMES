"""Save this run's SoPhy calibration files and load them into SERVAL.

HERMES never generates calibration files; SoPhy does. HERMES takes the
user-named `.bpc` and `.dacs` paths, copies each into the run's `config`
directory, records the saved path and its SHA-256, then asks SERVAL to load
each one. Loading is a GET whose `file` path SERVAL resolves on its own host
(here, the local machine), so we point it at the saved copies.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

import httpx
from loguru import logger

from hermes.runner.acquisition.serval.client import ServalClient
from hermes.state.models.acquisition.serval import (
    CalibrationFiles,
    CalibrationState,
    DacsFile,
    DacsLoad,
    PixelConfigFile,
    PixelConfigLoad,
)

_LOGGER = logger.bind(
    domain="acquisition",
    backend="serval",
    step="serval_calibration",
)

# SERVAL answers a load with a short line of text; keep only the start of it.
_MAX_RESPONSE_BODY_CHARS = 500
_HASH_CHUNK_BYTES = 65536

_LoadModel = TypeVar("_LoadModel", PixelConfigLoad, DacsLoad)


class ServalCalibrationError(Exception):
    """Raised when a named calibration file is missing or cannot be saved."""


def load_calibration(
    client: ServalClient,
    calibration_files: CalibrationFiles,
    config_directory: Path,
    run_directory: Path,
) -> CalibrationState:
    """Save the calibration files under the run and load them into SERVAL.

    `config_directory` is where the copies are written; `run_directory` is the
    root the saved paths are recorded relative to.
    """
    config_directory.mkdir(parents=True, exist_ok=True)

    pixel_saved, pixel_absolute = _save_file(
        calibration_files.pixel_config_file, config_directory, run_directory
    )
    pixel_config_file = PixelConfigFile(
        path=pixel_saved,
        source_path=calibration_files.pixel_config_file,
        file_hash=_sha256(pixel_absolute),
    )

    dacs_saved, dacs_absolute = _save_file(
        calibration_files.dacs_file, config_directory, run_directory
    )
    dacs_file = DacsFile(
        path=dacs_saved,
        source_path=calibration_files.dacs_file,
        file_hash=_sha256(dacs_absolute),
    )

    pixel_config_load = _load(
        client.load_pixel_config, str(pixel_absolute), PixelConfigLoad, "pixelconfig"
    )
    dacs_load = _load(client.load_dacs, str(dacs_absolute), DacsLoad, "dacs")

    return CalibrationState(
        pixel_config_file=pixel_config_file,
        dacs_file=dacs_file,
        pixel_config_load=pixel_config_load,
        dacs_load=dacs_load,
    )


def _save_file(
    source: Path,
    config_directory: Path,
    run_directory: Path,
) -> tuple[Path, Path]:
    """Copy `source` into `config_directory`; return (relative, absolute) paths."""
    if not source.is_file():
        msg = f"calibration file not found: {source}"
        _LOGGER.error(
            msg,
            event_type="acquisition.serval.calibration_missing",
            source=str(source),
        )
        raise ServalCalibrationError(msg)

    destination = config_directory / source.name
    shutil.copy2(source, destination)
    _LOGGER.info(
        "Saved calibration file {name} into the run config directory",
        event_type="acquisition.serval.calibration_saved",
        name=source.name,
        source=str(source),
        saved_path=str(destination),
    )
    return destination.relative_to(run_directory), destination


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(
    load_call: Callable[[str], httpx.Response],
    server_file_path: str,
    model: type[_LoadModel],
    label: str,
) -> _LoadModel:
    _LOGGER.info(
        "Loading {label} into SERVAL from {file}",
        event_type="acquisition.serval.calibration_load",
        label=label,
        file=server_file_path,
    )
    response = load_call(server_file_path)
    body = response.text.strip()
    return model(
        server_file_path=server_file_path,
        applied_at=datetime.now(tz=timezone.utc),
        status="loaded",
        http_status_code=response.status_code,
        server_response_body=body[:_MAX_RESPONSE_BODY_CHARS] or None,
    )
