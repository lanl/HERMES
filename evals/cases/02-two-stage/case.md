# Example 02 — Two-stage (unpacking + photon reconstruction)

Unpacks a single raw TPX3 file, then reconstructs photons from the pixel hits by
clustering neighboring hits that are close in space and time.

- **Input data:** `tests/data/tpx3/Tantalum_IronPowder.tpx3` (FP5, tantalum foil
  and iron powder in the beam, T-zeros on TDC1 at 20 Hz).
- **Working directory:** `data/02-two-stage/` (all output goes here).

Reconstruction runs with the `connected_components` algorithm (8-way
adjacency), arithmetic position averaging, and a leading-edge time estimator.
The `tests/data/tpx3/Tantalum_IronPowder.tpx3` file holds 505,721 pixel hits,
which cluster into 99,909 photons at the settings in `input/config.yaml`.

## Expected output

- `expected/output_tree.txt` — the working-directory layout after the run.
- `expected/HERMES-workflow.jsonl` — the workflow log, one JSON record per
  stage (times shown as `<TIMESTAMP>`).
- `expected/unpacker-summary.json` — the per-file unpacker summary.
- `expected/reconstruction-summary.json` — the per-file photon-reconstruction
  summary (`processing_times_seconds` shown as a placeholder in both).

## Notes

- `pixel_files: auto` tells the reconstruction stage to watch the unpacked pixel
  output directory and reconstruct each pixel file as it appears, so the two
  stages run back to back from one raw file.
- `detector_layout.kind` is `single_chip` (this run has only chip 0), so photon
  `x`/`y` stay in the chip's 256x256 frame. A `quad` detector would map each
  chip into the shared 516x516 sensor frame instead.
- `save_photon_pixels` is `true`, so the run also writes a pixel-to-cluster
  table (`pixel_clusters/..._pixel_clusters_00000.parquet`) in its own
  `pixel_clusters/` directory, tagging each pixel with the ID of the cluster it
  belongs to for reconstruction diagnostics. Here that table holds 488,304
  pixels (those in accepted clusters). Set it to `false` to skip it and write
  only the photon table.
- The counts in both summaries are real, taken from an actual two-stage run of
  this file: 505,721 pixels form 108,990 clusters, 9,081 are rejected, leaving
  99,909 photons.
