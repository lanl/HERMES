# Example 01 — Unpacking

Unpacks a single raw TPX3 file into per-category parquet tables (pixel hits, TDC
triggers, control packets, global timestamps) plus a summary log. No photon
reconstruction.

- **Input data:** `tests/data/tpx3/Example_1kHz_5frames.tpx3` (ASI, 1 kHz frame
  rate, 5 frames).
- **Working directory:** `data/01-unpacking/` (all output goes here).

The `tpx3_files` list in `input/config.yaml` accepts one or many files. To
unpack several files, add more `- path:` entries, or point the field at a text
file that lists them (`tpx3_files: <path-to-list>.txt`).

## Expected output

- `expected/output_tree.txt` — the working-directory layout after the run.
- `expected/HERMES-workflow.jsonl` — the workflow log, one JSON record per
  stage (times shown as `<TIMESTAMP>`).
- `expected/unpacker-summary.json` — the per-file unpacker summary
  (`processing_times_seconds` shown as a placeholder).

## Notes

- The unpacking backend `hermes-tpx3-spidr` creates the `analysis/`
  sub-directory layout and writes the summary log under `analysis/logs/unpacking/`.
- A final HERMES record is saved at the working-directory root.
- The counts in the summary are real, taken from an actual unpack of this file.
