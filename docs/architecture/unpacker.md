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
<executable> <input.tpx3> <analysis_directory>
```

The unpacker derives all category directories and output filenames from those
two inputs. Do not add separate command options for category directories, a
filename prefix, or a summary filename.

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

Every Parquet filename carries the raw TPX3 filename stem, chip index, and part
index:

```text
<raw-file-stem>-chip-<chip-index>-part-<five-digit-part-index>.parquet
```

For example, the first pixel-data part for chip 0 from
`DT_2p0V_000000.tpx3` is:

```text
analysis/pixelHits/DT_2p0V_000000-chip-0-part-00000.parquet
```

Part numbers start at zero independently for each raw file, chip, and data
category. The category name does not need to be repeated in the filename
because it is already stated by the parent directory. The chip index belongs in
the filename and should not be repeated in its rows. When a schema includes
`packet_index`, it is the packet index within its chunk.

Raw TPX3 filename stems must be unique within one measurement. The HERMES
runner must reject duplicate stems before launching any unpacker so one input
cannot overwrite another input's files. Existing files with the same expected
names must also cause the run to stop; the unpacker must not silently overwrite
them.

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
unpacker. A user-selected photon reconstruction backend should read the
`pixel_data` Parquet files and write photon Parquet files. Possible C++ and Rust
versions should be grouped under:

```text
backends/photon-reconstructors/<name>/
├── cpp/
└── rust/
```

The purpose of photon clustering is to group adjacent pixel-data rows that
likely came from one photon entering the image intensifier and producing a
phosphor response across multiple TPX3 pixels. A first clustering pass should
be configurable and should save its full settings in the summary and HERMES
state.

Important clustering parameters include:

- spatial adjacency rule, such as 4-connected or 8-connected pixels
- maximum time spread allowed within one cluster
- minimum and maximum cluster size
- ToT thresholds or ToT weighting rules
- ToA averaging rule
- x and y averaging rule
- whether clustering is performed before or after TDC association
- quality flags for ambiguous, saturated, split, or merged clusters

The photon output directory should contain two Parquet file groups:

- `photon_events`: one row per reconstructed photon candidate
- `photon_pixels`: membership rows linking source pixel data to photon candidates

`photon_events` should be a minimal event table with only the reconstructed
photon coordinates and signal values:

- `x`: average x position of the source pixels
- `y`: average y position of the source pixels
- `timestamp_canonical`: reconstructed photon time in canonical time units
- `tot`: sum of source-pixel ToT values in native units

The averaging rule should be explicit in the clustering metadata. The first
implementation may use arithmetic averages, but the schema should allow a
ToT-weighted average or fitted estimate later. Cluster diagnostics such as pixel
count, time span, quality flags, and source-pixel membership should not be
required fields in `photon_events`; they can be saved in `summary.json`, the
HERMES state, or optional diagnostic tables.

`photon_pixels` may include columns such as:

- `photon_id`
- `pixel_event_id`
- `x`
- `y`
- `tot_raw`
- `timestamp_canonical`

The HERMES state should save the photon-clustering settings, run status,
pixel-data input directory, photon-event output directory, photon-pixel output
directory, program version, photon counts, warnings, and errors.

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
