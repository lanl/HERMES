# Example 03 — Event reconstruction on a quad detector

Runs the full pipeline on a quad-detector raw file: unpacks the four chips,
reconstructs photons on each chip, then clusters those photons across the whole
sensor into events.

- **Input data:** `tests/data/tpx3/quad.tpx3` (a small four-chip sample).
- **Working directory:** `data/03-event-quad/` (all output goes here).

Photon reconstruction writes each photon's `x`/`y` in the shared 516x516 sensor
frame (the quad layout maps chips 0-3 into one grid with a four-pixel dead cross
at columns/rows 256-259). Event reconstruction then pools every chip's photon
file for the raw file and clusters them together, so a scintillation event whose
light lands on more than one chip becomes a single event instead of one per
chip.

## Expected output

- `expected/output_tree.txt` — the working-directory layout after the run.
- `expected/HERMES-workflow.jsonl` — the workflow log, one JSON record per stage
  (times shown as `<TIMESTAMP>`).
- `expected/unpacker-summary.json` — the per-file unpacker summary.
- `expected/reconstruction-summary.json` — the chip-0 photon-reconstruction
  summary (the comparison picks the first chip's file).
- `expected/event_reconstruction-summary.json` — the whole-sensor event summary
  (`processing_times_seconds` shown as a placeholder in all three).

## Notes

- `detector_layout.kind` is `quad`, so photon `x`/`y` stay in the 516x516 sensor
  frame. Event reconstruction reads that layout back from each photon file's
  metadata and sizes its grid to the full sensor: with `spatial_cells_per_axis`
  of 5, the derived cell width is 104 (516 rounded up over 5).
- Event reconstruction is whole-sensor per raw file: it gathers
  `photons/quad_chip_*_photon_*.parquet`, pools and time-sorts them, and writes
  one `events/quad_event_candidates.parquet` covering all four chips.
- `save_event_photons` is `true`, so the run also writes
  `event_photons/quad_event_photons.parquet`, tagging each photon with the ID of
  the event it belongs to. Here the four chips contribute 2,749 photons, which
  cluster into 2,707 events.
- The unpacker `warnings` list is shown as a placeholder: this sample carries
  many "unknown SPIDR control" warnings whose exact contents are not the point of
  the case.
