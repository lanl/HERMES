# TPX3 SPIDR Unpacker

The Rust unpacker should live outside the Python package:

```text
crates/hermes-tpx3-spidr/
```

The Rust crate should own low-level `.tpx3` packet decoding. It should keep the
core decoding logic in `src/lib.rs` and expose a CLI in `src/main.rs`.

The Python package should treat the unpacker as an external analysis engine. A
Python wrapper in `src/hermes/analysis/hermes_tpx3_spidr.py` can call the binary,
validate its summary output, and use `hermes.state_service` to update the
central Pydantic record. The wrapper must not directly mutate the record.

The CLI should have an explicit interface, for example:

```text
hermes-tpx3-spidr input.tpx3 --output decoded/ --summary decoded/summary.json
```

The state record should capture the input artifact, output artifact, summary
artifact, tool name, tool version, command arguments, packet counts, event
counts, timing ranges, warnings, and errors.

## Parquet Dataset

Decoded output should be written as an Apache Parquet dataset, preferably as a
directory of typed tables rather than one very large file. A first decoded
dataset might look like:

```text
decoded/
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
  photon/
    photon_events/
      part-00000.parquet
    photon_pixels/
      part-00000.parquet
```

The raw decoded tables should preserve native integer timing fields. Pixel hits,
TDC hits, and global timestamp packets have different timing fields and
resolutions, so the unpacker should not convert these fields only to floating
point seconds. Instead, it should keep raw integer columns and write metadata
that explains their units.

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

The unpacker should document native timestamp fields and units in the decoded
dataset metadata. The initial reference table is:

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
when enough information is available to place records on one shared time axis.
The preferred exact common unit is:

```text
1 canonical tick = 25 ns / 12288
```

This unit can exactly represent `25 ns`, `3.125 ns`, `1.5625 ns`, `25 ns / 4096`,
and the TDC fine step of `25 ns / 96`. Floating-point seconds or nanoseconds may
be added as convenience columns, but integer raw fields and integer synchronized
time should remain the source of truth.

If sorted output is required for timing analysis, the unpacker should sort by
canonical event time and record the sort order in metadata. For very large files,
the implementation should not require all decoded events to fit in memory. It
should be able to decode and sort chunks, write temporary sorted parts, and merge
those parts into a final sorted Parquet dataset.

## Photon Clustering

The unpacker may also produce photon-cluster output for image-intensifier data.
This should be treated as derived data built from decoded pixel hits, not as a
replacement for the raw `pixel_hits` table.

The purpose of photon clustering is to group adjacent pixel hits that likely came
from one photon entering the image intensifier and producing a phosphor response
across multiple TPX3 pixels. A first clustering pass should be configurable and
should record its full configuration in the summary and state model.

Important clustering parameters include:

- spatial adjacency rule, such as 4-connected or 8-connected pixels
- maximum time spread allowed within one cluster
- minimum and maximum cluster size
- ToT thresholds or ToT weighting rules
- ToA averaging rule
- x and y averaging rule
- whether clustering is performed before or after TDC association
- quality flags for ambiguous, saturated, split, or merged clusters

The `decoded/photon/` dataset should contain at least two logical tables:

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
required fields in `photon_events`; they can be recorded in `summary.json`, the
state model, or optional diagnostic tables.

`photon_pixels` may include columns such as:

- `photon_id`
- `pixel_event_id`
- `x`
- `y`
- `tot_raw`
- `event_time_ticks`

The state model should capture photon clustering as an analysis/unpack stage
with its own plan, status, input artifacts, output artifacts, algorithm version,
parameters, counts, warnings, and errors.
