"""Locate data files that HERMES ships alongside its code.

HERMES installs bundled data (today, the default calibrations) into the
environment's ``share/hermes/`` folder, a sibling of the ``bin/`` and ``lib/``
folders under a conda/pixi environment prefix. This module finds those files at
run time, preferring the installed copy and falling back to the repository root
so a git checkout works without installing.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def shipped_file(relative_path: str) -> Path:
    """Return the path to a data file HERMES ships.

    Prefers the copy installed into the environment's ``share/hermes/`` folder;
    falls back to the repository root so a git checkout works without installing.
    Raises FileNotFoundError if neither location has the file.
    """
    installed = Path(sys.prefix) / "share" / "hermes" / relative_path
    if installed.is_file():
        return installed
    repo_copy = _REPO_ROOT / relative_path
    if repo_copy.is_file():
        return repo_copy
    raise FileNotFoundError(
        f"shipped file not found in environment or repository: {relative_path}"
    )


def default_timewalk_calibration() -> Path:
    """Path to the time-walk calibration HERMES ships with by default."""
    return shipped_file("calibrations/tpx3/time-walk_example.json")
