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
- `clustering_settings.yaml` — the `HermesTpx3PhotonClusteringSettings` used to select
  in-cluster pixel pairs for the fit.

By default the example unpacks the sample `tests/data/tpx3/Tantalum_IronPowder.tpx3`,
which has enough multi-pixel photons for a fit. To calibrate your own camera,
edit `tpx3_files` in `timewalk_config.yaml` to point at your TPX3 files.

`pixi install` already builds the C++ unpacker. After changing C++ code, run
`pixi reinstall hermes` so the example uses your changes.

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
└── timewalk-cal/
    └── analysis/
        ├── pixel_hits/
        │   └── Tantalum_IronPowder_chip_0_pixels_00000.parquet
        └── logs/
            ├── timewalk-calibration.json              # detailed fit diagnostics
            ├── timewalk-calibration-comparison.png    # linear vs inverse plot
            └── timewalk-calibration-correction.json   # small correction file
```

For the sample file, the fit uses 92,682 photons (389,591 pixel pairs) and
keeps the linear model.

The correction file (`model`, `parameters`, `high_tot_anchor`, `time_unit`,
`date_created`, `note`) is the file the photon reconstruction clusterer reads.
It matches the format of the checked-in
`calibrations/tpx3/time-walk_example.json`, which HERMES ships as an example
shared curve. New photon-reconstruction runs leave correction off and use the
arithmetic average of the source-hit times.

To use the fitted correction, put these timing fields under
`analysis.photon_reconstruction.clustering_algorithm.settings` in your analysis
config, keeping the other clustering settings:

```yaml
photon_time_estimator: average
timewalk:
  method: calibration
  calibration_file: data/examples/analysis/timewalk_calibration/timewalk-cal/analysis/logs/timewalk-calibration-correction.json
```

That path assumes the default example directories and that HERMES is started
from the repository root. Change it to the correction file you generated, or
use `calibration_file: default` to explicitly select the shipped example curve.
The shared curve is applied to every source hit according to its raw ToT before
calculating photon time. It aligns relative hit times, without determining an
absolute photon-arrival offset. See [photon timing](../../../docs/photon-timing.md)
for other estimators and how to regenerate existing photon and event results.
