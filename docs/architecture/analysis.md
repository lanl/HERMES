# Analysis

`src/hermes/analysis/` contains the Python code that runs analysis. A HERMES
state file selects one complete analysis mode:

```yaml
analysis:
  mode: hermes
```

or:

```yaml
analysis:
  mode: empir
```

EMPIR and HERMES must not be mixed between analysis steps. An EMPIR analysis
uses the EMPIR binaries for the complete pipeline. A HERMES analysis uses the
HERMES unpacking and reconstruction programs for the complete pipeline.

Analysis must also work without acquisition state. For analysis-only use, the
selected analysis model contains the raw TPX3 files, executable paths, settings,
and output paths required by that mode.

## Python Directory Structure

Keep EMPIR and HERMES execution code in separate directories:

```text
src/hermes/analysis/
├── __init__.py
├── run.py                         # selects EMPIR or HERMES from analysis.mode
│
├── hermes/
│   ├── __init__.py
│   ├── run.py                     # orders the HERMES pipeline
│   ├── unpacker.py                # raw TPX3 files to sorted Parquet files
│   └── reconstruction.py          # future HERMES photon and event reconstruction
│
└── empir/
    ├── __init__.py
    ├── run.py                     # orders the EMPIR pipeline
    ├── pixel_to_photon.py         # runs empir_pixel2photon_tpx3spidr
    ├── photon_to_event.py         # runs empir_photon2event
    └── event_to_image.py          # runs empir_event2image
```

Do not add a base runner class, program registry, plugin system, or generic
analysis-step model. The two modes use different commands, settings, and files,
so their execution code and Pydantic models should remain explicit.

The Pydantic models remain under:

```text
src/hermes/state/models/analysis/
├── hermes_tpx3_spidr.py
└── empir.py
```

## Analysis Backend Structure

Python code under `src/hermes/analysis/` runs the selected analysis mode. The
C++ and Rust programs that perform HERMES unpacking and reconstruction remain
outside the Python package under `backends/`:

```text
HERMES/
├── Cargo.toml
└── backends/
    ├── unpackers/
    │   └── tpx3-spidr/
    │       ├── cpp/
    │       └── rust/
    └── reconstruction/
        ├── photons/
        │   ├── cpp/
        │   └── rust/
        └── events/
            ├── cpp/
            └── rust/
```

C++ and Rust versions of the same HERMES analysis step should live beside each
other. Add a backend directory only when its first working implementation is
being developed.

The top-level `Cargo.toml` should include each Rust backend that belongs to the
Cargo workspace. Each C++ backend should contain its own CMake project.

HERMES runs the executable path saved in the selected HERMES analysis model.
The executable may be built from this repository or installed elsewhere on the
user's computer. Python should not need different execution code for C++ and
Rust implementations of the same HERMES step.

C++ and Rust implementations of the same HERMES step must accept the same
required inputs and write the same files, columns, units, warnings, errors, and
exit codes. This allows a user to change the implementation without changing
the rest of the HERMES pipeline.

Backend selection does not allow EMPIR and HERMES to be mixed. A HERMES
analysis may select a C++ or Rust HERMES implementation for a defined HERMES
step, but every step remains part of `mode="hermes"`. An EMPIR analysis uses the
EMPIR binaries and remains `mode="empir"`.

## Program-Agnostic Entry Point

`src/hermes/analysis/run.py` should provide one small entry point. It reads the
selected Pydantic model from `StateManager` and calls exactly one mode-specific
pipeline:

```python
def run_analysis(state_manager: StateManager) -> HermesRecord:
    analysis = state_manager.get_state().analysis

    if isinstance(analysis, HermesTpx3AnalysisState):
        run_hermes_analysis(state_manager)
    elif isinstance(analysis, EmpirAnalysisState):
        run_empir_analysis(state_manager)
    else:
        raise AnalysisError("analysis configuration is missing")

    return state_manager.get_state()
```

The entry point should not accept a second mode argument. This prevents a
function argument or CLI option from disagreeing with `analysis.mode` in the
HERMES state file.

The entry point only selects the pipeline. Each mode-specific `run.py` owns the
order of its commands, checks its files, logs its progress, and applies its
results through `StateManager`.

## HERMES Analysis

The HERMES pipeline is:

```text
raw TPX3 files
  -> HERMES TPX3 SPIDR unpacker
  -> sorted pixel_hits Parquet files
  -> sorted tdc_triggers Parquet files
  -> sorted global_timestamps Parquet files
  -> sorted control_packets Parquet files
  -> future HERMES pixel-to-photon reconstruction
  -> future HERMES photon-to-event reconstruction
```

`hermes/run.py` should call the functions in `hermes/unpacker.py` for every raw
TPX3 file listed in `HermesTpx3AnalysisState.tpx3_files`. The state contains one
unpacker program, one shared analysis directory, and one overall unpacking
result for the complete list. All inputs use the shared analysis directory with
`pixelHits/`, `tdcTriggers/`,
`globalTimestamps/`, `controlPackets/`, `unknownPackets/`, and `logs/`
directories. The unpacker carries the raw TPX3 filename stem into every
Parquet filename and its summary JSON filename. The runner rejects duplicate
raw filename stems before launching any unpacker.

For example, `DT_2p0V_000000.tpx3` produces filenames beginning with
`DT_2p0V_000000-`. A Parquet part uses the full form
`DT_2p0V_000000-chip-0-part-00000.parquet`. Its unpacker summary is
`logs/DT_2p0V_000000-unpacker-summary.json`.

Each input-specific summary JSON file is the sole saved detailed result for
that raw TPX3 file. Packet counts, Parquet row counts and filenames, warnings,
errors, timestamp diagnostics, sorting diagnostics, and processing times stay
in that file. They are not copied into the HERMES YAML file.

When HERMES runs the same analysis again, it handles each raw TPX3 file in list
order:

1. Skip the raw file when its summary is valid and every listed Parquet file
   exists.
2. Run the unpacker when neither its summary nor matching Parquet files exist.
3. Stop when matching Parquet files exist without a valid summary.
4. Stop when the summary exists but is invalid.
5. Mark the overall unpacking result `completed` only after every raw file
   passes validation.

No resume flag is needed.

Only unpacking is currently defined. `hermes/reconstruction.py` should remain
empty until the HERMES photon and event settings, Arrow tables, saved Parquet
files, timing rules, and result fields are defined in the architecture.

HERMES programs may be implemented in C++ or Rust, but they must read and write
the HERMES files and columns defined for that analysis step. Choosing a C++ or
Rust HERMES implementation does not change `analysis.mode`; it remains
`mode="hermes"`.

## EMPIR Analysis

The EMPIR pipeline is:

```text
raw TPX3 files
  -> empir_pixel2photon_tpx3spidr
  -> EMPIR photon files
  -> empir_photon2event
  -> EMPIR event files
  -> empir_event2image
  -> TIFF image
```

`empir/run.py` should call these files in order:

1. `empir/pixel_to_photon.py`
2. `empir/photon_to_event.py`
3. `empir/event_to_image.py`

Call the EMPIR binaries directly. Do not call the EMPIR shell scripts.

The photon file must exist long enough for `empir_photon2event` to read it, and
the event file must exist long enough for `empir_event2image` to read it.
`save_photon_files` and `save_event_files` determine whether those intermediate
files remain after the next EMPIR step completes successfully. If a later step
fails, keep the intermediate files so the user can diagnose the failure.

## State Changes

Analysis code must not directly modify `HermesRecord`. Every durable change
must go through `StateManager`.

Each mode-specific pipeline should:

- read its executable paths, inputs, settings, and requested output paths from
  its selected analysis model
- apply `planned`, `running`, `completed`, and `failed` status through
  `StateManager`
- record the overall step start and finish times in the corresponding Pydantic
  result model
- keep detailed results in the program-specific files defined by the selected
  analysis mode
- stop before launching an executable when a required state change has not been
  approved
- return completed or failed state through `StateManager`

The calling workflow saves `StateManager.get_state()` as the HERMES YAML file
with the existing state I/O.

## Logging

Use Loguru with `domain="analysis"`. Every event should also include the selected
mode and the concrete step name.

Examples:

```text
domain="analysis", mode="hermes", step="tpx3_spidr_unpacking"
domain="analysis", mode="empir", step="pixel_to_photon"
domain="analysis", mode="empir", step="photon_to_event"
domain="analysis", mode="empir", step="event_to_image"
```

Log executable paths, input files, output paths, command arguments, exit codes,
elapsed times, counts, warnings, errors, and bounded stdout and stderr excerpts.
Do not put full stdout, full stderr, raw TPX3 bytes, Arrow arrays, or Parquet rows
in operational logs or the HERMES YAML file.

## Saved Files Between Steps

HERMES and EMPIR have different intermediate files and retention rules. Do not
force both modes into one generic setting.

For HERMES, the unpacker saves inspectable Parquet files in shared category
directories and one input-specific summary JSON file under `analysis/logs/`.
Later HERMES reconstruction work will define whether photon and event Arrow
tables are kept only in memory or also written as Parquet files.

For EMPIR, the file-based binaries require photon and event files between
commands. The existing `save_photon_files` and `save_event_files` fields control
whether those files remain after downstream success.

Always retain the original raw TPX3 files and the final output requested by the
user. Measure file reading and writing time before adding direct in-memory data
transfer between independently executed programs.
