# HERMES two-stage TPX3 analysis example

This example loads a user-editable YAML file, unpacks every configured raw TPX3
file into Parquet files, and then reconstructs pixel hits into photons. One
`Workflow` runs both stages and saves the completed HERMES record separately
from the input YAML.

The two stages are:

```text
raw TPX3 files
  -> pixel-hit Parquet files
  -> photon-event and optional photon-pixel Parquet files
```

This example stops after photon reconstruction. Photon-to-event reconstruction
is a separate future analysis stage.

## Build the C++ programs

Build the TPX3 SPIDR unpacker and photon clusterer:

```bash
pixi run build-cpp-unpacker
pixi run build-cpp-photon-clusterer
```

These commands create:

```text
build/backends/tpx3-spidr/hermes-tpx3-spidr
build/backends/photon-clusterer/hermes-photon-clusterer
```

## Run the example

Run the checked-in `two_stage_config.yaml`:

```bash
pixi run python examples/analysis/two_stage/run_two_stage.py
```

The default YAML uses `tests/data/Example_1kHz_5frames.tpx3`. To use another
configuration, supply its path:

```bash
pixi run python examples/analysis/two_stage/run_two_stage.py \
  /path/to/two_stage_config.yaml
```

The input YAML remains unchanged. The completed record is written to
`hermes-record_final.yaml` under the configured
`environment.working_dir`.

## Provide raw TPX3 files

List raw TPX3 files directly under `analysis.tpx3_files`:

```yaml
analysis:
  tpx3_files:
    - path: data/raw/run_001.tpx3
    - path: data/raw/run_002.tpx3
    - path: data/raw/run_003.tpx3
```

Every raw TPX3 filename stem must be unique because HERMES carries the stem into
each Parquet filename and summary JSON filename.

For a longer list, name a text file instead:

```yaml
analysis:
  tpx3_files:
    file_list: data/raw/raw_tpx3_files.txt
```

The text file contains one raw TPX3 path per line:

```text
# Paths relative to this text file are allowed.
run_001.tpx3
run_002.tpx3
run_003.tpx3
```

Blank lines and lines whose first non-whitespace character is `#` are ignored.
Relative entries are resolved from the text file's directory. The completed
HERMES record writes the expanded file list so it names every input used for
the run.

## Configure photon reconstruction

`analysis.photon_reconstruction` selects the photon clusterer and its output
directories. For the current HERMES layout:

```yaml
photon_reconstruction:
  pixel_data_directory: data/examples/analysis/two_stage/analysis/pixelHits
  photon_output_directory: data/examples/analysis/two_stage/analysis/photons
```

The pixel-data directory must be `analysis_directory/pixelHits`, and the photon
directory must be `analysis_directory/photons`.

The checked-in settings use connected components with:

- an inclusive 1 microsecond time gate (`491520` canonical ticks)
- 8-connectivity
- cluster sizes from 2 through 64 pixels
- per-pixel raw ToT of at least 1
- integrated raw ToT from 2 through 65,472
- maximum aspect ratio of 3
- minimum filled fraction of 0.5
- leading-edge photon time
- `calibrations/tpx3/time-walk_example.json`
- saved photon-pixel rows

Edit these values in the YAML for the detector data being analyzed.

## Fresh and repeated runs

On a fresh run, `workflow.run_analysis()`:

1. unpacks each raw TPX3 file
2. writes one input-specific unpacker summary
3. reconstructs photons for each raw filename stem
4. writes one input-specific reconstruction summary
5. saves the final HERMES record

On a repeated run, HERMES validates the existing summary JSON and Parquet files.
Inputs with complete valid output are skipped.

## Output

The default YAML writes ignored development output under:

```text
data/examples/analysis/two_stage/
├── hermes-record_final.yaml
└── analysis/
    ├── pixelHits/
    │   └── Example_1kHz_5frames-chip-0-part-00000.parquet
    ├── photons/
    │   ├── Example_1kHz_5frames-chip-0-photon-events-part-00000.parquet
    │   └── Example_1kHz_5frames-chip-0-photon-pixels-part-00000.parquet
    └── logs/
        ├── Example_1kHz_5frames-unpacker-summary.json
        └── Example_1kHz_5frames-reconstruction-summary.json
```

Photon Parquet files are written only when the input produces accepted photons.
The reconstruction summary records the photon count, rejected-cluster count,
settings, output file names, warnings, errors, and processing times.

## Checked-in sample result

The checked-in TPX3 sample is unpacker test data and does not contain
photon-like phosphor clusters. A completed run with zero accepted photons is the
expected result for the default YAML.

To reconstruct real photons, replace `analysis.tpx3_files` with raw TPX3 files
that contain phosphor clusters and adjust the clustering and time-walk settings
for that detector.

