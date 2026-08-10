# Photon Reconstruction

Photon reconstruction is a separate analysis step, not a required part of the
unpacker. A user-selected HERMES program reads sorted `pixel_data` Parquet files
from `analysis/pixel_hits/` and writes photon Parquet files under
`analysis/photons/`. C++ and Rust versions live beside each other:

```text
src/backends/reconstruction/photons/
├── cpp/
└── rust/
```

`clustering_algorithm="connected_components"` selects the first program.
`"dbscan"` is reserved for a later program and must be rejected until that
program exists. Both programs must accept the same required inputs and settings
and write the same columns, filenames, metadata, summary fields, warnings,
errors, and exit codes.

## Connected Components with a Time Gate

The connected-components program processes one raw filename stem at a time and
each chip independently. It reads the chip's numbered `pixel_data` parts in
order. The rows are already sorted by `timestamp_canonical`, with source order
as the stable tie breaker.

The program keeps only open components whose earliest timestamp remains within
the configured maximum time spread of the current row:

- 4-connected means the same pixel or a horizontal or vertical neighbor.
- 8-connected means the same pixel or any horizontal, vertical, or diagonal
  neighbor.
- 8-connected is the recommended default for roughly circular phosphor
  responses because diagonally touching pixels can come from the same photon.
- A row joins every adjacent open component when the combined component's
  maximum timestamp minus minimum timestamp is less than or equal to
  `max_time_spread_ticks`.
- When a row joins more than one open component, those components merge.
- A component closes when the next row would make its time spread greater than
  `max_time_spread_ticks`.

The maximum time spread is inclusive. Including repeated firing of the same
pixel allows one phosphor response to contain more than one hit at one pixel.
Connectivity grows transitively: a pixel may join a component through a chain
of immediate neighbors even when it is more than one coordinate step from the
component's first pixel. The program does not jump over a missing intermediate
pixel. Two groups separated by a spatial gap remain separate even when their
timestamps are within the time gate. Clustering happens before TDC association.

## Pixel and Cluster Filtering

The first program uses three saved rejection measures:

1. Drop a pixel row before clustering when `tot_raw` is less than
   `min_pixel_tot_raw`.
2. After a component closes, require its pixel count and summed `tot_raw` to be
   within their saved inclusive minimum and maximum values.
3. Require the closed component to pass both bounding-box aspect ratio and
   bounding-box filled fraction limits.

For a component with inclusive width `max_x - min_x + 1` and height
`max_y - min_y + 1`:

```text
aspect_ratio = max(width, height) / min(width, height)
filled_fraction = unique_pixel_coordinates / (width * height)
```

The aspect ratio rejects long tracks. The filled fraction rejects sparse
components whose bounding box contains mostly empty pixels. The cluster-size
limit already rejects oversized components, so the first implementation does
not add a radius-of-gyration setting.

A closed component is rejected when it fails any cluster limit. Rejection
counts name every failed limit and are therefore not mutually exclusive; their
sum may exceed the number of rejected components. The separately reported
low-ToT count is a count of dropped pixel rows, not rejected components.
Rejected components are not written to `photon_events`.

Each accepted photon has a `quality_flags` bit mask:

| Bit | Name | Meaning |
| --- | --- | --- |
| `0x0001` | `saturated_pixel` | At least one source pixel has the native 10-bit maximum `tot_raw` value of 1023. |
| `0x0002` | `bridged_components` | One source pixel joined two or more previously separate open components. |

All other bits are reserved. The reconstruction summary counts accepted photons
with each flag. Later split or ambiguous-photon flags require measured behavior
and must not be guessed in the first implementation.

## Photon Timing Investigation

The timing calibration uses compact components from ordinary photon
`pixel_data`; it does not require a dedicated calibration measurement or an
external trigger. For each component, the earliest pixel in stable input order
is the timing reference. For every other pixel, calibration records:

```text
relative_delay_ticks = pixel_timestamp_canonical
                     - reference_timestamp_canonical
pixel_tot_raw
reference_tot_raw
```

The calibration bins and plots `relative_delay_ticks` against `pixel_tot_raw`.
It then compares at least these candidate per-pixel correction functions:

```text
linear:  f(q) = m*q + d
inverse: f(q) = a/(q + b) + c
```

The fitted observation is the within-component difference
`f(pixel_tot_raw) - f(reference_tot_raw)`, not `f(pixel_tot_raw)` alone. The
additive offset cancels in this relative measurement. The comparison reports
binned residuals, held-out-component error, and fitted parameters from
time-ordered subsets of the input. The selected model should have lower
held-out error, no remaining ToT-dependent residual trend, and stable
parameters across the subsets. If the evidence does not distinguish the
models, select the linear model. The selected model remains subject to review
at the calibration stage approval gate.

The saved correction is normalized to zero at the 95th percentile of
`reference_tot_raw` in the calibration components:

```text
correction(q) = f(q) - f(high_tot_anchor)
```

This normalization aligns pixel times within a component but does not determine
an absolute photon-arrival offset. The fitted relation includes both
front-end threshold-crossing time-walk and the amplitude-dependent phosphor
response. It does not resolve per-pixel clock-distribution delays.

The calibration JSON file contains:

- schema version and canonical time unit
- relative input `pixel_data` filenames and clustering settings
- cluster and pixel-pair counts and the ToT-bin definitions and counts
- both candidate model names, parameters, residuals, held-out errors, and
  time-ordered-subset parameters
- selected model and selection reason
- high-ToT normalization anchor

The calibration also writes a comparison plot beside the JSON file using
`<calibration-file-stem>-comparison.png`. It shows the binned
relative-delay-versus-ToT distribution, both fitted curves, and their residuals
so the model choice can be reviewed before reconstruction is implemented.

`photon_time_estimator="leading_edge"` is the first implemented timing rule.
When a calibration file is supplied, the program subtracts the selected
normalized correction from every source-pixel timestamp and takes the earliest
corrected timestamp. The correction `delta_t(tot_raw) = a/(tot_raw+b)+c` is
fractional, so the corrected leading edge is written as a floating-point value
in canonical ticks to preserve sub-tick precision; it is not rounded to an
integer. When no calibration file is supplied, the correction is zero, the
earliest source-pixel timestamp is written unchanged (an integer value in the
float column), and the program records that it used the uncorrected leading
edge. It must not use guessed correction parameters.

Reconstruction timing is the one place floating-point time is allowed:
unpacking still works only in canonical integer ticks, but the time-walk
correction produces sub-tick offsets, so the reconstructed photon time is a
float64 canonical-tick value. `"brightest"`, `"mean"`, and `"tot_weighted"` are
reserved timing values and must be rejected until implemented.

## Photon Parquet Files

The `analysis/photons/` directory contains two distinct filename groups:

```text
<raw-file-stem>-chip-<chip-index>-photon-events-part-<five-digit-part-index>.parquet
<raw-file-stem>-chip-<chip-index>-photon-pixels-part-<five-digit-part-index>.parquet
```

Part numbers start at zero independently for each raw input, chip, and file
group. `photon_events` is always written when accepted photons exist.
`photon_pixels` is written only when `save_photon_pixels` is true. An empty file
group has zero files and a zero row count in the summary.

### `photon_events`

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `photon_id` | `uint64` | no | Zero-based photon number within the raw input and chip |
| `x` | `float64` | no | Arithmetic mean source-pixel x coordinate |
| `y` | `float64` | no | Arithmetic mean source-pixel y coordinate |
| `timestamp_canonical` | `float64` | no | Time-walk-corrected leading-edge photon time in canonical ticks (fractional; equals the earliest source-pixel timestamp when no calibration is applied) |
| `tot` | `uint64` | no | Sum of source-pixel `tot_raw` values |
| `quality_flags` | `uint16` | no | Accepted-photon flag bit mask |

The first position rule is `arithmetic`. ToT-weighted or fitted positions are
reserved for later work.

### `photon_pixels`

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `photon_id` | `uint64` | no | Photon number matching `photon_events` for the same raw input and chip |
| `pixel_event_id` | `uint64` | no | Zero-based row number after reading the chip's sorted input parts in order |
| `x` | `uint16` | no | Source pixel `local_x` |
| `y` | `uint16` | no | Source pixel `local_y` |
| `tot_raw` | `uint16` | no | Source pixel ToT |
| `timestamp_canonical` | `uint64` | no | Source pixel timestamp before timing correction |

Every photon Parquet file records these string metadata values:

- schema name and schema version
- canonical tick duration in seconds
- raw filename stem and chip index
- clustering algorithm and complete clustering settings as JSON
- position averaging rule
- photon time estimator
- correction model, fitted parameters, and high-ToT anchor, or
  `correction_model="none"`
- whether `photon_pixels` was requested

## Reconstruction Summary JSON File

Each raw TPX3 filename stem has one reconstruction summary:

```text
analysis/logs/<raw-file-stem>-reconstruction-summary.json
```

It is written only after every final photon Parquet file closes successfully.
Paths are relative to the analysis directory. The summary has this structure:

```yaml
schema_version: 1

reconstruction:
  pixel_rows_read: 0
  pixel_rows_below_min_tot: 0
  components_formed: 0
  photon_count: 0
  rejected_component_count: 0
  rejection_counts:
    below_min_cluster_size: 0
    above_max_cluster_size: 0
    below_min_cluster_tot: 0
    above_max_cluster_tot: 0
    above_max_aspect_ratio: 0
    below_min_filled_fraction: 0
  quality_flag_counts:
    saturated_pixel: 0
    bridged_components: 0
  warnings: []
  errors: []

clustering:
  algorithm: connected_components
  settings: {}

photon_timing:
  estimator: leading_edge
  correction_model: none
  calibration_file: null
  parameters: {}
  high_tot_anchor: null

parquet:
  input_pixel_data_files: []
  photon_events:
    row_count: 0
    files: []
  photon_pixels:
    requested: false
    row_count: 0
    files: []

processing_times_seconds:
  parquet_reading: 0.0
  clustering_and_filtering: 0.0
  parquet_writing: 0.0
  total: 0.0
  throughput:
    pixels_per_second: 0.0
    photons_per_second: 0.0
```

The complete saved settings include adjacency, maximum time spread, cluster-size
limits, pixel and cluster ToT limits, maximum aspect ratio, minimum filled
fraction, position rule, timing rule, optional calibration path, and
`save_photon_pixels`. Detailed per-input counts, filenames, warnings, errors,
timing, and throughput stay in this summary and are not copied into the HERMES
YAML file.
