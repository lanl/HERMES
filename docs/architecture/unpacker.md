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

The CLI should have an explicit interface, for example:

```text
<executable> input.tpx3 --output tpx3_parquet/ --summary tpx3_parquet/summary.json
```

This is the planned interface. The first C++ output implementation should expose
the complete workflow through its library, but should not add the `--output` and
`--summary` argument parsing yet.

The HERMES state should save the raw TPX3 input file, TPX3 Parquet output
directory, summary JSON file, unpacker name, unpacker version, command
arguments, pixel-hit count, TDC-trigger count, global-timestamp count,
control-packet count, timing ranges, warnings, and errors.

## TPX3 Parquet Output Directory

The unpacker should write separate Apache Parquet files for each TPX3 packet type
instead of combining every row in one large file. 

Following the working environment laidout by HERMES of 

```text
working_dir = /tmp/mymeasurements
data_dir = working_dir / "data"
raw_data_dir = data_dir / "tpx3"
analyzed_data_dir = data_dir / "analysis"
log_dir = working_dir / "logs"
preview_dir = working_dir / "preview"
```

The output directory should
look like:

```text
`data_dir`/
├── `log_dir`/
│   ├── `filename_0000.log`
│   └── `filename_0001.log`
├── `preview_dir`
│   ├── `filename_0000.png`
│   └── `filename_0001.png`
├── `raw_data_dir`/
│   ├── `filename_0000.tpx3`
│   └── `filename_0001.tpx3`
└── `analyzed_data_dir`/   
    ├── summaries/
    │   ├── `filename_0000-unpacker.json`
    │   └── `filename_0001-unpacker.json`
    ├── pixel_hits/
    │   ├── `filename_0000.parquet`
    │   └── `filename_0001.parquet`
    ├── tdc_triggers/
    │   ├── `filename_0000.parquet`
    │   └── `filename_0001.parquet`
    ├── global_timestamps/
    │   ├── `filename_0000.parquet`
    │   └── `filename_0001.parquet`
    ├── control_packets/
    │   ├── `filename_0000.parquet`
    │   └── `filename_0001.parquet`
    ├── unknown_packets/
    │   ├── `filename_0000.parquet`
    │   └── `filename_0001.parquet`
    └── integrated_pixels/
        ├── `filename_0000.parquet`
        └── `filename_0001.parquet`
```

The chip index belongs in each Parquet file name and should not be repeated in
its rows. Part numbers start at zero independently for each chip and dataset.
When a schema includes `packet_index`, it is the packet index within its chunk.

Integrated-ToT packets should be decoded and counted, but the first output
contract does not write them. A later acquisition-mode-specific version may add
an `integrated_pixels/` directory.

The C++ decoder should use the native integer timing fields to calculate final
timestamps, but it should not copy those raw timing fields into Parquet. Each
known timestamped dataset should contain only `timestamp_canonical` for time.
The Parquet metadata and summary JSON file should define the canonical unit.

Pixel ToT should remain in the pixel table because it is a detector measurement,
not an arrival-timestamp component. The TDC table should contain only
`trigger_type` and `timestamp_canonical`. `trigger_type` uses `0` for TDC1
rising, `1` for TDC1 falling, `2` for TDC2 rising, and `3` for TDC2 falling.
Invalid-time TDC packets should be counted as decoder errors and omitted from
Parquet.

## Parquet Schemas

Known-packet tables should contain the final analysis values rather than copies
of raw packet words or raw timestamp components. Unknown packets retain their
raw word because no reliable decoded representation exists for them.

### `pixel_hits`

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `chunk_index` | `uint64` | no | Chunk index in the input file |
| `packet_index` | `uint64` | no | Packet index within the chunk |
| `local_x` | `uint16` | no | Chip-local x coordinate |
| `local_y` | `uint16` | no | Chip-local y coordinate |
| `tot_raw` | `uint16` | no | Pixel ToT measurement |
| `timestamp_canonical` | `uint64` | no | Unwrapped final timestamp |

The raw `pixel_address`, ToA, FToA, and SPIDR time are used by the C++ decoder
but are not copied into Parquet. `local_x` and `local_y` contain the complete
decoded pixel location.

### `tdc_triggers`

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `trigger_type` | `uint8` | no | `0` TDC1 rising, `1` TDC1 falling, `2` TDC2 rising, `3` TDC2 falling |
| `timestamp_canonical` | `uint64` | no | Unwrapped final timestamp |

The normalized trigger type replaces separate channel and edge columns. Raw
edge code, trigger counter, reserved bits, fine-time validity, and packet
provenance remain decoder diagnostics and are not written. A TDC packet with an
invalid fine-time value does not produce a Parquet row.

### `global_timestamps`

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `chunk_index` | `uint64` | no | Chunk containing the high packet that completed the timestamp |
| `packet_index` | `uint64` | no | High packet index within that chunk |
| `timestamp_canonical` | `uint64` | no | Paired and unwrapped final timestamp |

Only complete low/high pairs are written. The low packet position and raw low,
high, paired, and SPIDR timing values are not copied into Parquet. Unpaired
packet counts belong in `summary.json`.

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

### `unknown_packets`

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `chunk_index` | `uint64` | no | Chunk index in the input file |
| `packet_index` | `uint64` | no | Packet index within the chunk |
| `raw_word` | `uint64` | no | Original unknown packet word |
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
| Global timestamp low | 32-bit | `25 ns` ticks | Low part of the 48-bit global timer. |
| Global timestamp high | 16-bit | high bits of same `25 ns` timer | Combined global timer lasts about `81 days`. |
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

Pixel, TDC, global-timestamp, and timestamped control rows should be calculated
in canonical time units. Global low and high packets should be paired per chip;
only paired global timestamps should be written. Timestamp rollovers should be
tracked independently for each chip and packet category. A paired global row's
`chunk_index` and `packet_index` should identify the high packet that completed
the pair; the low packet position should not be written.

Each timestamped dataset should be sorted by `timestamp_canonical`, using source
stream order internally as a stable tie breaker. For very large files, the
implementation should not require every extracted row to fit in memory. It may
write temporary sorted Parquet files and merge them into the final numbered
files.

## Summary JSON File

The summary JSON file should use nested `backend`, `configuration`, `source`,
and `output` objects. `source` describes the one raw `.tpx3` input file.
`output` contains the output directory, summary filename, and one entry for each
Parquet dataset with its row count, file count, and relative file paths.

Packet-family counts, validation counts, warnings, and errors should remain
separate top-level objects or arrays. A complete success summary should be
written only after every final Parquet file closes successfully.

The summary should also contain a top-level `timing` object for pixel hits, TDC
triggers, and global timestamps. Each entry should record the counter width,
native unit, raw maximum, rollover tick count and period, half-range rollover
detection threshold, canonical units per rollover, and detected rollover count
for each chip.

## Photon Reconstruction

Photon reconstruction is a separate analysis step, not a required part of the
unpacker. A user-selected photon reconstruction backend should read the
`pixel_hits` Parquet files and write photon Parquet files. Possible C++ and Rust
versions should be grouped under:

```text
backends/photon-reconstructors/<name>/
├── cpp/
└── rust/
```

The purpose of photon clustering is to group adjacent pixel hits that likely came
from one photon entering the image intensifier and producing a phosphor response
across multiple TPX3 pixels. A first clustering pass should be configurable and
should save its full settings in the summary and HERMES state.

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
- `photon_pixels`: membership rows linking source pixel hits to photon candidates

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
pixel-hit input directory, photon-event output directory, photon-pixel output
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
