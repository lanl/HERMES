# HERMES TPX3 Time-Walk Calibration Example

This example unpacks raw TPX3 files and then fits a time-walk correction from
the resulting `pixel_data` using the in-cluster relative method. It writes a
detailed calibration-result JSON, a comparison plot, and the small correction
file that the photon reconstruction clusterer consumes. The script constructs a
`Workflow` from one `HermesRecord`, calls `workflow.run_analysis()`, and saves
the completed `workflow.record`.

## Input Files

The example unpacks all TPX3 files found in `data/list_tests/`:

- `Example_1kHz_5frames_0000.tpx3`
- `Example_1kHz_5frames_0001.tpx3`
- `Example_1kHz_5frames_0002.tpx3`
- `Example_1kHz_5frames_0003.tpx3`

> **Substitute your own data.** These bundled files are the unpacker test
> fixtures. They do **not** contain photon-like phosphor blobs, so they yield
> no in-cluster pixel pairs and the calibration cannot fit a correction — the
> example prints a message and exits. To produce a real calibration, edit
> `RAW_TPX3_DIRECTORY` in `run_timewalk_calibration.py` to point at a directory
> of TPX3 files that contain phosphor clusters.

## Building the Unpacker

Before running the example, build the C++ unpacker:

```bash
pixi run build-cpp-unpacker
```

This creates the executable at `build/backends/tpx3-spidr/hermes-tpx3-spidr`.

## Running the Example

```bash
rm -rf data/examples/analysis/timewalk_calibration
pixi run python examples/analysis/timewalk_calibration/run_timewalk_calibration.py
```

This will:

1. Construct a `Workflow` and call `workflow.run_analysis()` to unpack the TPX3
   files in `data/list_tests/`.
2. Cluster the unpacked `pixel_data` with the connected-components + time-gate
   rule and the cluster-selection settings defined in the script.
3. Take each cluster's earliest pixel as the timing reference and accumulate
   the relative delay against `tot_raw`.
4. Fit a linear and an inverse correction, compare them with held-out RMSE,
   residual correlation, and per-time-block parameter stability, and select a
   model.
5. Write the detailed calibration result, the comparison plot, and the small
   correction file.

## Cluster-Selection Settings

The script uses an inclusive 1 microsecond time gate (491,520 canonical ticks),
8-connectivity, cluster sizes 2 through 64, per-pixel ToT at least 1, integrated
ToT from 2 through 65,472, aspect ratio at most 3, and filled fraction at least
0.5. Adjust these in `run_timewalk_calibration.py` for your detector.

## Output Structure

```text
data/examples/analysis/timewalk_calibration/
├── hermes-record.yaml
└── analysis/
    ├── pixelHits/
    │   └── Example_1kHz_5frames_000X-chip-0-part-00000.parquet
    └── logs/
        ├── timewalk-calibration.json              # detailed fit diagnostics
        ├── timewalk-calibration-comparison.png    # linear vs inverse plot
        └── timewalk-calibration-correction.json   # small correction file
```

The correction file (`model`, `parameters`, `high_tot_anchor`, `time_unit`,
`date_created`, `note`) is the file the photon reconstruction clusterer reads.
It matches the format of the checked-in
`calibrations/tpx3/time-walk_example.json`.
