# End-to-end TPX3 analysis example

This example uses one HERMES workflow to run the full chain, from a raw TPX3
file to reconstructed events:

```text
raw TPX3 file
  -> pixel-hit Parquet file    (analysis/pixel_hits/, from unpacking)
  -> photon Parquet file       (analysis/photons/, from photon reconstruction)
  -> event Parquet file        (analysis/events/, from event reconstruction)
```

The raw file is the sample `tests/data/tpx3/Tantalum_IronPowder.tpx3`, read
where it is. Unpacking, photon reconstruction and event reconstruction run in
order, and the completed HERMES record is saved separately once all three
finish.

`pixi install` already builds the three C++ programs. After changing C++ code,
run `pixi reinstall hermes` so the example uses your changes.

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
  and optional time-walk correction. The checked-in config uses
  `photon_time_estimator: average` and `timewalk: {method: none}`: each photon's
  time is the arithmetic average of all its source-hit times, without correction.
  See [photon timing](../../../docs/photon-timing.md) for calibrated timing,
  brightest-hit timing, and explicit leading-edge timing.
- `analysis.event_reconstruction` selects the event reconstructor and its
  connected-components settings (10-pixel linking radius, 5-cell-per-axis lookup
  grid, 10 µs maximum time difference, 30 µs maximum event duration).

## Output

The checked-in configuration writes ignored development output under:

```text
data/examples/analysis/end_to_end/
├── hermes-record_final.yaml
└── raw-to-events/
    └── analysis/
        ├── pixel_hits/
        │   └── Tantalum_IronPowder_chip_0_pixels_00000.parquet
        ├── photons/
        │   └── Tantalum_IronPowder_chip_0_photon_00000.parquet
        ├── pixel_clusters/
        │   └── Tantalum_IronPowder_chip_0_pixel_clusters_00000.parquet
        ├── events/
        │   └── Tantalum_IronPowder_event_candidates.parquet
        └── logs/
            ├── unpacking/
            │   └── Tantalum_IronPowder_unpacker_summary.json
            ├── photon_reconstruction/
            │   └── Tantalum_IronPowder_chip_0_photon_reconstruction_summary_00000.json
            └── event_reconstruction/
                └── Tantalum_IronPowder_event_reconstruction_summary.json
```

(The unpacker also writes `control_packets/`, `global_timestamps/` and
`tdc_triggers/` Parquet files under `analysis/`, left out here.)

The script prints the photon and event counts: 92,703 photons and 45,122 events
for the sample file.

Each stage writes its own Parquet files and a summary JSON. Running the example
again validates the existing summaries, skips complete work, and refreshes
`hermes-record_final.yaml`.
After changing photon timing, enable
`analysis.photon_reconstruction.runtime_options.overwrite: true` or use a fresh
analysis directory. Photon overwrite also regenerates downstream events when
both stages run together.
