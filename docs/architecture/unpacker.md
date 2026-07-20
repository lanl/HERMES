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

Python should run the unpacker selected by the user as a separate command-line
program. Code in `src/hermes/analysis/` should run the selected executable,
check the summary JSON file, and save the results through
`hermes.state_service`. It must not change the HERMES state directly.

The CLI should have an explicit interface, for example:

```text
<executable> input.tpx3 --output tpx3_parquet/ --summary tpx3_parquet/summary.json
```

The HERMES state should save the raw TPX3 input file, TPX3 Parquet output
directory, summary JSON file, unpacker name, unpacker version, command
arguments, pixel-hit count, TDC-hit count, global-timestamp count,
control-packet count, timing ranges, warnings, and errors.

## TPX3 Parquet Output Directory

The unpacker should write separate Apache Parquet files for each TPX3 packet type
instead of combining every row in one large file. The output directory should
look like:

```text
tpx3_parquet/
  summary.json
  pixel_hits/
    part-00000.parquet
    part-00001.parquet
  tdc_hits/
    part-00000.parquet
  global_timestamps/
    part-00000.parquet
  control_packets/
    part-00000.parquet
```

The Parquet files should preserve the integer timing fields read from the raw
packets. Pixel hits, TDC hits, and global timestamp packets have different timing
fields and resolutions, so the unpacker should not replace them with only
floating-point seconds. It should keep the integer columns and save their units
in the Parquet metadata and summary JSON file.

For example, pixel timing columns may include:

- `toa_raw`
- `ftoa_raw`
- `tot_raw`
- `spidr_time_raw`

TDC timing columns may include:

- `tdc_timestamp_raw`
- `tdc_fine_raw`
- `trigger_counter`

## Native Timestamp Fields

The unpacker should save the following timestamp fields and units in the
Parquet metadata and summary JSON file:

| Quantity | Raw field | Native unit | Notes |
| --- | --- | --- | --- |
| Pixel `spidr_time` | 16-bit | `25 ns * 2^14 = 409.6 us` | Extends pixel ToA beyond 14 bits. |
| Pixel `ToA` | 14-bit | `25 ns` ticks | Coarse pixel arrival time. |
| Pixel `FToA` | 4-bit | `-1.5625 ns` correction | Fine ToA correction. SERVAL treats this as negative fine time. |
| Pixel `ToT` | 10-bit | `25 ns` ticks | Native ToT is a tick count; physical energy calibration is separate. |
| Pixel coarse timestamp | `(spidr_time << 14) | ToA` | `25 ns` ticks | 30-bit coarse pixel time, maximum about `26.84 s`. |
| Pixel fine timestamp | derived from `spidr_time`, `ToA`, and `FToA` | `1.5625 ns` derived ticks | A common ASI formula is `(((spidr_time << 14) + ToA) << 4) - FToA`. |
| TDC edge ID | packet subheader | none | `0xF` TDC1 rise, `0xA` TDC1 fall, `0xE` TDC2 rise, `0xB` TDC2 fall. |
| TDC trigger counter | 12-bit | count | Counter, not a time. |
| TDC coarse time | packet timestamp field | `25 ns` ticks | Used with finer TDC fields to derive edge time. |
| TDC sub-coarse time | packet timestamp field | `3.125 ns` ticks | Part of the TDC timestamp. |
| TDC fine time | 4-bit, values `1..12` | `260.416666 ps` steps | Value `0` is an error state per ASI documentation. |
| Global timestamp low | 32-bit | `25 ns` ticks | Low part of the 48-bit global timer. |
| Global timestamp high | 16-bit | high bits of same `25 ns` timer | Combined global timer lasts about `81 days`. |
| SPIDR control timestamp | packet type `0x5` | `25 ns` ticks | Used for shutter and heartbeat-style control packets. |

The unpacker should also produce a canonical synchronized integer time column
when enough information is available to place rows on one shared time axis.
The preferred exact common unit is:

```text
1 canonical tick = 25 ns / 12288
```

This unit can exactly represent `25 ns`, `3.125 ns`, `1.5625 ns`, `25 ns / 4096`,
and the TDC fine step of `25 ns / 96`. Floating-point seconds or nanoseconds may
be added as convenience columns, but integer raw fields and integer synchronized
time should remain the source of truth.

If sorted output is required for timing analysis, the unpacker should sort by
canonical event time and save the sort order in metadata. For very large files,
the implementation should not require every extracted row to fit in memory. It
should read and sort chunks, write temporary sorted Parquet files, and merge them
into the final Parquet files.

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
- `toa`: average source-pixel ToA in native clock ticks
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
- `event_time_ticks`

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
