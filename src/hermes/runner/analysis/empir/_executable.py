"""Resolve configured EMPIR program names and explicit executable paths."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_executable(configured_path: Path) -> Path:
    """Return an absolute executable path for one configured EMPIR program.

    A value containing a directory is treated as an explicit filesystem path.
    A bare program name is searched for on ``PATH``.
    """
    expanded_path = configured_path.expanduser()
    is_explicit_path = expanded_path.is_absolute() or expanded_path.parent != Path(".")

    if is_explicit_path:
        resolved_path = expanded_path.resolve()
    else:
        matched_path = shutil.which(str(expanded_path))
        if matched_path is None:
            raise FileNotFoundError(
                f"EMPIR executable was not found on PATH: {configured_path}"
            )
        resolved_path = Path(matched_path).resolve()

    if not resolved_path.is_file():
        raise FileNotFoundError(
            f"EMPIR executable is not a file: {resolved_path}"
        )
    if not os.access(resolved_path, os.X_OK):
        raise PermissionError(
            f"EMPIR executable is not executable: {resolved_path}"
        )

    return resolved_path
