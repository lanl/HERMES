# TPX3 SPIDR Unpacking

TPX3 SPIDR unpackers should live outside the Python package. C++ and Rust
versions should live beside each other:

```text
src/backends/unpackers/tpx3-spidr/
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
program. Code in `src/hermes/runner/analysis/` should run the selected executable,
check the summary JSON file, and save the results through
`hermes.state_service`. It must not change the HERMES state directly.

The Python runner should call the unpacker with the raw TPX3 file and the
shared analysis directory:

```text
<executable> --input <input.tpx3> --output <analysis_directory> --measurement-id <measurement-id> --run <run> [--overwrite] [--time-sort]
```

The unpacker accepts exactly these options and no others:

- `--input <input.tpx3>` — the raw TPX3 file to unpack. Required; the unpacker
  raises an error if it is missing. Implemented.
- `--output <analysis_directory>` — the shared analysis directory. The unpacker
  creates all category directories and output filenames from it. Optional; when
  omitted, the unpacker prints summary statistics only and writes no files. The
  HERMES analysis workflow always supplies it. Implemented.
- `--measurement-id <measurement-id>` — the measurement identifier. The unpacker
  copies it into the summary JSON so each summary names the measurement it
  belongs to. Required when `--output` is given.
- `--run <run>` — the run label within the measurement. The unpacker copies it
  into the summary JSON next to the measurement identifier. Required when
  `--output` is given.
- `--overwrite` — redo the unpacking or reconstruction and replace existing
  output files instead of stopping. Optional, defaults to false. Without it the
  unpacker preserves existing files (see below). Implemented.
- `--time-sort` — sort output by canonical timestamp. Optional, defaults to
  false. Not implemented yet.

Do not add any option outside this list. The measurement identifier and run
label are the only run-identity inputs; in particular, do not add separate
command options for category directories, a filename prefix, or a summary
filename; the unpacker creates those from `--output`.

The Python runner should keep this simple and clean: confirm the input file is
set, then call the binary with the flags. Do not add helper functions or a
builder abstraction for assembling the command.

The HERMES state should save the raw TPX3 input files, shared analysis
directory, unpacker program, and per-file unpacking status. Each
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
    ├── pixel_hits/
    ├── tdc_triggers/
    ├── global_timestamps/
    ├── control_packets/
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
| Pixel data | `pixel_hits/` | `pixel_data` |
| TDC timestamps | `tdc_triggers/` | `tdc_timestamps` |
| Heartbeat packets | `global_timestamps/` | `heartbeat_packets` |
| Control packets | `control_packets/` | `control_packets` |
| Unrecognized packets | `unknownPackets/` | `unrecognized_packets` |

## Parquet Filenames

Filenames join the raw TPX3 filename stem, a descriptive data label, and a
five-digit part index with underscores:

```text
<raw-file-stem>_<data-label>_<five-digit-part-index>.parquet
```

Pixel data can come from more than one chip, so its label carries the chip
index:

```text
<raw-file-stem>_chip_<chip-index>_pixels_<five-digit-part-index>.parquet
```

For example, the first pixel-data part for chip 0 from `DT_2p0V_000000.tpx3` is:

```text
analysis/pixel_hits/DT_2p0V_000000_chip_0_pixels_00000.parquet
```

The other categories are not associated with a chip. Global timestamps, control
packets, and unrecognized packets use the category name as their label:

| Directory | Data label |
| --- | --- |
| `global_timestamps/` | `global_timestamps` |
| `control_packets/` | `control_packets` |
| `unknownPackets/` | `unrecognized_packets` |

TDC triggers are split by channel and edge (see below), so the `tdc_triggers/`
directory uses one of four labels instead of a single category name:

| Directory | Data label | Written when |
| --- | --- | --- |
| `tdc_triggers/` | `tdc1_rising_triggers` | any TDC1 rising trigger occurs |
| `tdc_triggers/` | `tdc1_falling_triggers` | any TDC1 falling trigger occurs |
| `tdc_triggers/` | `tdc2_rising_triggers` | any TDC2 rising trigger occurs |
| `tdc_triggers/` | `tdc2_falling_triggers` | any TDC2 falling trigger occurs |

Each label produces a file only when at least one trigger of that channel and
edge occurs; a channel or edge that never fires produces no file. For example, a
raw file with only TDC1 rising triggers writes just one TDC file:

```text
analysis/tdc_triggers/DT_2p0V_000000_tdc1_rising_triggers_00000.parquet
```

Part numbers start at zero independently for each raw file, data category,
(for pixel data) chip, and (for TDC triggers) channel and edge. The descriptive
label makes each file readable on its own; when a chip index is present it should
not be repeated in the rows. When a schema includes `packet_index`, it is the
packet index within its chunk.

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
not an arrival-timestamp component. TDC triggers are written to separate files
by channel and edge, so the channel (TDC1 or TDC2) and edge (rising or falling)
are carried by the filename rather than a column; each TDC table contains only
`chunk_index`, `packet_index`, and `timestamp_canonical`. Invalid-time TDC
packets should be counted as unpacking errors and omitted from Parquet.

On a multi-chip sensor the SPIDR board copies each external TDC trigger into
every chip's data stream, so one physical trigger is decoded once per chip. The
unpacker removes these duplicates before writing Parquet, keeping one row per
physical trigger (identified by its channel, edge, and canonical timestamp). The
raw per-packet decode counts still include every copy, but the TDC trigger
counts and Parquet rows report the de-duplicated triggers.

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
| `chunk_index` | `uint64` | no | Chunk index in the input file |
| `packet_index` | `uint64` | no | Packet index within the chunk |
| `timestamp_canonical` | `uint64` | no | Unwrapped final timestamp |

The channel and edge are encoded in the filename (see Parquet Filenames), so
they are not written as a column. Raw edge code, trigger counter, reserved bits,
fine-time validity, and packet provenance remain unpacker diagnostics and are
not written. A TDC packet with an invalid fine-time value does not produce a
Parquet row.

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
| TDC timestamp | 35-bit (bits 43-9) | `3.125 ns` ticks | Single edge-time counter, where `3.125 ns = 25 ns / 8`. Wraps after `2^35 * 3.125 ns`, about `107.37 s`. |
| TDC fine time | 4-bit, values `1..12` | `25 ns / 96` steps, about `260.417 ps` | Twelve steps fill one `3.125 ns` counter tick. Value `0` is an error state per ASI documentation. |
| Heartbeat timestamp low | 32-bit | `25 ns` ticks | Low part of the 48-bit global timer. |
| Heartbeat timestamp high | 16-bit | high bits of same `25 ns` timer | Combined 48-bit global timer wraps after about `81 days`. |
| SPIDR control timestamp | 34-bit (bits 45-12) | `25 ns` ticks | Used for shutter and heartbeat-style control packets. Wraps after `2^34 * 25 ns`, about `429.5 s`. This low-rate control heartbeat is separate from the 48-bit master timer above. |

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

## How the clocks synchronize

The four counters above do not each restart at the top of a file, and they are
not all the same width. They are all driven from one `25 ns` time base inside
the SPIDR board:

- The 48-bit heartbeat timer is the master clock. It starts when the run begins
  and runs continuously until the run ends; the board does not reset it between
  files. Because it is 48 bits wide it does not wrap within a realistic run
  (about `81 days`). Every other time is placed against it.
- The pixel coarse counter (30-bit, about `26.84 s`), the TDC counter (35-bit,
  about `107.37 s`), and the SPIDR control counter (34-bit, about `429.5 s`)
  share the same `25 ns` base but are far narrower than a run, so each one wraps
  back to zero many times. Their low bits already match the master clock; only
  the number of wraps is missing.

The unpacker recovers the missing wrap count by comparing each short counter to
the heartbeat clock on the same chip. It adds whole counter periods until the
counter's time in canonical ticks sits as close as possible to the heartbeat's
time in canonical ticks; the number of periods added is the wrap count for that
row. Wraps are counted separately for each chip and each packet category,
because the counters differ in width and each chip carries its own heartbeat.

Once every row carries its wrap count, all four streams share one absolute time
axis measured in canonical ticks from the start of the run. Times from
different streams can then be subtracted directly. A neutron time of flight, for
example, is a pixel or event time minus the most recent TDC time, both already
on this shared axis.

Because the axis is measured from the start of the run and not the start of a
file, absolute timestamps grow with elapsed run time. A file holding the Nth
fixed-length frame of a run begins near N times the frame length; for a run with
`2 s` frames the hundredth file begins near `200 s`. This is expected and does
not indicate a clock error.

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

Each raw TPX3 file has one summary JSON file in `analysis/logs/unpacking/`:

```text
<raw-file-stem>_unpacker_summary.json
```

For example:

```text
analysis/logs/unpacking/DT_2p0V_000000_unpacker_summary.json
```

The summary JSON file is the sole saved detailed result for that raw TPX3 file.
It contains information calculated by the unpacker, including the raw byte
count. It opens with the measurement identifier and run label (from
`--measurement-id` and `--run`) and the raw input path, so each summary names
the measurement, run, and file it belongs to. It does not repeat the unpacker
program, shared analysis directory, summary filename, or overall HERMES
unpacking status.

The summary should have this structure:

```yaml
measurement_info:
  measurement_id: harness-01-unpacking
  run: 1kHz-testing

inputfile: tests/data/tpx3/Example_1kHz_5frames.tpx3

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
  sorting_time_seconds: 0.0

output_parquet:
  pixel_data:
    row_count: 1200000
    files:
      - data/expt/1kHz-testing/analysis/pixel_hits/DT_2p0V_000000_chip_0_pixels_00000.parquet
      - data/expt/1kHz-testing/analysis/pixel_hits/DT_2p0V_000000_chip_0_pixels_00001.parquet
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
a different input. Each path is the `--output` directory joined with the
category directory and filename, exactly as `--output` was given, so a reader
can open the file directly from the working directory. The file count is
calculated from `len(files)` and is not saved.

Unpacked packet counts and Parquet row counts both remain because they describe
different processing stages. An unpacked packet may be rejected before a
Parquet row is written. Warnings and errors remain in the section that produced
them. `canonical_time_seconds` records the duration of one canonical tick:
`25 ns / 12288`, or about `2.0345 ps`. Throughput uses the total processing
time, with megabytes calculated as `1,000,000` bytes.

The TDC edge counts show how the de-duplicated triggers divide between TDC1 and
TDC2 rising and falling edges; they sum to `tdc_timestamps` and match the TDC
Parquet row counts. `heartbeat_pairs.number_of_beats` reports the paired
heartbeat timestamps used for time adjustment. The `time_adjustments` counts
show how many pixel, TDC, and control packets received adjusted times and how
many adjustments failed; the TDC count includes every decoded packet, including
the per-chip duplicates removed before writing. `sorting.strategy` is either
`in_memory` or `external_merge`.

Write the summary only after every final Parquet file closes successfully.