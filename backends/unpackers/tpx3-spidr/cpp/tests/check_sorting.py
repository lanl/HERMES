#!/usr/bin/env python3
"""
Verify that TPX3 unpacker output is properly time-sorted.

Usage:
    python check_sorting.py <output_directory>

Example:
    python check_sorting.py .scratch/test_output
"""

import sys
import os
from pathlib import Path
import pyarrow.parquet as pq


def check_sorting(file_path, name):
    """Check if a Parquet file is sorted by timestamp_canonical."""
    if not os.path.exists(file_path):
        print(f"\n{name}: SKIPPED (file not found)")
        return True  # Not an error if file doesn't exist

    table = pq.read_table(file_path)

    if "timestamp_canonical" not in table.column_names:
        print(f"\n{name}: SKIPPED (no timestamp column)")
        return True

    timestamps = table.column("timestamp_canonical").to_pylist()

    if len(timestamps) == 0:
        print(f"\n{name}: EMPTY")
        return True

    # Filter out None values (for nullable timestamp columns)
    non_null_timestamps = [(i, t) for i, t in enumerate(timestamps) if t is not None]

    if len(non_null_timestamps) == 0:
        print(f"\n{name}: NO TIMESTAMPS (all null)")
        return True

    # Check if sorted (only checking non-null values)
    unsorted_positions = []
    for i in range(len(non_null_timestamps) - 1):
        idx, ts = non_null_timestamps[i]
        next_idx, next_ts = non_null_timestamps[i+1]
        if ts > next_ts:
            unsorted_positions.append(idx)

    is_sorted = len(unsorted_positions) == 0

    # Get just the timestamp values for min/max
    ts_values = [t for _, t in non_null_timestamps]

    print(f"\n{name}:")
    print(f"  Total rows: {len(timestamps):,}")
    print(f"  Timestamped rows: {len(non_null_timestamps):,}")
    if len(non_null_timestamps) < len(timestamps):
        print(f"  Null timestamps: {len(timestamps) - len(non_null_timestamps):,}")
    print(f"  Sorted: {'✓ YES' if is_sorted else '✗ NO'}")
    print(f"  Min timestamp: {min(ts_values):,}")
    print(f"  Max timestamp: {max(ts_values):,}")
    print(f"  Time range: {max(ts_values) - min(ts_values):,} canonical ticks")

    if not is_sorted:
        print(f"  ERROR: Found {len(unsorted_positions)} unsorted positions")
        first_bad = unsorted_positions[0]
        print(f"  First unsorted at row index {first_bad}: "
              f"{timestamps[first_bad]:,} > {timestamps[first_bad+1]:,}")

    return is_sorted


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    output_dir = Path(sys.argv[1])

    if not output_dir.exists():
        print(f"Error: Directory not found: {output_dir}")
        sys.exit(1)

    print(f"Checking sorting in: {output_dir}")
    print("=" * 70)

    # Check all dataset types
    datasets = [
        ("pixel_hits", "Pixel Hits"),
        ("tdc_triggers", "TDC Triggers"),
        ("global_timestamps", "Global Timestamps"),
        ("control_packets", "Control Packets"),
        ("unknown_packets", "Unknown Packets"),
    ]

    all_sorted = True
    for dataset_dir, display_name in datasets:
        dataset_path = output_dir / dataset_dir
        if dataset_path.exists():
            # Check all parquet files in the dataset directory
            parquet_files = sorted(dataset_path.glob("*.parquet"))
            for pq_file in parquet_files:
                file_display = f"{display_name} ({pq_file.name})"
                all_sorted &= check_sorting(pq_file, file_display)

    print("\n" + "=" * 70)
    if all_sorted:
        print("✓ All datasets are properly time-sorted")
        sys.exit(0)
    else:
        print("✗ Some datasets are NOT properly sorted")
        sys.exit(1)


if __name__ == "__main__":
    main()
