"""Tell SERVAL where to write raw `.tpx3` data for this run.

SERVAL runs on the same machine as HERMES, so the write location is a local
directory named with a `file:` URI. This builds a single raw destination, sends
it to SERVAL, reads it back, and confirms it points at the directory we asked
for. No measurement is started here.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

from loguru import logger

from hermes.runner.acquisition.serval.client import ServalClient
from hermes.state.models.acquisition.serval import (
    DestinationConfiguration,
    ServalRawDestination,
)

_LOGGER = logger.bind(
    domain="acquisition",
    backend="serval",
    step="serval_destination",
)

# Time-based file names, one file per frame. Carried over from the working
# prototype's SERVAL setup; unchanged until a reason to change appears.
_RAW_FILE_PATTERN = "%yyyy-MM-dd'T'HHmmss_"
_RAW_SPLIT_STRATEGY = "FRAME"


def configure_raw_destination(
    client: ServalClient,
    raw_data_directory: Path,
) -> DestinationConfiguration:
    """Point SERVAL at `raw_data_directory` and return the applied destination.

    Creates the directory, PUTs a single raw destination that writes time-named,
    per-frame `.tpx3` files there, then reads `/server/destination` back and
    warns if the read-back does not point at the same directory.
    """
    raw_data_directory.mkdir(parents=True, exist_ok=True)
    requested = DestinationConfiguration(
        raw=[
            ServalRawDestination(
                base=raw_data_directory.as_uri(),
                file_pattern=_RAW_FILE_PATTERN,
                split_strategy=_RAW_SPLIT_STRATEGY,
            )
        ]
    )
    _LOGGER.info(
        "Setting SERVAL raw destination to {directory}",
        event_type="acquisition.serval.destination_set",
        directory=str(raw_data_directory),
        base=requested.raw[0].base,
    )
    client.put_destination(requested)

    applied = client.get_destination()
    if _any_raw_points_to(applied, raw_data_directory):
        _LOGGER.info(
            "SERVAL destination confirmed at {directory}",
            event_type="acquisition.serval.destination_confirmed",
            directory=str(raw_data_directory),
        )
    else:
        _LOGGER.warning(
            "SERVAL destination read-back does not point at {directory}",
            event_type="acquisition.serval.destination_mismatch",
            directory=str(raw_data_directory),
            applied_bases=[entry.base for entry in applied.raw],
        )
    return applied


def _any_raw_points_to(
    destination: DestinationConfiguration,
    directory: Path,
) -> bool:
    target = directory.resolve()
    return any(_base_points_to(entry.base, target) for entry in destination.raw)


def _base_points_to(base: str, target: Path) -> bool:
    """True when a `file:` destination base resolves to `target`.

    Compares the local directory the base names, not the raw string, so
    SERVAL echoing a differently spelled but equivalent `file:` URI still
    counts as a match.
    """
    path_part = base
    for prefix in ("file://", "file:"):
        if path_part.startswith(prefix):
            path_part = path_part[len(prefix) :]
            break
    try:
        return Path(unquote(path_part)).resolve() == target
    except OSError:
        return False
