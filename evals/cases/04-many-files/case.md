# Example 04 — Many input files (offload to sibling files)

Unpacks eleven raw TPX3 files in one run. With more than ten files, the saved
`HERMES_record.yaml` moves both its long lists out to sibling files so the
record stays small:

- the input list `unpacking.tpx3_files` becomes `{file_list: tpx3_files.txt}`,
- the per-file `unpacking.results` becomes
  `{results_file: unpacking_results.jsonl}`.

The loader expands both back on read, so a saved record round-trips to the same
state.

- **Input data:** eleven copies of `tests/data/tpx3/Example_1kHz_5frames.tpx3`
  (ASI, 1 kHz frame rate, 5 frames), generated at run time by
  `input/prepare.py` under the gitignored `data/04-many-files/raw/` so no
  duplicate detector data is committed.
- **Working directory:** `data/04-many-files/` (all output goes here).

## Expected output

- `expected/output_tree.txt` — the working-directory layout after the run,
  including `HERMES_record.yaml`, `tpx3_files.txt`, and `unpacking_results.jsonl`
  at the run-directory root.
- `expected/HERMES-workflow.jsonl` — the workflow log, one JSON record per file
  (times shown as `<TIMESTAMP>`).
- `expected/unpacker-summary.json` — the per-file unpacker summary for the
  sorted-first file `many_00` (`processing_times_seconds` shown as a
  placeholder).

## Notes

- The ten-file threshold that triggers each offload is
  `MAX_INLINE_FILE_ENTRIES` in `hermes.state_service.state_io`.
- The raw input directory is a sibling of the run directory, so clearing the run
  directory between runs leaves the generated inputs in place.
