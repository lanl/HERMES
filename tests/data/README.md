## Overview

This is a small data directory containing various data sets for the examples and unit tests. 

Users should not modify or write to these directories or files. 
They are meant to be starting points for various examples and test cases. 

## Contents

- `tpx3/` — contains TPX3-related test data files.
- `pixelHits/` — contains pixel hits-related test data files.
- `photons/` — contains photon reconstruction-related test data files.

## TPX3 data

### `Example_1kHz_5frames.tpx3` 

Example TPX3 data file from ASI taken with 1 kHz frame rate and 5 frames.

### `Tantalum_IronPowder.tpx3`

Example TPX3 data file taken on FP5 with a tantalum foil and iron powder
in the beam. Has T-zeros recorded via TDC1 channel at 20 Hz. 

## Pixel Hits data

Pixel hits are the raw per-pixel detections decoded from a TPX3 file, before
any clustering into photons.

### `Tantalum_IronPowder.parquet`

Pixel hits decoded from `tpx3/Tantalum_IronPowder.tpx3` (505,721 rows). Columns:

- `chunk_index` — index of the source data chunk the hit was decoded from.
- `packet_index` — index of the hit's packet within that chunk.
- `local_x`, `local_y` — pixel column and row on the chip (0–255).
- `tot_raw` — raw time-over-threshold, an uncalibrated measure of deposited charge.
- `timestamp_canonical` — hit arrival time in canonical ticks
  (1 tick = 2.0345052083333334e-12 s).

## Photons data

Photons are reconstructed by clustering neighboring pixel hits that are close in
space and time, then estimating a single position, time, and time-over-threshold
for each cluster.

### `Tantalum_IronPowder.parquet`

Photons reconstructed from `pixelHits/Tantalum_IronPowder.parquet` (99,909 rows),
which in turn comes from `tpx3/Tantalum_IronPowder.tpx3`. Columns:

- `photon_id` — unique identifier for the photon.
- `x`, `y` — reconstructed sub-pixel position on the chip.
- `timestamp_canonical` — reconstructed arrival time in canonical ticks
  (1 tick = 2.0345052083333334e-12 s).
- `tot` — summed time-over-threshold of the cluster's pixel hits.
- `quality_flags` — bit flags describing reconstruction quality.

Reconstruction settings are stored in the file's schema metadata. This file was
produced with the `connected_components` clustering algorithm (8-way adjacency),
arithmetic position averaging, and a leading-edge time estimator.