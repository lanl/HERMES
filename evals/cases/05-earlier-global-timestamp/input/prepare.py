"""Generate the two raw files for eval case 05.

``frame_000.tpx3`` is a copy of the committed sample TPX3 file.
``frame_001.tpx3`` is the same file with every global timestamp packet taken
out, so it has none of its own and must use the last one of ``frame_000``.
Both are written under the (gitignored) ``data/`` tree, so no duplicate
detector data is committed.

Run from the repo root, standalone or via the eval harness.
"""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

SOURCE_FILE = Path("tests/data/tpx3/Example_1kHz_5frames.tpx3")
RAW_DIRECTORY = Path("data/05-earlier-global-timestamp/raw")
# A global timestamp packet has 0x4 in its top four bits.
GLOBAL_TIMESTAMP_TYPE = 0x4


def without_global_timestamps(data: bytes) -> bytes:
    """Return the raw file with its global timestamp packets taken out.

    A raw file is a series of chunks. Each chunk starts with an 8-byte header,
    "TPX3", the chip number, one more byte, and the chunk's size in bytes, and
    is followed by that many bytes of 8-byte packets. The header's size is
    rewritten to match the packets that are kept.
    """
    kept = bytearray()
    position = 0
    while position < len(data):
        header = data[position:position + 8]
        size = struct.unpack_from("<H", header, 6)[0]
        packets = data[position + 8:position + 8 + size]
        position += 8 + size
        kept_packets = b"".join(
            packets[start:start + 8]
            for start in range(0, len(packets), 8)
            if packets[start + 7] >> 4 != GLOBAL_TIMESTAMP_TYPE
        )
        if kept_packets:
            kept += header[:6] + struct.pack("<H", len(kept_packets)) + kept_packets
    return bytes(kept)


def main() -> None:
    RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE_FILE, RAW_DIRECTORY / "frame_000.tpx3")
    (RAW_DIRECTORY / "frame_001.tpx3").write_bytes(
        without_global_timestamps(SOURCE_FILE.read_bytes())
    )


if __name__ == "__main__":
    main()
