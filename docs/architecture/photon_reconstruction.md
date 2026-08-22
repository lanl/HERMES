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

The connected-components program processes one pixel file at a time: a single
chip and a single part, clustered on its own. The rows are already sorted by
`timestamp_canonical`, with source order as the stable tie breaker.

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
sum may exceed the number of rejected components. Pixel rows dropped for low
`tot_raw` happen before clustering, so they are not rejected components and are
not part of these rejection counts. Rejected components are not written to
`photon_events`.

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
normalized correction `correction(q) = f(q) - f(high_tot_anchor)` from every
source-pixel timestamp and takes the earliest corrected timestamp. That
correction is fractional, so the corrected leading edge is written as a
floating-point value in canonical ticks to preserve sub-tick precision; it is
not rounded to an integer. When no calibration file is supplied, the correction is zero, the
earliest source-pixel timestamp is written unchanged (an integer value in the
float column), and the program records that it used the uncorrected leading
edge. It must not use guessed correction parameters.

Reconstruction timing is the one place floating-point time is allowed:
unpacking still works only in canonical integer ticks, but the time-walk
correction produces sub-tick offsets, so the reconstructed photon time is a
float64 canonical-tick value. `"brightest"`, `"mean"`, and `"tot_weighted"` are
reserved timing values and must be rejected until implemented.

## Sensor Coordinate Frame

Clustering runs one chip at a time in that chip's own 256x256 pixel space, but
the photon `x` and `y` written to the photon table are in a single shared sensor
frame so the event stage can group light that lands on more than one chip. The
`detector_layout` setting selects the frame:

- `single_chip` leaves the chip's `local_x`/`local_y` unchanged, a 256x256
  frame.
- `quad` tiles four chips 2x2 with a four-pixel dead gap between them, giving a
  516x516 sensor with empty columns and rows at 256-259. Each chip's photon
  position maps into the sensor as:

  | Chip | Sensor x | Sensor y |
  | --- | --- | --- |
  | 0 | `x + 260` | `y` |
  | 1 | `515 - x` | `515 - y` |
  | 2 | `255 - x` | `515 - y` |
  | 3 | `x` | `y` |

The map is an offset and flip only, so applying it to a photon's mean position
gives the same result as mapping every source pixel and then averaging;
clustering stays chip-local and only the photon table moves to the sensor frame.
The `pixel_clusters` table keeps each source pixel's raw chip-local `local_x`
and `local_y`. A `quad` chip index outside 0-3 is an error.

## Photon Parquet Files

Reconstruction writes two tables in two directories under `analysis/`. The
photon table goes in `photons/` and the pixel-to-cluster table goes in
`pixel_clusters/`. Both filenames join the raw TPX3 filename stem, the chip
number, a descriptive label, and the pixel file's five-digit part index with
underscores:

```text
photons/<raw-file-stem>_chip_<chip>_photon_<five-digit-part-index>.parquet
pixel_clusters/<raw-file-stem>_chip_<chip>_pixel_clusters_<five-digit-part-index>.parquet
```

For example, reconstructing
`pixel_hits/Tantalum_IronPowder_chip_0_pixels_00000.parquet` writes
`photons/Tantalum_IronPowder_chip_0_photon_00000.parquet` and, when
`save_photon_pixels` is true,
`pixel_clusters/Tantalum_IronPowder_chip_0_pixel_clusters_00000.parquet`.

The part index matches the pixel file the run read. The photon table is always
written when accepted photons exist. The pixel-to-cluster table is written only
when `save_photon_pixels` is true, in its own `pixel_clusters/` directory. An
empty table has zero files and a zero row count in the summary.

### photon table

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `photon_id` | `uint64` | no | Zero-based photon number within this pixel file (one chip, one part) |
| `x` | `float64` | no | Arithmetic mean source-pixel x coordinate, in the sensor frame |
| `y` | `float64` | no | Arithmetic mean source-pixel y coordinate, in the sensor frame |
| `timestamp_canonical` | `float64` | no | Time-walk-corrected leading-edge photon time in canonical ticks (fractional; equals the earliest source-pixel timestamp when no calibration is applied) |
| `tot` | `uint64` | no | Sum of source-pixel `tot_raw` values |
| `quality_flags` | `uint16` | no | Accepted-photon flag bit mask |

The first position rule is `arithmetic`. ToT-weighted or fitted positions are
reserved for later work.

### pixel-to-cluster table

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `photon_id` | `uint64` | no | Photon number matching the photon table for the same pixel file |
| `pixel_event_id` | `uint64` | no | Zero-based row number of the source pixel within this pixel file's sorted input |
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
- detector layout (`single_chip` or `quad`); the photon `x`/`y` are in this
  layout's sensor frame

## Reconstruction Summary JSON File

Each input pixel file has one reconstruction summary in
`analysis/logs/photon_reconstruction/`, named for the same raw filename stem,
chip number, and five-digit part index as the pixel file it read:

```text
analysis/logs/photon_reconstruction/<raw-file-stem>_chip_<chip>_photon_reconstruction_summary_<five-digit-part-index>.json
```

The chip number and part index keep each input's summary distinct, so a later
part does not overwrite part `00000` and get skipped on a rerun.

The reconstruction program reads the same run-identity inputs as the unpacker
(`--measurement-id` and `--run`) and copies them into the summary so it names
the measurement and run it belongs to. The summary is written after the input's
photon Parquet file closes successfully, and also when the input produces zero
photons and no photon file is written. Each listed Parquet path is the
`--input` path or the output path the program wrote, so a reader can open the
file directly from the working directory. The summary has this structure:

```yaml
measurement_info:
  measurement_id: 02-two-stage
  run: tantalum-ironpowder

reconstruction:
  pixels_read: 0
  clusters_formed: 0
  rejected_clusters: 0
  rejection_reasons:
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
  total_photons: 0

clustering:
  algorithm: connected_components
  settings: {}

photon_timing:
  estimator: leading_edge
  correction_model: none
  calibration_file: null
  parameters: {}
  high_tot_anchor: null

parquet_files:
  input_pixel_data_file: []
  photons:
    row_count: 0
    files: []
  pixel_clusters:
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

`clustering.settings` holds the complete settings the run used: adjacency,
maximum time spread, cluster-size limits, pixel and cluster ToT limits, maximum
aspect ratio, minimum filled fraction, position rule, timing rule, optional
calibration path, `save_photon_pixels`, and `detector_layout`. `pixel_clusters.requested` mirrors
`save_photon_pixels`, and its `row_count` counts the pixels in accepted
clusters. Detailed per-input counts, filenames, warnings, errors, timing, and
throughput stay in this summary and are not copied into the HERMES YAML file.
