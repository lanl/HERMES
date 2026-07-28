# HERMES TPX3 Unpacker: Multiple Files Example

This example loads a partial user-authored YAML file as a `HermesRecord` and
runs the state-managed HERMES C++ unpacker over several raw TPX3 files with
resource-aware parallel execution.

## Input Files

The example is self-contained. Before unpacking, `run_unpacker_mf.py` copies the
checked-in `tests/data/Example_1kHz_5frames.tpx3` file five times into
`data/multiFileExample/`:

- `Example_1kHz_5frames_0000.tpx3`
- `Example_1kHz_5frames_0001.tpx3`
- `Example_1kHz_5frames_0002.tpx3`
- `Example_1kHz_5frames_0003.tpx3`
- `Example_1kHz_5frames_0004.tpx3`

Each copy contains identical data. The unique filename stems ensure that output
files do not collide. This means a fresh clone needs no extra data setup.

## Building the Unpacker

Before running the example, build the C++ unpacker:

```bash
pixi run build-cpp-unpacker
```

This creates the executable at `build/backends/tpx3-spidr/hermes-tpx3-spidr`.

## Running the Example

Run the checked-in `unpacker_mf_config.yaml`:

```bash
pixi run python examples/analysis/unpacker_multiple_files/run_unpacker_mf.py
```

This will:
1. Create `data/multiFileExample/` and write the five raw TPX3 copies
2. Load and validate `unpacker_mf_config.yaml` as a `HermesRecord`
3. Run the unpacker for each file using the public `run_hermes_analysis()`
   runner with `resource_limit_percent=90`
4. Write Parquet files under shared directories:
   - `pixelHits/`
   - `tdcTriggers/`
   - `globalTimestamps/`
   - `controlPackets/`
   - `unknownPackets/`
5. Write one summary JSON file per input under `analysis/logs/`
6. Save the completed HERMES state to `hermes-record_final.yaml`

To use another YAML file, supply its path as the first argument:

```bash
pixi run python examples/analysis/unpacker_multiple_files/run_unpacker_mf.py \
  /path/to/unpacker_config.yaml
```

### Repeat Run

Running the example again validates every summary and listed Parquet file and
skips all five inputs without launching any unpacker process:

```bash
pixi run python examples/analysis/unpacker_multiple_files/run_unpacker_mf.py
```

### Overwriting Existing Output

By default, files that have already been unpacked are skipped. To re-unpack
every file and overwrite the previously written summary and Parquet files in
place, pass `--overwrite`:

```bash
pixi run python examples/analysis/unpacker_multiple_files/run_unpacker_mf.py \
  --overwrite
```

## YAML fields

The checked-in `unpacker_mf_config.yaml` lists the five raw TPX3 files directly
under `analysis.tpx3_files`. The YAML must contain:

- `measurement_info.measurement_id`
- `measurement_info.run_number`
- `environment`
- `analysis.mode: hermes`
- `analysis.unpacker_program.name`
- `analysis.unpacker_program.executable_path`
- `analysis.analysis_directory`
- at least one entry in `analysis.tpx3_files`

## Output Structure

```text
data/examples/analysis/unpacker_multiple_files/
├── hermes-record_final.yaml
└── analysis/
    ├── pixelHits/
    │   ├── Example_1kHz_5frames_0000-chip-0-part-00000.parquet
    │   ├── Example_1kHz_5frames_0001-chip-0-part-00000.parquet
    │   ├── Example_1kHz_5frames_0002-chip-0-part-00000.parquet
    │   ├── Example_1kHz_5frames_0003-chip-0-part-00000.parquet
    │   └── Example_1kHz_5frames_0004-chip-0-part-00000.parquet
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
        ├── Example_1kHz_5frames_0003-unpacker-summary.json
        └── Example_1kHz_5frames_0004-unpacker-summary.json
```

Each Parquet filename begins with its raw TPX3 filename stem. Each summary JSON
file is the sole detailed result for its raw TPX3 file. The `hermes-record_final.yaml`
file records the complete validated `HermesRecord`, including the overall
unpacking status, start time, finish time, and resource limit percentage, but
does not duplicate per-file packet counts or Parquet row counts.

## Resource Limit

The example sets `resource_limit_percent=90` to demonstrate the default resource
dial. This limits the scheduled unpacker worker count to 90% of the system's
physical CPU cores and available memory.

The resource limit is read from `unpacker_mf_config.yaml` and used for every
run. To change the limit, edit the value in the YAML file before the next run.
