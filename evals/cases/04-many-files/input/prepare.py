"""Generate the many-file input for eval case 04.

The committed sample TPX3 file is copied into eleven uniquely-named raw files
under the (gitignored) ``data/`` tree, so the case exercises both offloads:
the input list and the per-file results list each pass the ten-file threshold
that moves them into sibling files. No duplicate detector data is committed.

Run from the repo root, standalone or via the eval harness.
"""

from __future__ import annotations

import shutil
from pathlib import Path

SOURCE_FILE = Path("tests/data/tpx3/Example_1kHz_5frames.tpx3")
RAW_DIRECTORY = Path("data/04-many-files/raw")
FILE_COUNT = 11


def main() -> None:
    RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for index in range(FILE_COUNT):
        shutil.copyfile(SOURCE_FILE, RAW_DIRECTORY / f"many_{index:02d}.tpx3")


if __name__ == "__main__":
    main()
