# TPX3 SPIDR Unpacking

TPX3 SPIDR unpackers should live outside the Python package. C++ and Rust
versions should live beside each other:

```text
backends/unpackers/tpx3-spidr/
├── cpp/
└── rust/
```

Each version should read the binary packets in a raw `.tpx3` file, identify the
packet type, and extract its fields. C++ and Rust versions must accept the same
required inputs and write the same required outputs.

The current implementation work covers the C++ unpacker only. Completion does
not require a Rust unpacker, Python execution wrapper, HERMES state updates, or
performance optimization.

Python should run the unpacker selected by the user as a separate command-line
program. Code in `src/hermes/analysis/` should run the selected executable,
check the summary JSON file, and save the results through
`hermes.state_service`. It must not change the HERMES state directly.

The Python runner should call the unpacker with the raw TPX3 file and the
shared analysis directory:

```text
<executable> --input <input.tpx3> [--output <analysis_directory>] [--overwrite] [--time-sort]
```

The unpacker accepts exactly these options and no others:

- `--input <input.tpx3>` — the raw TPX3 file to unpack. Required; the unpacker
  raises an error if it is missing. Implemented.
- `--output <analysis_directory>` — the shared analysis directory. The unpacker
  creates all category directories and output filenames from it. Optional; when
  omitted, the unpacker prints summary statistics only and writes no files. The
  HERMES analysis workflow always supplies it. Implemented.
- `--overwrite` — redo the unpacking or reconstruction and replace existing
  output files instead of stopping. Optional, defaults to false. Without it the
  unpacker preserves existing files (see below). Implemented.
- `--time-sort` — sort output by canonical timestamp. Optional, defaults to
  false. Not implemented yet.

Do not add any option outside this list. In particular, do not add separate
command options for category directories, a filename prefix, or a summary
filename; the unpacker creates those from `--output`.

The Python runner should keep this simple and clean: confirm the input file is
set, then call the binary with the flags. Do not add helper functions or a
builder abstraction for assembling the command.

The HERMES state should save the raw TPX3 input files, shared analysis
directory, unpacker program, and overall unpacking status and times. Each
input-specific summary JSON file should save its byte and packet counts,
Parquet filenames and row counts, timestamp-processing information, sorting
information, processing times, throughput, warnings, and errors.

## Shared Analysis Directories

The unpacker should write separate Apache Parquet files for each TPX3 packet type
instead of combining every row in one large file.

All raw TPX3 files in one measurement use the same category directories. The
unpacker must not create a new directory tree for each raw file. A measurement
uses this layout:

```text
data/
├── rawTpx3/
│   ├── DT_2p0V_000000.tpx3
│   └── DT_2p0V_000001.tpx3
└── analysis/
    ├── pixelHits/
    ├── tdcTriggers/
    ├── globalTimestamps/
    ├── controlPackets/
    ├── unknownPackets/
    ├── logs/
    ├── photons/
    └── events/
```

The unpacker creates the five unpacked-data directories and `logs/` before it
starts writing files. These directories remain present when a category has no
rows. An empty category has no Parquet file, and its summary entry reports zero
rows and zero files. The `photons/` and `events/` directories belong to later
reconstruction steps and are not created by the unpacker.

The directory names and the corresponding Parquet data category names are:

| Saved data | Directory | Parquet data category |
| --- | --- | --- |
| Pixel data | `pixelHits/` | `pixel_data` |
| TDC timestamps | `tdcTriggers/` | `tdc_timestamps` |
| Heartbeat packets | `globalTimestamps/` | `heartbeat_packets` |
| Control packets | `controlPackets/` | `control_packets` |
| Unrecognized packets | `unknownPackets/` | `unrecognized_packets` |

## Parquet Filenames

Pixel data can come from more than one chip, so its filenames carry the raw TPX3
filename stem, chip index, and part index:

```text
<raw-file-stem>-chip-<chip-index>-part-<five-digit-part-index>.parquet
```

For example, the first pixel-data part for chip 0 from
`DT_2p0V_000000.tpx3` is:

```text
analysis/pixelHits/DT_2p0V_000000-chip-0-part-00000.parquet
```

The other categories (`tdcTriggers`, `globalTimestamps`, `controlPackets`, and
`unknownPackets`) are not associated with a chip, so their filenames omit the
chip index and carry only the raw TPX3 filename stem and part index:

```text
<raw-file-stem>-part-<five-digit-part-index>.parquet
```

For example, the first TDC-timestamps part from `DT_2p0V_000000.tpx3` is:

```text
analysis/tdcTriggers/DT_2p0V_000000-part-00000.parquet
```

Part numbers start at zero independently for each raw file, data category, and
(for pixel data) chip. The category name does not need to be repeated in the
filename because it is already stated by the parent directory. When a chip index
is present it should not be repeated in the rows. When a schema includes
`packet_index`, it is the packet index within its chunk.

Raw TPX3 filename stems must be unique within one measurement. The HERMES
runner must reject duplicate stems before launching any unpacker so one input
cannot overwrite another input's files. Without `--overwrite`, existing files
with the same expected names must cause the run to stop; the unpacker must not
silently overwrite them. With `--overwrite`, the unpacker redoes the run and
replaces those files.

Integrated-ToT packets should be unpacked and counted, but the first output
format does not write them. A later acquisition-mode-specific version may add
an `integratedPixels/` directory.

The C++ unpacker should use the native integer timing fields to calculate final
timestamps, but it should not copy those raw timing fields into Parquet. Each
known timestamped dataset should contain only `timestamp_canonical` for time.
The Parquet metadata and summary JSON file should define the canonical unit.

Pixel ToT should remain in the pixel table because it is a detector measurement,
not an arrival-timestamp component. The TDC table should contain only
`trigger_type` and `timestamp_canonical`. `trigger_type` uses `0` for TDC1
rising, `1` for TDC1 falling, `2` for TDC2 rising, and `3` for TDC2 falling.
Invalid-time TDC packets should be counted as unpacking errors and omitted from
Parquet.

## Parquet Schemas

Known-packet tables should contain the final analysis values rather than copies
of raw packet words or raw timestamp components. Unrecognized packets retain
their raw word because no reliable unpacked representation exists for them.

### `pixel_data`

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `chunk_index` | `uint64` | no | Chunk index in the input file |
| `packet_index` | `uint64` | no | Packet index within the chunk |
| `local_x` | `uint16` | no | Chip-local x coordinate |
| `local_y` | `uint16` | no | Chip-local y coordinate |
| `tot_raw` | `uint16` | no | Pixel ToT measurement |
| `timestamp_canonical` | `uint64` | no | Unwrapped final timestamp |

The raw `pixel_address`, ToA, FToA, and SPIDR time are used by the C++ unpacker
but are not copied into Parquet. `local_x` and `local_y` contain the complete
unpacked pixel location.

### `tdc_timestamps`

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `trigger_type` | `uint8` | no | `0` TDC1 rising, `1` TDC1 falling, `2` TDC2 rising, `3` TDC2 falling |
| `timestamp_canonical` | `uint64` | no | Unwrapped final timestamp |

The normalized trigger type replaces separate channel and edge columns. Raw
edge code, trigger counter, reserved bits, fine-time validity, and packet
provenance remain unpacker diagnostics and are not written. A TDC packet with an
invalid fine-time value does not produce a Parquet row.

### `heartbeat_packets`

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `chunk_index` | `uint64` | no | Chunk containing the high packet that completed the timestamp |
| `packet_index` | `uint64` | no | High packet index within that chunk |
| `timestamp_canonical` | `uint64` | no | Paired and unwrapped final timestamp |

Only complete heartbeat low/high pairs are written. The low packet position and
raw low, high, paired, and SPIDR timing values are not copied into Parquet.

### `control_packets`

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `chunk_index` | `uint64` | no | Chunk index in the input file |
| `packet_index` | `uint64` | no | Packet index within the chunk |
| `source` | `uint8` | no | `0` SPIDR, `1` TPX3 |
| `control_type` | `uint16` | no | Normalized control type |
| `packet_id` | `uint8` | yes | SPIDR packet ID when present |
| `subtype` | `uint8` | yes | SPIDR subtype when present |
| `packet_count` | `uint64` | yes | Packet count when present |
| `reserved_high` | `uint16` | yes | SPIDR upper reserved field when present |
| `reserved_low` | `uint16` | yes | SPIDR lower reserved field when present |
| `control_value_raw` | `uint16` | yes | TPX3 control value when present |
| `control_payload_raw` | `uint64` | yes | TPX3 control value data when present |
| `timestamp_canonical` | `uint64` | yes | Unwrapped final timestamp when present |

### `unrecognized_packets`

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `chunk_index` | `uint64` | no | Chunk index in the input file |
| `packet_index` | `uint64` | no | Packet index within the chunk |
| `raw_word` | `uint64` | no | Original unrecognized packet word |
| `most_significant_byte` | `uint8` | no | Raw most-significant byte |

Every schema should record its version and the canonical time unit in Parquet
metadata. The first writer should use one fixed row limit per part rather than
adding another command-line option.

## Native Timestamp Fields

The unpacker uses the following native fields and units during timestamp
calculation. They are documented in the summary metadata but are not saved as
Parquet columns:

| Quantity | Raw field | Native unit | Notes |
| --- | --- | --- | --- |
| Pixel `spidr_time` | 16-bit | `25 ns * 2^14 = 409.6 us` | Extends pixel ToA beyond 14 bits. |
| Pixel `ToA` | 14-bit | `25 ns` ticks | Coarse pixel arrival time. |
| Pixel `FToA` | 4-bit | `-1.5625 ns` correction | Fine ToA correction. SERVAL treats this as negative fine time. |
| Pixel coarse timestamp | `(spidr_time << 14) | ToA` | `25 ns` ticks | 30-bit coarse pixel time, maximum about `26.84 s`. |
| Pixel fine timestamp | derived from `spidr_time`, `ToA`, and `FToA` | `1.5625 ns` derived ticks | A common ASI formula is `(((spidr_time << 14) + ToA) << 4) - FToA`. |
| TDC coarse time | packet timestamp field | `25 ns` ticks | Used with finer TDC fields to derive edge time. |
| TDC sub-coarse time | packet timestamp field | `3.125 ns` ticks | Part of the TDC timestamp. |
| TDC fine time | 4-bit, values `1..12` | `260.416666 ps` steps | Value `0` is an error state per ASI documentation. |
| Heartbeat timestamp low | 32-bit | `25 ns` ticks | Low part of the 48-bit global timer. |
| Heartbeat timestamp high | 16-bit | high bits of same `25 ns` timer | Combined global timer lasts about `81 days`. |
| SPIDR control timestamp | packet type `0x5` | `25 ns` ticks | Used for shutter and heartbeat-style control packets. |

The unpacker should produce a final integer `timestamp_canonical` column when
enough information is available to place a row on its category's time axis.
The preferred exact common unit is:

```text
1 canonical tick = 25 ns / 12288
```

This unit can exactly represent `25 ns`, `3.125 ns`, `1.5625 ns`, `25 ns / 4096`,
and the TDC fine step of `25 ns / 96`. The unpacker should not write derived
floating-point time columns. Later analysis code may calculate floating-point
seconds or nanoseconds when needed.

Pixel-data, TDC-timestamp, heartbeat, and timestamped control rows should be
calculated in canonical time units. Heartbeat low and high packets should be
paired per chip; only paired heartbeat timestamps should be written. Timestamp
rollovers should be tracked independently for each chip and packet category. A
paired heartbeat row's `chunk_index` and `packet_index` should identify the high
packet that completed the pair; the low packet position should not be written.

Each timestamped dataset should be sorted by `timestamp_canonical`, using source
stream order internally as a stable tie breaker. For very large files, the
implementation should not require every extracted row to fit in memory. It may
write temporary sorted Parquet files and merge them into the final numbered
files.

## Summary JSON File

Each raw TPX3 file has one summary JSON file in `analysis/logs/`:

```text
<raw-file-stem>-unpacker-summary.json
```

For example:

```text
analysis/logs/DT_2p0V_000000-unpacker-summary.json
```

The summary JSON file is the sole saved detailed result for that raw TPX3 file.
It contains information calculated by the unpacker, including the raw byte
count. It does not repeat the unpacker program, raw input path, shared analysis
directory, summary filename, or overall HERMES unpacking status.

The summary should have this structure:

```yaml
unpacking:
  bytes_read: 0
  chunks_read: 0
  packets_read: 0
  pixel_data_packets: 0
  tdc_timestamps: 0
  heartbeat_packets: 0
  spidr_control_packets: 0
  tpx3_control_packets: 0
  unrecognized_packets: 0
  tdc1_rising: 0
  tdc1_falling: 0
  tdc2_rising: 0
  tdc2_falling: 0
  unknown_tdc_edges: 0
  errors: []
  warnings: []

timestamp_processing:
  heartbeat_pairs:
    number_of_beats: 0
  time_adjustments:
    pixel_packets: 0
    tdc_packets: 0
    control_packets: 0
    failed: 0

sorting:
  strategy: in_memory
  memory_budget_bytes: 0
  estimated_memory_bytes: 0
  temporary_runs_created: 0

parquet:
  pixel_data:
    row_count: 1200000
    files:
      - pixelHits/DT_2p0V_000000-chip-0-part-00000.parquet
      - pixelHits/DT_2p0V_000000-chip-0-part-00001.parquet
  tdc_timestamps:
    row_count: 0
    files: []
  heartbeat_packets:
    row_count: 0
    files: []
  control_packets:
    row_count: 0
    files: []
  unrecognized_packets:
    row_count: 0
    files: []
  errors: []

processing_times_seconds:
  canonical_time_seconds: 2.0345e-12
  unpacking: 0.0
  canonical_conversion: 0.0
  time_adjustments: 0.0
  sorting: 0.0
  parquet_writing: 0.0
  total: 0.0
  throughput:
    packets_per_second: 0.0
    megabytes_per_second: 0.0
```

All five category entries are required, including categories with no rows. The
file list contains only final Parquet files written for the raw TPX3 file named
by the summary filename; it must not list temporary sorting files or files from
a different input. Paths are relative to the shared analysis directory and
begin with their category directory, so the directory is not repeated in
another field. The file count is calculated from `len(files)` and is not saved.

Unpacked packet counts and Parquet row counts both remain because they describe
different processing stages. An unpacked packet may be rejected before a
Parquet row is written. Warnings and errors remain in the section that produced
them. `canonical_time_seconds` records the duration of one canonical tick:
`25 ns / 12288`, or about `2.0345 ps`. Throughput uses the total processing
time, with megabytes calculated as `1,000,000` bytes.

The TDC edge counts show how the unpacked timestamps divide between TDC1 and
TDC2 rising and falling edges. `heartbeat_pairs.number_of_beats` reports the
paired heartbeat timestamps used for time adjustment. The `time_adjustments`
counts show how many pixel, TDC, and control packets received adjusted times
and how many adjustments failed. `sorting.strategy` is either `in_memory` or
`external_merge`.

Write the summary only after every final Parquet file closes successfully.

## Photon Reconstruction

Photon reconstruction is a separate analysis step, not a required part of the
unpacker. A user-selected HERMES program reads sorted `pixel_data` Parquet files
from `analysis/pixelHits/` and writes photon Parquet files under
`analysis/photons/`. C++ and Rust versions live beside each other:

```text
backends/reconstruction/photons/
├── cpp/
└── rust/
```

`clustering_algorithm="connected_components"` selects the first program.
`"dbscan"` is reserved for a later program and must be rejected until that
program exists. Both programs must accept the same required inputs and settings
and write the same columns, filenames, metadata, summary fields, warnings,
errors, and exit codes.

### Connected Components with a Time Gate

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

### Pixel and Cluster Filtering

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

### Photon Timing Investigation

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

### Photon Parquet Files

The `analysis/photons/` directory contains two distinct filename groups:

```text
<raw-file-stem>-chip-<chip-index>-photon-events-part-<five-digit-part-index>.parquet
<raw-file-stem>-chip-<chip-index>-photon-pixels-part-<five-digit-part-index>.parquet
```

Part numbers start at zero independently for each raw input, chip, and file
group. `photon_events` is always written when accepted photons exist.
`photon_pixels` is written only when `save_photon_pixels` is true. An empty file
group has zero files and a zero row count in the summary.

#### `photon_events`

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

#### `photon_pixels`

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

### Reconstruction Summary JSON File

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

## Event Reconstruction

Event reconstruction is another separate analysis step. A user-selected event
reconstruction backend should read photon Parquet files and write event Parquet
files. Possible C++ and Rust versions should be grouped under:

```text
backends/event-reconstructors/<name>/
├── cpp/
└── rust/
```

The exact event file columns and timing rules must be added to the architecture
before the first event reconstruction backend is implemented.
