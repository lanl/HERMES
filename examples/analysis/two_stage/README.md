# Two-stage TPX3 analysis example

This example uses one HERMES workflow to:

```text
raw TPX3 files
  -> pixel-hit Parquet files
  -> photon-event and optional photon-pixel Parquet files
```

The input YAML remains unchanged. The completed HERMES state is saved
separately after unpacking and photon reconstruction finish.

## Build the C++ programs

Run these commands from the repository root:

```bash
pixi run build-cpp-unpacker
pixi run build-cpp-photon-clusterer
```

## Run the example

Run the checked-in `two_stage_config.yaml`:

```bash
pixi run python examples/analysis/two_stage/run_two_stage.py
```

To use another configuration, supply its path:

```bash
pixi run python examples/analysis/two_stage/run_two_stage.py \
  /path/to/two_stage_config.yaml
```

## Provide raw TPX3 files

List files directly under `analysis.tpx3_files`:

```yaml
tpx3_files:
  - path: data/raw/run_001.tpx3
  - path: data/raw/run_002.tpx3
```

For a longer list, name a text file:

```yaml
tpx3_files:
  file_list: data/raw/raw_tpx3_files.txt
```

Each non-comment line in that text file names one raw TPX3 file. Relative
entries are resolved from the text file's directory. Raw TPX3 filename stems
must be unique because HERMES uses them in Parquet and summary JSON filenames.

## Configure photon reconstruction

The `analysis.photon_reconstruction` section selects the photon clusterer,
pixel input directory, photon output directory, clustering settings, and
time-walk calibration file. Edit those YAML values for the detector data being
analyzed.

The checked-in configuration uses connected components, leading-edge photon
time, and `timewalk_calibration_file: default`. `default` uses the time-walk
calibration that ships with HERMES, so this example runs whether HERMES is
installed or run from a git checkout. The three cases for that field are: omit it
(or `null`) for no time-walk correction, `default` for the shipped calibration,
or a path to your own calibration file. It also enables `save_photon_pixels` so
the source pixels for each reconstructed photon are written.

## Output

The checked-in configuration writes ignored development output under:

```text
data/examples/analysis/two_stage/
├── hermes-record_final.yaml
└── analysis/
    ├── pixel_hits/
    │   └── Example_1kHz_5frames-chip-0-part-00000.parquet
    ├── photons/
    │   ├── Example_1kHz_5frames-chip-0-photon-events-part-00000.parquet
    │   └── Example_1kHz_5frames-chip-0-photon-pixels-part-00000.parquet
    └── logs/
        ├── Example_1kHz_5frames-unpacker-summary.json
        └── Example_1kHz_5frames-reconstruction-summary.json
```

The photon-events file contains each reconstructed photon's position, summed
ToT, leading-edge time, and quality flags. The optional photon-pixels file
contains the source pixels for each photon. The reconstruction summary contains
the settings, photon and rejected-cluster counts, rejection reasons, output
filenames, warnings, errors, and processing times.

Photon Parquet files are written only when the input produces accepted photons.
The checked-in TPX3 file is unpacker test data and is expected to produce zero
accepted photons.

Running the example again validates the existing summary JSON and Parquet
files, skips complete work, and refreshes `hermes-record_final.yaml`.
