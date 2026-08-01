# TPX3 SPIDR Unpacker Usage

## Building and Installing

### Option 1: Build and Install (Recommended)
Build and install the unpacker to `.pixi/bin/` (automatically added to PATH in pixi environment):

```bash
pixi run install-backends
```

Then run directly:
```bash
pixi run hermes-tpx3-spidr input.tpx3                    # Print summary
pixi run hermes-tpx3-spidr input.tpx3 output_directory   # Write Parquet files
```

### Option 2: Build Only
Build without installing:

```bash
pixi run build-cpp-unpacker
```

Then run from build directory:
```bash
build/backends/tpx3-spidr/hermes-tpx3-spidr input.tpx3
```

## Running the Unpacker

### Show help
```bash
pixi run hermes-tpx3-spidr --help
pixi run hermes-tpx3-spidr --version
```

### Print summary only (no output files)
```bash
pixi run hermes-tpx3-spidr input.tpx3
```

### Write Parquet files and summary.json
```bash
pixi run hermes-tpx3-spidr input.tpx3 output_directory
```

## Output Structure

When an output directory is specified, the unpacker creates:

```
output_directory/
├── summary.json                          # Complete run summary with diagnostics
├── pixel_hits/
│   └── chip_0-00000.parquet             # Sorted pixel hits
├── tdc_triggers/
│   └── tdcs_0-00000.parquet             # Sorted TDC trigger events
├── global_timestamps/
│   └── gs_0-00000.parquet               # Global timestamp anchor points
└── control_packets/
    └── controls_0-00000.parquet         # Control packets (SPIDR and TPX3)
```

## Verifying Time Sorting

Use the provided script to verify all datasets are properly time-sorted:

```bash
pixi run python backends/unpackers/tpx3-spidr/cpp/tests/check_sorting.py output_directory
```

Example output:
```
Checking sorting in: output_directory
======================================================================

Pixel Hits (chip_0-00000.parquet):
  Total rows: 34
  Timestamped rows: 34
  Sorted: ✓ YES
  Min timestamp: 134,869,171,968
  Max timestamp: 1,402,708,055,808
  Time range: 1,267,838,883,840 canonical ticks

TDC Triggers (tdcs_0-00000.parquet):
  Total rows: 21,632
  Timestamped rows: 21,632
  Sorted: ✓ YES
  ...

======================================================================
✓ All datasets are properly time-sorted
```

## Reading Parquet Files

Using Python with pyarrow:

```python
import pyarrow.parquet as pq

# Read a dataset
table = pq.read_table("output_directory/pixel_hits/chip_0-00000.parquet")

# Access columns
chunk_indices = table.column("chunk_index").to_pylist()
timestamps = table.column("timestamp_canonical").to_pylist()

# Convert to pandas (if available)
df = table.to_pandas()
```

## Dataset Schemas

### pixel_hits
- `chunk_index` (uint64): Chunk number in file
- `packet_index` (uint64): Packet number within chunk
- `local_x` (uint16): X coordinate (0-255)
- `local_y` (uint16): Y coordinate (0-255)
- `tot_raw` (uint16): Time-over-threshold raw value
- `timestamp_canonical` (uint64): Canonical timestamp in units of 25ns/12288

### tdc_triggers
- `chunk_index` (uint64): Chunk number in file
- `packet_index` (uint64): Packet number within chunk
- `trigger_type` (uint8): 0=TDC1_rising, 1=TDC1_falling, 2=TDC2_rising, 3=TDC2_falling
- `timestamp_canonical` (uint64): Canonical timestamp

### global_timestamps
- `chunk_index` (uint64): Chunk number in file (from high packet)
- `packet_index` (uint64): Packet number within chunk (from high packet)
- `timestamp_canonical` (uint64): 48-bit global timestamp in canonical units

### control_packets
All control packets (SPIDR and TPX3) with nullable fields depending on type:
- `chunk_index`, `packet_index` (uint64)
- `source` (uint8): 0=SPIDR, 1=TPX3
- `control_type` (uint16): Type code
- `packet_id`, `subtype`, `packet_count`, `reserved_high`, `reserved_low` (nullable)
- `control_value_raw`, `control_payload_raw` (nullable)
- `timestamp_canonical` (uint64, nullable): Only present for timestamped controls

## Performance Timing

The unpacker includes detailed timing metrics for each processing stage:

```
Timing:
  Unpacking:         0.000858 s  (decoding raw packets)
  Epoch assignment:  0.000333 s  (timestamp unwrapping)
  Sorting:           0.000000 s  (time-ordering datasets)
  Conversion:        0.000110 s  (converting to output rows)
  Parquet writing:   0.003333 s  (writing output files)
  Total:             0.004737 s
```

Timing data is:
- Printed to console when writing Parquet output
- Included in `summary.json` under `timing_diagnostics`
- Useful for identifying optimization opportunities

## Running Tests

```bash
pixi run test-cpp-unpacker
```

All 6 test suites should pass.

## Example with Test Data

```bash
# Install backends first
pixi run install-backends

# Process example file
pixi run hermes-tpx3-spidr \
    .agent/resources/Example_1kHz_5frames.tpx3 \
    .scratch/test_output

# Verify sorting
pixi run python backends/unpackers/tpx3-spidr/cpp/tests/check_sorting.py .scratch/test_output

# View summary
cat .scratch/test_output/summary.json | python3 -m json.tool
```

## Notes

- All timestamps are in **canonical units**: 25 ns / 12288 ≈ 2.03 picoseconds per tick
- Data is sorted by `timestamp_canonical` (with `source_packet_order` as tiebreaker)
- Multi-chip support exists in the code but currently processes chip 0 only
- Files are split into parts when row count exceeds 1,000,000 (configurable)
