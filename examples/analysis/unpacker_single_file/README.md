# TPX3 SPIDR unpacker example

This example loads a partial user-authored YAML file as a `HermesRecord`, runs
the state-managed HERMES C++ unpacker, and saves the completed record separately
from the input YAML.

Build the C++ executable:

```bash
pixi run build-cpp-unpacker
```

Run the checked-in `unpacker_config.yaml`:

```bash
pixi run python examples/analysis/unpacker_single_file/run_unpacker.py
```

To use another YAML file, supply its path as the only argument:

```bash
pixi run python examples/analysis/unpacker_single_file/run_unpacker.py \
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
