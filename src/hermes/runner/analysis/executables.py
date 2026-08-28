"""Resolve a configured HERMES or EMPIR backend name or explicit executable path.

Each backend names its program in the config. A value that contains a directory,
or that names an existing file in the current directory, is used as an explicit
filesystem path; any other bare program name is looked up on PATH. This lets a
config say ``executable_path: hermes-tpx3-spidr`` and find the program that the
package install placed on PATH, while still accepting an explicit build path.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_executable(configured_path: Path) -> Path:
    """Return an absolute executable path for one configured program.

    A value containing a directory, or naming an existing file in the current
    directory, is treated as an explicit filesystem path. Any other bare
    program name is searched for on ``PATH``.
    """
    expanded_path = configured_path.expanduser()
    is_explicit_path = (
        expanded_path.is_absolute()
        or expanded_path.parent != Path(".")
        or expanded_path.is_file()
    )

    if is_explicit_path:
        resolved_path = expanded_path.resolve()
    else:
        matched_path = shutil.which(str(expanded_path))
        if matched_path is None:
            raise FileNotFoundError(
                f"executable was not found on PATH: {configured_path}"
            )
        resolved_path = Path(matched_path).resolve()

    if not resolved_path.is_file():
        raise FileNotFoundError(
            f"executable is not a file: {resolved_path}"
        )
    if not os.access(resolved_path, os.X_OK):
        raise PermissionError(
            f"executable is not executable: {resolved_path}"
        )

    return resolved_path


def single_thread_environment() -> dict[str, str]:
    """Copy the current environment with common thread-count variables set to 1.

    Each analysis subprocess is Arrow/Parquet-linked; left unset, its internal
    thread pools size themselves to every core, so many concurrent workers
    oversubscribe the machine. Pinning them to one thread keeps one worker to
    roughly one core, which is what the worker-count formula assumes.
    """
    environment = dict(os.environ)
    for name in ("OMP_NUM_THREADS", "ARROW_NUM_THREADS", "ARROW_IO_THREADS"):
        environment[name] = "1"
    return environment
