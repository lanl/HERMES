# TPX3 SPIDR unpacker example

This example loads a partial user-authored YAML file as a `HermesRecord`,
constructs a `Workflow`, and calls `workflow.run_analysis()` to run the HERMES
C++ unpacker. It then saves `workflow.record` separately from the input YAML.
The caller does not construct or configure a `StateManager`.

Build the C++ executable:

```bash
pixi run build-cpp-unpacker
```

Run the checked-in `unpacker_config.yaml`:

```bash
pixi run python examples/analysis/unpacking/unpacker_single_file/run_unpacker.py
```

To use another YAML file, supply its path as the only argument:

```bash
pixi run python examples/analysis/unpacking/unpacker_single_file/run_unpacker.py \
  /path/to/unpacker_config.yaml
```

## YAML fields

The YAML must contain:

- `measurement_info.measurement_id`
- `measurement_info.run_number`
- `environment`
- `analysis.mode: hermes`
- `analysis.unpacker_program.name`
- `analysis.unpacker_program.executable_path`
- `analysis.analysis_directory`
- at least one entry in `analysis.tpx3_files`

The checked-in YAML omits values that already have Pydantic defaults. These
include:

- `acquisition: null`
- `analysis.resource_limit_percent: 90`
- unpacking status `planned`
- optional photon reconstruction
- optional unpacker version
- optional raw TPX3 file information

## Multiple raw TPX3 files

List the files directly:

```yaml
tpx3_files:
  - path: data/raw/run_001.tpx3
  - path: data/raw/run_002.tpx3
  - path: data/raw/run_003.tpx3
```

Or name a text file:

```yaml
tpx3_files:
  file_list: data/raw/raw_tpx3_files.txt
```

The text file contains one path per line:

```text
# Relative to this text file's directory.
run_001.tpx3
run_002.tpx3
run_003.tpx3
```

Blank lines and lines beginning with `#` are ignored. A relative path inside
the text file is resolved from the text file's directory. The text file must
exist and contain at least one raw TPX3 file path. Raw TPX3 filename stems must
remain unique.

The final `hermes-record_final.yaml` always contains the expanded
`tpx3_files` list so it records the exact raw TPX3 files used. The command
prints every configured raw TPX3 path and reports how many were unpacked or
skipped.

Unknown fields, missing required fields, invalid values, malformed YAML, and a
missing analysis mode stop the example before analysis starts. A valid
non-HERMES analysis record is rejected by the HERMES runner with an ERROR-level
Loguru event.

## Output

The default YAML writes persistent development output outside the tracked
source tree:

```text
data/examples/analysis/unpacker/
├── hermes-record_final.yaml
└── analysis/
    ├── pixelHits/
    ├── tdcTriggers/
    ├── globalTimestamps/
    ├── controlPackets/
    ├── unknownPackets/
    └── logs/
        └── Example_1kHz_5frames-unpacker-summary.json
```

The input YAML remains unchanged. The final `hermes-record_final.yaml` contains
the complete validated `HermesRecord`, including Pydantic defaults and the
completed unpacking result.

Running the example again validates the existing summary and Parquet files,
skips the valid raw TPX3 file, and refreshes the final HERMES YAML file.
