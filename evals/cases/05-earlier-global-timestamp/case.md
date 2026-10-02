# Example 05 — A raw file with no global timestamp of its own

Unpacks two raw files from one run. The second file has no global timestamp, so
on its first unpacking every pixel and TDC time has no way to count clock wraps
and is counted as failed. The runner then unpacks it again by itself with the
last global timestamp of the earlier file (`--previous-global-timestamp`), and
every time is placed on the run's time axis.

- **Input data:** generated at run time by `input/prepare.py` under the
  gitignored `data/05-earlier-global-timestamp/raw/`:
  - `frame_000.tpx3` — a copy of `tests/data/tpx3/Example_1kHz_5frames.tpx3`
    (8 global timestamps).
  - `frame_001.tpx3` — the same file with its global timestamp packets taken
    out.
- **Working directory:** `data/05-earlier-global-timestamp/` (all output goes
  here).

## Expected output

- `expected/output_tree.txt` — the working-directory layout after the run. Only
  `frame_000` has a global timestamps Parquet file.
- `expected/HERMES-workflow.jsonl` — the workflow log; both files succeed.
- `expected/frame_001_unpacker_summary.json` — the summary of the file without
  global timestamps after it is unpacked again: `number_of_beats` is 0,
  `previous_file_timestamp_canonical` is the `last_timestamp_canonical` of
  `frame_000`, and `failed` is 0.

## Notes

- The two files hold the same packets, so their pixel and TDC times come out
  the same. In a real run the second file would start later than the first.
- The analysis log has an `analysis.tpx3_unpacking.unpacking_again` event for
  `frame_001`.
