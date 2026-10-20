# Event reconstruction example

This example runs the event stage on its own, starting from an existing photon
file:

```text
photon-event Parquet file
  -> event Parquet file
```

Unpacking and photon reconstruction are already done for this dataset, so only
the event stage runs. The script copies the sample photon file
(`tests/data/photons/Tantalum_IronPowder.parquet`, 92,703 photons) into the
analysis `photons/` folder, named the way the photon stage names its files, and
groups the photons into events by connected components over space and time.

`pixi install` already builds the C++ event reconstructor. After changing C++
code, run `pixi reinstall hermes` so the example uses your changes.

## Run the example

Run the checked-in `photon-to-event.yaml`:

```bash
pixi run python examples/analysis/event_reconstruction/photon-to-event.py
```

To use another configuration, supply its path:

```bash
pixi run python examples/analysis/event_reconstruction/photon-to-event.py \
  /path/to/photon-to-event.yaml
```

## Configure event reconstruction

The `analysis.event_reconstruction` section selects the event reconstructor,
photon input directory, event output directory, and the clustering settings.
The checked-in configuration uses connected components with a 10-pixel linking
radius, a 5-cell-per-axis lookup grid, a 10 µs maximum time difference, and a
30 µs maximum event duration. There is no `photon_reconstruction` section
because the photon file already exists.

## Output

The checked-in configuration writes ignored development output under:

```text
data/examples/analysis/event_reconstruction/
├── hermes-record_final.yaml
└── photon-to-event/
    └── analysis/
        ├── photons/
        │   └── Tantalum_IronPowder_chip_0_photon_00000.parquet
        ├── events/
        │   └── Tantalum_IronPowder_event_candidates.parquet
        └── logs/
            └── event_reconstruction/
                └── Tantalum_IronPowder_event_reconstruction_summary.json
```

For the sample file, the script prints `Tantalum_IronPowder: completed, 45122 events`.

The event file contains each reconstructed event's centroid position, earliest
photon time, photon count, and quality flags. The reconstruction summary
contains the settings, photon and event counts, quality-flag counts, output
filenames, warnings, errors, and processing times.

Running the example again validates the existing summary JSON, skips complete
work, and refreshes `hermes-record_final.yaml`.
