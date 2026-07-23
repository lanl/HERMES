# HERMES TPX3 Unpacker: Multiple Files Example

This example demonstrates unpacking multiple raw TPX3 files using the HERMES
unpacker with resource-aware parallel execution.

## Input Files

The example unpacks all TPX3 files found in `data/list_tests/`:

- `Example_1kHz_5frames_0000.tpx3`
- `Example_1kHz_5frames_0001.tpx3`
- `Example_1kHz_5frames_0002.tpx3`
- `Example_1kHz_5frames_0003.tpx3`

Each file is 348,128 bytes and contains identical data. The unique filename
stems ensure that output files do not collide.

## Building the Unpacker

Before running the example, build the C++ unpacker:

```bash
pixi run build-cpp-unpacker
```

This creates the executable at `build/backends/tpx3-spidr/hermes-tpx3-spidr`.

## Running the Example

### Fresh Run

To unpack all four files with a clean output directory:

```bash
rm -rf data/examples/analysis/unpacker_multiple_files/analysis
pixi run python examples/analysis/unpacker_multiple_files/run_unpacker_mf.py
```

This will:
1. Find and sort all TPX3 files in `data/list_tests/`
2. Create a HERMES analysis state with `resource_limit_percent=90`
3. Run the unpacker for each file using the public `run_hermes_analysis()` runner
4. Write Parquet files under shared directories:
   - `pixelHits/`
   - `tdcTriggers/`
   - `globalTimestamps/`
   - `controlPackets/`
   - `unknownPackets/`
5. Write one summary JSON file per input under `analysis/logs/`
6. Save the final HERMES state to `hermes-record.yaml`

### Repeat Run

To verify that existing output is skipped:

```bash
pixi run python examples/analysis/unpacker_multiple_files/run_unpacker_mf.py
```

The example validates every summary and listed Parquet file and skips all four
inputs without launching any unpacker process.

## Output Structure

```text
data/examples/analysis/unpacker_multiple_files/
├── hermes-record.yaml
└── analysis/
    ├── pixelHits/
    │   ├── Example_1kHz_5frames_0000-chip-0-part-00000.parquet
    │   ├── Example_1kHz_5frames_0001-chip-0-part-00000.parquet
    │   ├── Example_1kHz_5frames_0002-chip-0-part-00000.parquet
    │   └── Example_1kHz_5frames_0003-chip-0-part-00000.parquet
    ├── tdcTriggers/
    │   └── ...
    ├── globalTimestamps/
    │   └── ...
    ├── controlPackets/
    │   └── ...
    ├── unknownPackets/
    │   └── ...
    └── logs/
        ├── Example_1kHz_5frames_0000-unpacker-summary.json
        ├── Example_1kHz_5frames_0001-unpacker-summary.json
        ├── Example_1kHz_5frames_0002-unpacker-summary.json
        └── Example_1kHz_5frames_0003-unpacker-summary.json
```

Each Parquet filename begins with its raw TPX3 filename stem. Each summary JSON
file is the sole detailed result for its raw TPX3 file. The HERMES state file
records the overall unpacking status, start time, finish time, and resource
limit percentage, but does not duplicate per-file packet counts or Parquet row
counts.

## Resource Limit

The example sets `resource_limit_percent=90` to demonstrate the default resource
dial. This limits the scheduled unpacker worker count to 90% of the system's
physical CPU cores and available memory.

The resource limit is saved in the HERMES YAML file and used for every run. To
change the limit, modify the value in `run_unpacker_mf.py` or edit the saved
`hermes-record.yaml` file before the next run.
