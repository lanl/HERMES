# HERMES Data Directory

This directory is for organizing experimental data through acquisition and analysis workflows. All contents except this README are gitignored.

## Directory Structure

Create working directories here using symlinks to your actual data storage locations:

```
data/
├── README.md                    # This file (tracked)
├── experiment_YYYY_MM_DD/       # Example working directory (not tracked)
|   ├── config.yaml              # Configuration for the experiment
│   ├── rawtpx3/                 # Raw TPX3 files
│   │   ├── run_001.tpx3
│   │   ├── run_002.tpx3
│   │   └── ...                
│   ├── logs/                    # logged information from the acquisition system
│   └── analysis/                # Processed results
|       ├── summary.json
|       ├── pixel_hits/
|       │   ├── chip_0-00000.parquet
|       │   └── chip_0-00001.parquet
|       ├── tdc_triggers/
|       │   ├── tdcs_0-00000.parquet
|       │   └── ...
|       ├── global_timestamps/
|       │   ├── gs_0-00000.parquet
|       │   └── ...
|       ├── control_packets/
|       │   ├── controls_0-00000.parquet
|       │   └── ...
|       ├── photons/
|       │   ├── photons_0-00000.parquet 
|       │   └── ...
|       ├── events/
|       │   ├── events_0-00000.parquet 
|       │   └── ...
|       └── unknown_packets/
|           ├── unknown_0-00000.parquet
|           └── ...
|
└── experiment_[PROPOSAL_#]/     # Another working directory (not tracked)
    ├── acquisition/
    └── analysis/
```

## Recommended Workflow

### 1. Create a Working Directory

Either create a local directory:
```bash
mkdir -p data/my_experiment/{acquisition,analysis}
```

Or symlink to external storage:
```bash
ln -s /path/to/your/data/storage data/my_experiment
```

### 2. Organize Acquisition Data

Store raw detector data in the `acquisition/` subdirectory:
- Raw TPX3 files (`.tpx3`)
- Configuration files
- Run metadata (YAML, JSON)
- Lab notes

```bash
# Example: Copy data from acquisition system
cp /mnt/detector/run_*.tpx3 data/my_experiment/acquisition/
```

### 3. Process Data

Run unpacking and analysis, storing results in `analysis/`:

```bash
# Unpack TPX3 data
pixi run hermes-tpx3-spidr \
    data/my_experiment/acquisition/run_001.tpx3 \
    data/my_experiment/analysis/run_001_unpacked

# Verify sorting
pixi run python backends/unpackers/tpx3-spidr/cpp/tests/check_sorting.py \
    data/my_experiment/analysis/run_001_unpacked
```

### 4. Analysis Structure

Typical analysis directory layout:
```
analysis/
├── run_001_unpacked/           # Unpacked detector data
│   ├── pixel_hits/             # Parquet files
│   ├── tdc_triggers/
│   ├── global_timestamps/
│   ├── control_packets/
│   └── summary.json            # Processing diagnostics
├── run_001_calibrated/         # After calibration
├── run_001_reconstructed/      # After photon reconstruction
└── combined_analysis/          # Multi-run analysis
```

## Using Symlinks

### Why Symlinks?

Symlinks allow you to:
- Keep large datasets on high-capacity storage
- Work with data across multiple filesystems
- Share data between projects
- Avoid duplicating large files

### Creating Symlinks

**Link an entire experiment directory:**
```bash
ln -s /mnt/large_storage/experiment_2024 data/experiment_2024
```

**Link just the acquisition data:**
```bash
mkdir -p data/experiment_2024
ln -s /mnt/large_storage/raw_data data/experiment_2024/acquisition
mkdir data/experiment_2024/analysis
```

**Verify symlinks:**
```bash
ls -l data/
# Look for entries like: experiment_2024 -> /mnt/large_storage/experiment_2024
```

## Best Practices

### Naming Conventions

**Experiment directories:**
- Use descriptive names: `photodetection_calibration_2024_07_21`
- Include dates: `YYYY_MM_DD` or ISO format `YYYY-MM-DD`
- Use underscores, not spaces

**Run files:**
- Sequential numbering: `run_001.tpx3`, `run_002.tpx3`
- Include conditions: `run_001_dark.tpx3`, `run_002_1kHz.tpx3`
- Keep original timestamps if available

### Metadata

Always include metadata files in `acquisition/`:

**metadata.yaml example:**
```yaml
experiment:
  name: "TPX3 calibration run"
  date: "2024-07-21"
  operator: "A. Long"
  
detector:
  type: "TPX3 SPIDR"
  chip_id: "W0001_H01"
  bias_voltage: 150  # V
  
runs:
  - file: "run_001.tpx3"
    description: "Dark current baseline"
    duration: 300  # seconds
    
  - file: "run_002.tpx3"
    description: "1 kHz trigger test"
    trigger_rate: 1000  # Hz
    duration: 60
```

### Data Lifecycle

1. **Acquisition** → Store in `acquisition/` as soon as data is collected
2. **Backup** → Backup raw data before processing (symlink doesn't backup!)
3. **Process** → Unpack and analyze, results in `analysis/`
4. **Archive** → After analysis is complete:
   - Keep raw data archived
   - Keep final analysis results
   - Intermediate files can be regenerated

### Storage Tips

**For large datasets:**
- Use external drives: `/Volumes/DataDrive/hermes_data/`
- Use network storage: `/mnt/lab_nas/username/`
- Use compute cluster: `/scratch/username/hermes/`

**Disk space management:**
```bash
# Check space usage
du -sh data/*/

# Find large files
find data/ -type f -size +1G

# Clean up intermediate files (keep acquisition/ and final analysis/)
rm -rf data/experiment_2024/analysis/*_temp/
```

## Integration with HERMES

The `data/` directory integrates with HERMES workflows:

**Python API (future):**
```python
from hermes.acquisition import load_tpx3_run
from hermes.analysis import unpack_and_analyze

# Load data
run = load_tpx3_run("data/my_experiment/acquisition/run_001.tpx3")

# Process
results = unpack_and_analyze(run, output_dir="data/my_experiment/analysis/run_001")
```

**CLI workflows:**
```bash
# Process all runs in an experiment
for tpx3 in data/my_experiment/acquisition/*.tpx3; do
    basename=$(basename "$tpx3" .tpx3)
    pixi run hermes-tpx3-spidr "$tpx3" "data/my_experiment/analysis/${basename}"
done
```

## Example: Complete Workflow

```bash
# 1. Create experiment directory
mkdir -p data/photodetection_test_2024/{acquisition,analysis}

# 2. Copy or symlink acquisition data
cp /mnt/detector/run_*.tpx3 data/photodetection_test_2024/acquisition/

# 3. Create metadata
cat > data/photodetection_test_2024/acquisition/metadata.yaml << EOF
experiment:
  name: "Photodetection test"
  date: "2024-07-21"
runs:
  - file: "run_001.tpx3"
    description: "Initial test run"
EOF

# 4. Process data
pixi run hermes-tpx3-spidr \
    data/photodetection_test_2024/acquisition/run_001.tpx3 \
    data/photodetection_test_2024/analysis/run_001_unpacked

# 5. Verify results
pixi run python backends/unpackers/tpx3-spidr/cpp/tests/check_sorting.py \
    data/photodetection_test_2024/analysis/run_001_unpacked

# 6. View timing
cat data/photodetection_test_2024/analysis/run_001_unpacked/summary.json | \
    python3 -m json.tool | grep -A 8 timing_diagnostics
```

## Troubleshooting

**Symlink doesn't work:**
- Check permissions: `ls -l /path/to/target`
- Verify target exists: `test -d /path/to/target && echo "exists"`
- Use absolute paths for symlinks across filesystems

**Out of disk space:**
- Check if you're using symlinks correctly (shouldn't copy data)
- Clean up intermediate analysis files
- Move old experiments to archive storage

**File not found errors:**
- Broken symlink: `ls -L data/experiment` (follows symlinks)
- Fix: `rm data/broken_link && ln -s /correct/path data/experiment`

## Security Notes

- **Never commit data files to git** (gitignore handles this)
- **Protect sensitive data** - use appropriate file permissions
- **Backup raw data** - symlinks don't backup the original files
- **Document data provenance** - always include metadata

## Questions?

See the main HERMES documentation or backend-specific READMEs:
- TPX3 unpacker: `backends/unpackers/tpx3-spidr/README.md`
- Build instructions: Root `README.md`
