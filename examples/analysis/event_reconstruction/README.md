# Event reconstruction example

This example runs the event stage on its own, starting from an existing photon
file:

```text
photon-event Parquet file
  -> event Parquet file
```

Unpacking and photon reconstruction are already done for this dataset, so only
the event stage executes. The starting photon file
(`tests/data/photons/Tantalum_IronPowder.parquet`, 99,909 photons) is copied
into the analysis `photons/` directory and grouped into events by connected
components over space and time.

## Build the C++ program

Run this command from the repository root:

```bash
pixi run build-cpp-event-reconstructor
```

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
└── analysis/
    ├── photons/
    │   └── Tantalum_IronPowder.parquet
    ├── events/
    │   └── Tantalum_IronPowder.parquet
    └── logs/
        └── events/
            └── Tantalum_IronPowder-reconstruction-summary.json
```

The event file contains each reconstructed event's centroid position, earliest
photon time, photon count, and quality flags. The reconstruction summary
contains the settings, photon and event counts, quality-flag counts, output
filenames, warnings, errors, and processing times.

Running the example again validates the existing summary JSON, skips complete
work, and refreshes `hermes-record_final.yaml`.
