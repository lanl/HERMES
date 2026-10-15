"""Small synthetic source hits shared by the three numerical timing cases."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def prepare_pixels(run_directory: Path) -> None:
    """Write three separated clusters in raw timestamp order.

    The first repeats a coordinate. The second bridges two components and
    contains a saturated hit. The last exposes premature float64 rounding.
    Expected output values are authored separately under each case's expected/.
    """
    pixel_file = run_directory / "analysis/pixel_hits/timing_chip_0_pixels_00000.parquet"
    pixel_file.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({
        "local_x": pa.array([0, 1, 1, 1, 10, 12, 11, 11, 20, 21], type=pa.uint16()),
        "local_y": pa.array([0, 0, 1, 1, 0, 0, 0, 0, 20, 20], type=pa.uint16()),
        "tot_raw": pa.array([10, 30, 20, 30, 30, 10, 1023, 20, 10, 30], type=pa.uint16()),
        "timestamp_canonical": pa.array(
            [100, 106, 110, 110, 200, 202, 204, 206, 2**53 + 1, 2**53 + 2],
            type=pa.uint64(),
        ),
    }), pixel_file)
