# Analysis

`src/hermes/runner/analysis/` contains the Python code that runs analysis. A HERMES
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
src/hermes/runner/analysis/
├── __init__.py
├── run.py                         # selects EMPIR or HERMES from analysis.mode
│
├── hermes/
│   ├── __init__.py
│   ├── run.py                     # orders the HERMES pipeline
│   ├── unpacker.py                # raw TPX3 files to sorted Parquet files
│   └── reconstruction.py          # pixel_data to HERMES photon Parquet files
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

Python code under `src/hermes/runner/analysis/` runs the selected analysis mode. The
C++ and Rust programs that perform HERMES unpacking and reconstruction remain
outside the Python package, under `src/backends/`:

```text
HERMES/
├── Cargo.toml
└── src/
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

## Analysis Entry Point

`Workflow.run_analysis` is the entry point for analysis. It calls the dispatcher
in `src/hermes/runner/analysis/run.py`, which reads the selected Pydantic model
from `StateManager` and sends it to the matching runner:

```python
def run_analysis(state_manager, *, overwrite=False):
    analysis = state_manager.get_state().analysis

    if isinstance(analysis, EmpirAnalysisState):
        return run_empir_analysis(state_manager)
    if isinstance(analysis, HermesTpx3AnalysisState):
        return run_hermes_analysis(state_manager, overwrite=overwrite)

    raise AnalysisModeError("no valid analysis mode is configured")
```

The entry point selects the mode from `analysis.mode` in the saved record, not
from a function argument or CLI option, so the two cannot disagree. HERMES
analysis honors `overwrite`; EMPIR has no overwrite behavior, and its preflight
rejects an output that already exists. EMPIR and HERMES steps are never mixed:
each runner handles one complete mode.

## Timing Comparison

Both runners measure each program with a monotonic clock and write
`elapsed_seconds` to `analysis.jsonl`. This is end-to-end process wall time,
including startup and file I/O, which is the useful measure for the file-based
design.

When comparing EMPIR with HERMES, compare EMPIR pixel-to-photon time with the
combined HERMES raw unpacking and photon-reconstruction time for the same input,
not with the HERMES unpacker alone. EMPIR photon-to-event has no current HERMES
equivalent, and event-to-image time should be reported separately.

## HERMES Analysis

The HERMES pipeline is:

```text
raw TPX3 files
  -> HERMES TPX3 SPIDR unpacker
  -> sorted pixel_data Parquet files
  -> sorted tdc_timestamps Parquet files
  -> sorted heartbeat_packets Parquet files
  -> sorted control_packets Parquet files
  -> optional HERMES pixel-to-photon reconstruction
  -> future HERMES photon-to-event reconstruction
```

`hermes/run.py` should call the functions in `hermes/unpacker.py` for every raw
TPX3 file listed in `HermesTpx3AnalysisState.tpx3_files`. The state contains one
unpacker program, one shared analysis directory, one resource limit percentage,
and one overall unpacking result for the complete list. All inputs use the
shared analysis directory with `pixelHits/`, `tdcTriggers/`,
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

When photon reconstruction is configured, `hermes/run.py` calls
`hermes/reconstruction.py` after every raw TPX3 file has valid unpacker output.
Photon reconstruction is optional. It reads the time-sorted `pixel_data` files
for one raw filename stem from `analysis/pixelHits/`, processes each chip
independently, then writes `photon_events` and optional `photon_pixels` files
under `analysis/photons/`. It does not read TDC files or perform
photon-to-event reconstruction.

The first photon reconstruction program uses connected components with a time
gate. `clustering_algorithm="connected_components"` selects it. The reserved
`"dbscan"` value must be rejected until the separate DBSCAN program is
implemented. Both programs use the same input columns, settings, output
columns, filenames, summary fields, and exit behavior.

HERMES runs photon reconstruction once for each raw filename stem after
validating its pixel-data files. Reconstruction settings are saved in the
HERMES state and passed to the selected program in a temporary JSON file. The
command remains positional with an explicit settings flag:

    <executable> <analysis-directory> <raw-file-stem> --settings <settings-json-file>

The settings JSON file contains the chip-independent clustering settings and
optional time-correction calibration path. The program processes every chip
for the named raw input, derives `pixelHits/`, `photons/`, and `logs/` from the
analysis directory, and records the complete settings in its summary. HERMES
removes the temporary settings file after the process exits.

## Resource-Aware Parallel Unpacking

HERMES runs independent unpacker processes concurrently when multiple raw TPX3
files are present. The analysis state includes a `resource_limit_percent` field
that controls how much of the system's physical CPU cores and available memory
HERMES may schedule for unpacking work. This percentage accepts any integer from
1 through 100, with a default of 90 percent.

The runner calculates the worker count once before starting execution:

```text
resource_fraction = resource_limit_percent / 100
cpu_slots = max(1, floor(physical_cpu_count * resource_fraction))
estimated_worker_memory = max(
    1 GiB,
    16 * largest_pending_raw_file_size,
)
memory_budget = available_memory * resource_fraction
memory_slots = max(1, floor(memory_budget / estimated_worker_memory))
worker_count = min(pending_file_count, cpu_slots, memory_slots)
```

The runner uses `psutil` to read physical CPU count and currently available
memory on supported macOS and Linux platforms. The selected resource percentage,
resource inputs, per-process memory estimates, and calculated worker count are
logged so the scheduling decision can be understood after a run.

The resource limit controls scheduled concurrency rather than enforcing an
operating-system CPU or memory cap. At least one worker is allowed even when its
estimated memory exceeds the selected memory allowance, ensuring forward
progress. The runner logs a warning in that case.

The 1 GiB minimum per-process memory and the 16-times file-size multiplier are
initial safety margins based on the C++ unpacker declaring a 1 GiB sorting
memory budget. The C++ unpacker currently always uses in-memory sorting, and the
declared budget is not enforced as a process memory limit. The 1 GiB minimum and
16-times multiplier cover estimated process memory for decoding, Arrow, Parquet,
and other allocations beyond the sorting budget alone.

When HERMES runs the same analysis again, it validates every raw TPX3 file,
every existing summary, and every existing Parquet file before launching any
unpacker. Files are handled according to these rules:

1. Skip the raw file when its summary is valid and every listed Parquet file
   exists.
2. Run the unpacker when neither its summary nor matching Parquet files exist.
3. Stop when matching Parquet files exist without a valid summary.
4. Stop when the summary exists but is invalid.
5. Mark the overall unpacking result `completed` only after every raw file
   passes validation.

Skipped inputs are logged but never submitted to the worker pool. Files whose
planned action is `run` are submitted to a `ThreadPoolExecutor` with the
calculated worker count. Each worker waits for an independent C++ subprocess.

The runner returns completed files in the original `tpx3_files` order,
regardless of completion order. All HERMES state changes remain on the main
thread. Worker threads may launch and validate one unpacker process but must not
modify HERMES state directly.

If one unpacker fails, the runner cancels work that has not started, allows
already running processes to finish, marks overall unpacking `failed`, and
raises a `HermesTpx3Error`. Valid summaries and Parquet files written by
successful processes are retained. A later run validates and skips those files.

No resume flag is needed.

Photon reconstruction uses the same restart rule. Before launching the
program, HERMES validates the selected executable, the unpacker summary, every
listed `pixel_data` file, and any existing reconstruction summary and photon
files:

1. Skip the raw file when its reconstruction summary is valid and every listed
   `photon_events` file exists.
2. Also require every listed `photon_pixels` file when the saved
   `save_photon_pixels` setting is true.
3. Do not require `photon_pixels` when `save_photon_pixels` is false; the
   summary must then report that no membership files were requested.
4. Run reconstruction when neither its summary nor matching photon files
   exist.
5. Stop when matching photon files exist without a valid summary, when a
   summary is invalid, or when its saved settings differ from the requested
   settings.

The runner applies the overall reconstruction status `running` through
`StateManager` before launching the first reconstruction process. If that
trusted-workflow change is not allowed, it stops before launching the process.
Reconstruction runs sequentially by raw filename stem in the first
implementation. State changes remain on the main thread.

If one reconstruction process fails, the runner marks the overall
reconstruction result `failed`, raises a HERMES reconstruction error, and
keeps valid photon files and summaries from inputs that completed. A later run
validates and skips those inputs. After every input validates, the runner marks
the overall reconstruction result `completed`.

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
domain="analysis", mode="hermes", step="photon_reconstruction"
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
Photon reconstruction saves `photon_events` Parquet files and, when
`save_photon_pixels` is true, `photon_pixels` Parquet files under
`analysis/photons/`. It also saves one input-specific reconstruction summary
JSON file under `analysis/logs/`. Event reconstruction remains undefined.

For EMPIR, the file-based binaries require photon and event files between
commands. The existing `save_photon_files` and `save_event_files` fields control
whether those files remain after downstream success.

Always retain the original raw TPX3 files and the final output requested by the
user. Measure file reading and writing time before adding direct in-memory data
transfer between independently executed programs.
