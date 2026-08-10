# End-to-end TPX3 analysis example

This example uses one HERMES workflow to run the full chain, from a raw TPX3
file to reconstructed events:

```text
raw TPX3 file
  -> pixel-hit Parquet file    (analysis/pixel_hits/, from unpacking)
  -> photon Parquet file       (analysis/photons/, from photon reconstruction)
  -> event Parquet file        (analysis/events/, from event reconstruction)
```

The starting raw file (`tests/data/tpx3/Tantalum_IronPowder.tpx3`) is copied
into the working directory's `rawTpx3/` sub-directory, then unpacking, photon
reconstruction, and event reconstruction run in sequence. The completed HERMES
state is saved separately once all three stages finish.

## Build the C++ programs

Run these commands from the repository root:

```bash
pixi run build-cpp-unpacker
pixi run build-cpp-photon-clusterer
pixi run build-cpp-event-reconstructor
```

## Run the example

Run the checked-in `raw-to-events.yaml`:

```bash
pixi run python examples/analysis/end_to_end/raw-to-events.py
```

To use another configuration, supply its path:

```bash
pixi run python examples/analysis/end_to_end/raw-to-events.py \
  /path/to/raw-to-events.yaml
```

## Configure the stages

- `analysis.unpacking` selects the unpacker and the raw TPX3 file to unpack.
- `analysis.photon_reconstruction` selects the photon clusterer, its settings,
  and the time-walk calibration file
  (`calibrations/tpx3/time-walk_example.json`), using leading-edge photon time.
- `analysis.event_reconstruction` selects the event reconstructor and its
  connected-components settings (10-pixel linking radius, 5-cell-per-axis lookup
  grid, 10 µs maximum time difference, 30 µs maximum event duration).

## Output

The checked-in configuration writes ignored development output under:

```text
data/examples/analysis/end_to_end/
├── hermes-record_final.yaml
├── rawTpx3/
│   └── Tantalum_IronPowder.tpx3
└── analysis/
    ├── pixel_hits/
    │   └── Tantalum_IronPowder-chip-0-part-00000.parquet
    ├── photons/
    │   ├── Tantalum_IronPowder-chip-0-part-00000.parquet
    │   └── Tantalum_IronPowder-chip-0-part-00000-photon-pixels.parquet
    ├── events/
    │   └── Tantalum_IronPowder-chip-0-part-00000.parquet
    └── logs/
        ├── unpacker/
        │   └── Tantalum_IronPowder-unpacker-summary.json
        ├── photons/
        │   └── Tantalum_IronPowder-chip-0-part-00000-reconstruction-summary.json
        └── events/
            └── Tantalum_IronPowder-chip-0-part-00000-reconstruction-summary.json
```

(The unpacker also writes `control_packets/`, `global_timestamps/`, and
`tdc_triggers/` Parquet files under `analysis/`, omitted here for brevity.)

Each stage writes its own Parquet files and a summary JSON. Running the example
again validates the existing summaries, skips complete work, and refreshes
`hermes-record_final.yaml`.
