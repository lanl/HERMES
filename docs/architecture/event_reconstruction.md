# Event Reconstruction

Event reconstruction is a separate analysis step, not part of the unpacker or
photon reconstruction. A user-selected HERMES program reads photon Parquet files
from `analysis/photons/` and writes event Parquet files under `analysis/events/`.
C++ and Rust versions live beside each other:

```text
src/backends/event-reconstructors/
└── connected-components/
    ├── cpp/
    └── rust/
```

`event_algorithm="connected_components"` selects the first program. Both a C++
and a later Rust program must accept the same required inputs and settings and
write the same columns, filenames, metadata, summary fields, warnings, errors,
and exit codes. The C++ program is implemented first.

The goal of this first program is **reliable candidate event identification**,
not optimal event reconstruction. It groups detected photons into candidate
scintillation events and records a few observable properties per event. It does
not attempt interaction-position fitting, interaction-time estimation, energy
estimation, or separation of overlapping events; those are later work that
operates on individual candidate events rather than the full photon stream.

## Motivation

The TPX3Cam observes scintillation light at low optical efficiency, so the
clustering must tolerate missing photons and must not rely on high local
density:

- Many scintillation photons are never detected.
- An event may contain only two to five detected photons.
- A genuine event may produce a single detected photon.
- The first detected photon is not necessarily the first emitted photon.
- Large gaps between detected photons are expected from sparse sampling.

The linking thresholds are therefore intentionally permissive.

## Two Independent Parameters

The algorithm separates a **physics** parameter from an **implementation**
parameter, and they are chosen independently:

- The **spatial linking radius** (`spatial_link_radius_pixels`) decides when two
  photons are neighbors. It is a physics choice driven by detector light spread
  and optical blur.
- The **number of grid cells per axis** (`spatial_cells_per_axis`) sets how
  finely the field of view is divided for the neighbor-lookup grid. It is only a
  lookup accelerator: changing it must never change which events are produced; it
  may change only runtime, memory use, and the number of distance tests. The cell
  width in pixels is **derived** from it (see "Spatial Grid" below).

Both are user settings because event size depends on the optical setup. A
microscope objective may image a field under one centimeter, while a single-lens
system may cover roughly ten centimeters; the apparent size of an event, and so
the useful grid granularity, differs between them. The user adjusts
`spatial_cells_per_axis` alongside `spatial_link_radius_pixels` to match the
setup, subject to the one correctness constraint below.

## Connected Components over Space and Time

Each raw filename stem is processed one at a time, and each chip independently,
in the chip's local 256 x 256 pixel space. The program reads the chip's
`photon_events` parts in order.

Two photons are **connected** when they satisfy both criteria:

- Spatial: `(x_i - x_j)^2 + (y_i - y_j)^2 <= spatial_link_radius_pixels^2`. The
  squared form avoids the square root.
- Temporal: `|t_i - t_j| <= max_time_difference_ticks`.

Both bounds are inclusive. Photons are vertices and connected photon pairs are
edges; every connected component becomes one candidate event. Connectivity is
transitive, so components may branch. Unlike an ordered chain, every connected
photon contributes equally and there is no dependence on processing order.

### Time Ordering

`photon_events` rows are written in reconstruction order, which is close to but
not guaranteed to be strictly increasing in `timestamp_canonical`. After reading
a chip's photons the program sorts them by `timestamp_canonical`, breaking ties
by `photon_id`, and then streams them in that order. Photon counts are far
smaller than pixel counts, so this sort is inexpensive. The photon time is a
float64 canonical-tick value carried through unchanged.

### Streaming with a Rolling Time Window

The program keeps two data structures over active photons:

```cpp
std::deque<PhotonIndex> active_by_time;                 // rolling time window
std::array<std::vector<PhotonIndex>, kCellCount> cells; // spatial grid
```

A Union-Find (disjoint-set) structure over all photon indices records the
connected components as they form. For each photon `P_i` in time order:

1. Expire photons: pop from the front of `active_by_time` every photon `P_j`
   with `t_i - t_j > max_time_difference_ticks`, and remove each from its cell.
   Expired photons can never connect to a future photon, so the grid holds only
   active photons.
2. Finalize components: any open component whose latest photon time is more than
   `max_time_difference_ticks` behind `t_i` can gain no further members, so it
   is closed and its event is emitted in time order.
3. Compute `P_i`'s cell.
4. Search `P_i`'s own cell and its neighboring cells (see "Spatial Grid").
5. For each active photon `P_j` found, apply the exact squared-distance test.
   Every pair that passes is unioned with `P_i`. Most candidates fail the
   distance test; that is expected and acceptable.
6. Insert `P_i` into its cell and append it to `active_by_time`.

At end of input, all remaining open components are flushed. The spatial grid and
time window are updated continuously and are never rebuilt as time advances.

### Spatial Grid

The 256 x 256 chip is divided once into a fixed square grid for the whole
acquisition. Each photon maps to a cell:

```cpp
cell_x = static_cast<int>(x) / cell_width;
cell_y = static_cast<int>(y) / cell_width;
```

The cell width in pixels is **derived** from `spatial_cells_per_axis` and the
fixed 256-pixel chip width, so the user sets a cell count rather than a raw width:

```text
cell_width = ceil(256 / spatial_cells_per_axis)
```

Rounding up guarantees exactly `spatial_cells_per_axis` cells span the chip along
each axis; the last cell on each axis may be a little narrower than the rest,
which does not affect correctness. Worked examples:
`spatial_cells_per_axis = 5` (the default) gives cell width 52; `= 4` gives 64;
`= 3` gives 86; `= 2` gives 128; `= 1` gives 256.

The one correctness constraint is that the derived cell width must be **at least
the linking radius**. When it is, a photon within the radius can only fall in the
same cell or an immediately adjacent one, so a fixed **3 x 3** cell neighborhood
search is always sufficient and exact. A grid fine enough to make the cell width
smaller than the linking radius would let the 3 x 3 search miss genuine neighbors
and silently change the clustering result; such a combination of
`spatial_cells_per_axis` and `spatial_link_radius_pixels` is rejected during
settings validation rather than accepted. For sparse TPX3Cam data a wider cell
(fewer cells per axis) reduces bookkeeping at the cost of a few more distance
tests, which are cheap at low photon density.

This design avoids an O(N^2) all-pairs search while producing identical events
regardless of cell width.

## Event Properties

For every connected component the program computes the candidate event
properties written to `event_candidates`:

- Centroid position, the arithmetic mean of member-photon `x` and `y`
  (floating-point accumulation). Weighted or fitted positions are reserved.
- Event time, the earliest member-photon `timestamp_canonical`. This is an
  observable, not necessarily the true interaction time.
- Photon count, the number of member photons.

It also computes these diagnostics, which stay in the reconstruction summary and
are not written as event columns in this first program:

- latest member-photon time
- event duration (`latest - earliest`)
- spatial RMS about the centroid
- bounding box (`min_x`, `min_y`, `max_x`, `max_y`)

## Event Flags and Non-Discarding

The program never discards components. Two situations are flagged rather than
dropped, so later analysis can decide how to treat them.

Each event carries a `quality_flags` bit mask:

| Bit | Name | Meaning |
| --- | --- | --- |
| `0x0001` | `single_photon` | The event has exactly one member photon. It may be a genuine low-light event, detector background, or a dark count. |
| `0x0002` | `duration_exceeded` | The event duration is greater than `max_event_duration_ticks`. Connected components can occasionally chain separate events, so a long duration is suspicious rather than invalid. |

All other bits are reserved. Later split or ambiguous-event flags require
measured behavior and must not be guessed in the first program.

`min_photon_count` is an optional analysis threshold recorded in the settings and
summary. It does **not** cause the clustering stage to drop events; downstream
analysis may apply it.

## Settings

The program runs with built-in defaults and no settings file. An optional JSON
file overrides only the fields it names. Unknown keys, wrong value types, or
out-of-range values throw and cause a nonzero exit before any output is written.

| Setting | Type | Default | Meaning |
| --- | --- | --- | --- |
| `spatial_link_radius_pixels` | float64 | 20.0 | Physics linking radius in pixels. |
| `spatial_cells_per_axis` | uint32 | 5 | Number of neighbor-lookup grid cells along each detector axis. Accelerator only; must not be so large that the derived cell width falls below the linking radius. |
| `max_time_difference_ticks` | float64 | 245760.0 | Maximum time difference between two linked photons, in canonical ticks (500 ns). |
| `max_event_duration_ticks` | float64 | (tune) | Duration above which an event is flagged `duration_exceeded`. |
| `min_photon_count` | uint32 | 1 | Analysis threshold recorded for downstream use; not applied during clustering. |

`spatial_link_radius_pixels` (20) and `max_time_difference_ticks` (500 ns) were
chosen from a 9 mm microscope-FoV TaAtScraper run, where a single neutron's
scintillation light spreads over roughly 13-23 pixels and its photons arrive tens
to hundreds of ns apart, so a 500 ns link chains one neutron event together while
keeping separate neutrons apart. These suit that optical setup; other setups will
need different values. `max_event_duration_ticks` still has no principled default
and must be chosen by benchmarking before the `duration_exceeded` flag is trusted.
`spatial_cells_per_axis` is an implementation accelerator that the user tunes for
the optical setup; the cell width in pixels is derived from it as described above
and is not itself a setting.

Times are in canonical ticks. One canonical tick is `25 ns / 12288`, matching
the unpacker and photon reconstruction.

## Event Parquet Files

The `analysis/events/` directory contains one filename group:

```text
<raw-file-stem>-chip-<chip-index>-event-candidates-part-<five-digit-part-index>.parquet
```

Part numbers start at zero independently for each raw input and chip.
`event_candidates` is written whenever events exist. An empty group has zero
files and a zero row count in the summary.

### `event_candidates`

| Column | Arrow type | Nullable | Description |
| --- | --- | --- | --- |
| `event_id` | `uint64` | no | Zero-based event number within the raw input and chip |
| `x` | `float64` | no | Arithmetic mean member-photon x |
| `y` | `float64` | no | Arithmetic mean member-photon y |
| `timestamp_canonical` | `float64` | no | Earliest member-photon time in canonical ticks |
| `photon_count` | `uint64` | no | Number of member photons |
| `quality_flags` | `uint16` | no | Event flag bit mask |

Every event Parquet file records these string metadata values so a reader can
recover how the events were produced without the summary JSON:

- schema name and schema version
- canonical tick duration in seconds
- raw filename stem and chip index
- event algorithm name and complete event settings as JSON
- position rule (`arithmetic`)
- event time estimator (`earliest_photon`)

## Reconstruction Summary JSON File

Each raw TPX3 filename stem has one event-reconstruction summary, written only
after every final event Parquet file closes successfully. Paths are relative to
the analysis directory:

```text
analysis/logs/<raw-file-stem>-event-reconstruction-summary.json
```

```yaml
schema_version: 1

reconstruction:
  photons_read: 0
  components_formed: 0
  event_count: 0
  quality_flag_counts:
    single_photon: 0
    duration_exceeded: 0
  min_photon_count_below: 0   # events with fewer than min_photon_count members
  warnings: []
  errors: []

clustering:
  algorithm: connected_components
  settings: {}

event_timing:
  estimator: earliest_photon

parquet:
  input_photon_events_files: []
  event_candidates:
    row_count: 0
    files: []

processing_times_seconds:
  photon_reading: 0.0
  clustering: 0.0
  parquet_writing: 0.0
  total: 0.0
  throughput:
    photons_per_second: 0.0
    events_per_second: 0.0
```

The saved settings include `spatial_link_radius_pixels`,
`spatial_cells_per_axis`, `max_time_difference_ticks`, `max_event_duration_ticks`,
and `min_photon_count`. The derived cell width is recorded alongside them for
diagnostics. Per-input
counts, filenames, warnings, errors, timing, and throughput stay in this summary
and are not copied into the HERMES YAML file.

## Program Interface and Build

The C++ program mirrors the photon clusterer so the two are operated the same
way. It reads one `photon_events` Parquet file and writes one event file:

```text
hermes-event-reconstructor --input <photon_events_file> [--output <event_file>]
                           [--settings <file>] [--overwrite]
```

- `--input` is required; without `--output` the program prints summary counts
  and writes no files.
- With `--output` it writes the `event_candidates` file at the given path and
  the event-reconstruction summary JSON to a `logs/` directory beside the output
  directory.
- `--overwrite` replaces existing event and summary files; without it, an
  existing file is refused.
- Exit code 0 on success, 2 on argument or settings errors.

The build mirrors `src/backends/reconstruction/photons/cpp/`: CMake with
`cxx_std_17`, `-Wall -Wextra -Wpedantic`, Arrow and Parquet for Parquet I/O,
`nlohmann_json` for settings and the summary, a `hermes_event_reconstructor`
static library, the `hermes-event-reconstructor` executable, and CTest targets
per translation unit under `tests/`.

## Future Work

Once candidate events are reliable, later programs can operate on individual
events: improved interaction-time estimation, maximum-likelihood position
estimation, photon weighting, energy estimation, and separation of overlapping
events. These are additive and do not change the candidate-event stage.
