# HERMES TPX3 Time-Walk Calibration Example

This example unpacks raw TPX3 files and then fits a time-walk correction from
the resulting `pixel_data` using the in-cluster relative method. It writes a
detailed calibration-result JSON, a comparison plot, and the small correction
file that the photon reconstruction clusterer consumes.

The example loads the initial `HermesRecord` from `timewalk_config.yaml`, builds
one `Workflow`, calls `workflow.run_analysis()`, and saves the completed
`workflow.record`. The cluster-selection settings for the fit are loaded from
`clustering_settings.yaml`. The script performs no manual error checks: YAML
loading, Pydantic model validation, the `Workflow`, and `calibrate_timewalk`
report their own errors.

## Configuration Files

- `timewalk_config.yaml` — the `HermesRecord` describing the unpacking stage
  (unpacker program, analysis directory, and raw TPX3 inputs).
- `clustering_settings.yaml` — the `Tpx3PhotonClusteringSettings` used to select
  in-cluster pixel pairs for the fit.

By default the example unpacks `tests/data/Example_1kHz_5frames.tpx3`.

> **Substitute your own data.** The bundled fixture does **not** contain
> photon-like phosphor blobs, so it yields no in-cluster pixel pairs and
> `calibrate_timewalk` raises a `ValueError`. To produce a real calibration,
> edit `tpx3_files` in `timewalk_config.yaml` to point at TPX3 files that
> contain phosphor clusters.

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

Pass an alternate configuration YAML as the only argument:

```bash
pixi run python examples/analysis/timewalk_calibration/run_timewalk_calibration.py my_config.yaml
```

This will:

1. Load `timewalk_config.yaml`, construct a `Workflow`, and call
   `workflow.run_analysis()` to unpack the configured TPX3 files.
2. Load `clustering_settings.yaml` and cluster the unpacked `pixel_data` with the
   connected-components + time-gate rule.
3. Take each cluster's earliest pixel as the timing reference and accumulate the
   relative delay against `tot_raw`.
4. Fit a linear and an inverse correction, compare them with held-out RMSE,
   residual correlation, and per-time-block parameter stability, and select a
   model.
5. Write the detailed calibration result, the comparison plot, and the small
   correction file.

## Output Structure

```text
data/examples/analysis/timewalk_calibration/
├── hermes-record_final.yaml
└── analysis/
    ├── pixelHits/
    │   └── Example_1kHz_5frames-chip-0-part-00000.parquet
    └── logs/
        ├── timewalk-calibration.json              # detailed fit diagnostics
        ├── timewalk-calibration-comparison.png    # linear vs inverse plot
        └── timewalk-calibration-correction.json   # small correction file
```

The correction file (`model`, `parameters`, `high_tot_anchor`, `time_unit`,
`date_created`, `note`) is the file the photon reconstruction clusterer reads.
It matches the format of the checked-in
`calibrations/tpx3/time-walk_example.json`.
