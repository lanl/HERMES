# TPX3 SPIDR unpacking example

This example loads a YAML configuration, unpacks one or more raw TPX3 files,
and saves the completed HERMES state separately from the input YAML.

## Build the unpacker

Run this command from the repository root:

```bash
pixi run build-cpp-unpacker
```

## Unpack one file

The default `single_file.yaml` uses the checked-in TPX3 test file:

```bash
pixi run python examples/analysis/unpacking/run_unpacking.py
```

## Unpack multiple files

Run the same script with `multiple_files.yaml`:

```bash
pixi run python examples/analysis/unpacking/run_unpacking.py \
  examples/analysis/unpacking/multiple_files.yaml
```

For a self-contained demonstration, the script copies the checked-in TPX3 file
five times with unique filename stems before loading this configuration.
HERMES can then schedule the five raw files using the configured
`resource_limit_percent`.

## Use another configuration

Pass any HERMES YAML file as the optional argument:

```bash
pixi run python examples/analysis/unpacking/run_unpacking.py \
  /path/to/unpacking.yaml
```

List raw TPX3 files directly:

```yaml
tpx3_files:
  - path: data/raw/run_001.tpx3
  - path: data/raw/run_002.tpx3
```

For a longer list, use a text file:

```yaml
tpx3_files:
  file_list: data/raw/raw_tpx3_files.txt
```

Each non-comment line in that text file names one raw TPX3 file. Relative
entries are resolved from the text file's directory. Raw TPX3 filename stems
must be unique because they are used in the Parquet and summary JSON filenames.

## Output

The checked-in configurations write ignored development output under:

```text
data/examples/analysis/unpacking/
├── single_file/
│   ├── hermes-record_final.yaml
│   └── analysis/
│       ├── pixelHits/
│       └── logs/
└── multiple_files/
    ├── input/
    ├── hermes-record_final.yaml
    └── analysis/
        ├── pixelHits/
        └── logs/
```

The input YAML remains unchanged. Running a configuration again validates the
existing summary JSON and Parquet files, skips complete raw TPX3 files, and
refreshes `hermes-record_final.yaml`.
