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
├── executables.py                 # resolves a configured program name or path
│
├── hermes/
│   ├── __init__.py
│   ├── run.py                     # orders the HERMES pipeline
│   ├── unpacker.py                # raw TPX3 files to sorted Parquet files
│   ├── photon_reconstruction.py   # pixel_data to HERMES photon Parquet files
│   ├── event_reconstruction.py    # photon files to HERMES event Parquet files
│   └── timewalk_calibration.py    # standalone time-walk calibration fit
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
analysis honors `overwrite`; EMPIR has no overwrite flag and instead skips a
step whose requested output file already exists, recording that step as
`skipped`. EMPIR and HERMES steps are never mixed: each runner handles one
complete mode.

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
  -> optional HERMES photon-to-event reconstruction
```

`hermes/run.py` should call the functions in `hermes/unpacker.py` for every raw
TPX3 file listed in `HermesTpx3AnalysisState.tpx3_files`. The state contains one
unpacker program, one shared analysis directory, one resource limit percentage,
and one overall unpacking result for the complete list. All inputs use the
shared analysis directory with `pixel_hits/`, `tdc_triggers/`,
`global_timestamps/`, `control_packets/`, `unrecognized_packets/`, and `logs/`
directories. The unpacker carries the raw TPX3 filename stem into every
Parquet filename and its summary JSON filename. The runner rejects duplicate
raw filename stems before launching any unpacker.

For example, `DT_2p0V_000000.tpx3` produces filenames beginning with
`DT_2p0V_000000_`. A pixel Parquet part uses the full form
`pixel_hits/DT_2p0V_000000_chip_0_pixels_00000.parquet`. Its unpacker summary is
`logs/unpacking/DT_2p0V_000000_unpacker_summary.json`.

Each input-specific summary JSON file is the sole saved detailed result for
that raw TPX3 file. Packet counts, Parquet row counts and filenames, warnings,
errors, timestamp diagnostics, sorting diagnostics, and processing times stay
in that file. They are not copied into the HERMES YAML file.

When photon reconstruction is configured, `hermes/run.py` calls
`hermes/photon_reconstruction.py` after every raw TPX3 file has valid unpacker
output. Photon reconstruction is optional. It reads one time-sorted pixel-data
file from `analysis/pixel_hits/` (each file holds one chip's hits), clusters
those chip-local pixels, then writes `photon_events` and optional `photon_pixels`
files under `analysis/photons/`. It does not read TDC files or perform
photon-to-event reconstruction.

Clustering stays chip-local, but the photon `x`/`y` are written in a single
shared sensor coordinate frame selected by `detector_layout` (`single_chip` or
`quad`, defaulting to `quad`). The runner passes the layout in the settings JSON.
This shared frame lets the later event stage group light that lands on more than
one chip. See `photon_reconstruction.md` for the per-chip map.

The first photon reconstruction program uses connected components with a time
gate. `clustering_algorithm="connected_components"` selects it. The reserved
`"dbscan"` value must be rejected until the separate DBSCAN program is
implemented. Both programs use the same input columns, settings, output
columns, filenames, summary fields, and exit behavior.

HERMES runs photon reconstruction once for each pixel-data file after validating
it. Reconstruction settings are saved in the HERMES state and passed to the
selected program in a temporary JSON file. The command names the input pixel
file and the analysis directory with explicit flags:

    <executable> --input <pixel-file> --output <analysis-directory> --measurement-id <id> --run <run> --settings <settings-json-file> [--overwrite]

The settings JSON file contains the chip-independent clustering settings, the
`detector_layout`, and an optional time-correction calibration path. The program
reads the named pixel file, derives its output filenames and the `photons/` and
`logs/` directories from the analysis directory, and records the complete
settings in its summary. HERMES removes the temporary settings file after the
process exits.

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
every existing summary, and confirms that every Parquet file its summary lists
exists before launching any unpacker. It does not open those Parquet files: the
summary is written only after every Parquet file closes, so its presence already
means the outputs are complete, and its row counts are trusted rather than
re-read. Reading and validating one file's summary is independent of every other
file's, so this scan runs across the same worker pool used for unpacking. Files
are handled according to these rules:

1. Skip the raw file when its summary is valid and every listed Parquet file
   exists.
2. Run the unpacker when neither its summary nor matching Parquet files exist.
3. Stop when matching Parquet files exist without a valid summary.
4. Stop when the summary exists but is invalid.
5. Record each raw file's result as it finishes; a file is `completed` only
   after its outputs pass validation, `skipped` when reused, or `failed` when
   its unpacker did not finish successfully.

Skipped inputs are logged but never submitted to the worker pool. Files whose
planned action is `run` are grouped into small chunks, and the chunks are
submitted to a `ThreadPoolExecutor` with the calculated worker count. Each worker
waits for one C++ subprocess that unpacks its chunk's files in sequence. A run
has tens of thousands of tiny raw files, and starting a fresh process for each
one is dominated by the fixed cost of loading the Arrow/Parquet libraries;
unpacking a chunk of files in one process pays that cost once for the whole
chunk. Reconstruction still runs one process per file — its inputs are larger, so
the fixed startup cost is a small fraction of each file's work and grouping would
not help. The chunk size is capped so a subprocess that dies partway loses only
that chunk's not-yet-finished files, which a later resume re-runs.

Each subprocess runs with its internal thread pools limited to a single thread.
Left unconstrained, the Arrow/Parquet thread pool inside each unpacker process
sizes itself to the whole machine, so many concurrent workers would spawn far
more runnable threads than cores and oversubscribe the CPU. Pinning them to one
thread keeps roughly one worker per core, which is the assumption behind the
worker-count formula.

The runner returns completed files in the original `tpx3_files` order,
regardless of completion order. All HERMES state changes remain on the main
thread. Worker threads may launch and validate unpacker processes but must not
modify HERMES state directly.

Each file's result is decided from its own summary, not the shared exit code of
the process that unpacked its chunk: a file is `completed` only when its summary
is present and every listed Parquet file passes validation, and `failed`
otherwise — including a file whose process died before reaching it, which simply
has no valid summary and is re-run on a later resume. Valid summaries and Parquet
files already written are retained, so one file (or one chunk) failing never
discards another file's finished output. A whole-stage problem still stops the
run and raises a `HermesTpx3Error`: a missing or unbuilt executable, a missing
raw file, or a prior summary that is invalid or has partial Parquet output
(rules 3 and 4 above). Those mean the stage cannot safely proceed; a single file
failing to unpack does not.

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

The runner records one result per pixel file after that file finishes: it never
writes a start-of-work status. Each result is `completed`, `skipped`, or
`failed`.

If one reconstruction process fails, the runner logs that file's failure,
records it `failed`, and keeps reconstructing the remaining files, retaining
valid photon files and summaries from inputs that completed. A later run skips
those completed inputs. A whole-stage problem still stops the run and raises a
HERMES reconstruction error: an unsupported algorithm, a missing executable, or
a pixel filename that does not match the expected pattern.

HERMES programs may be implemented in C++ or Rust, but they must read and write
the HERMES files and columns defined for that analysis step. Choosing a C++ or
Rust HERMES implementation does not change `analysis.mode`; it remains
`mode="hermes"`.

### HERMES event reconstruction

The `hermes/event_reconstruction.py` runner is built. When
`analysis.event_reconstruction` is configured, `hermes/run.py` runs it once for
each photon file, reading `analysis/photons/` and writing an event Parquet file
under `analysis/events/` with a per-file summary under `analysis/logs/events/`.
It uses the same restart, per-file result, and failure rules as photon
reconstruction.

The C++ or Rust event program that the runner launches is not implemented yet:
only its `inc/` and `tests/` directories exist under
`src/backends/reconstruction/events/`. Until that program is built, a HERMES run
cannot complete photon-to-event reconstruction even though the runner is ready.

### HERMES time-walk calibration

Time-walk calibration is a standalone tool, not a pipeline step, so `hermes/run.py`
never calls it. After unpacking, `hermes/timewalk_calibration.py` reads the
sorted pixel-data files, clusters them chip-locally, and fits how a pixel's
arrival time depends on its time-over-threshold using both a linear and an
inverse model. It selects the better model and writes a calibration report, a
comparison plot, and a small correction file. Photon reconstruction later
consumes that correction file through the calibration path saved in its
clustering settings. The example under
`examples/analysis/timewalk_calibration/` shows it running after unpacking.

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

Each step checks its requested output file before running. If that file already
exists, the step is skipped and recorded as `skipped`; otherwise the step runs.
A failed step marks only itself `failed` and leaves the later steps unrun.

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
- write one result per step through `StateManager` once the step finishes, with
  status `completed`, `skipped`, or `failed`; a step that has not run yet has no
  result object
- keep detailed results in the program-specific files defined by the selected
  analysis mode
- return completed or failed state through `StateManager`

The calling workflow saves `StateManager.get_state()` as the HERMES YAML file
with the existing state I/O.

## Logging

Use Loguru with `domain="analysis"`. Every event should also include the selected
mode and the concrete step name.

Examples:

```text
domain="analysis", mode="hermes", step="tpx3_spidr_unpacking"
domain="analysis", mode="hermes", step="tpx3_spidr_reconstruction"
domain="analysis", mode="hermes", step="tpx3_spidr_event_reconstruction"
domain="analysis", mode="hermes", step="timewalk_calibration"
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
JSON file under `analysis/logs/`. Event reconstruction saves one event Parquet
file per photon file under `analysis/events/` with a per-file summary under
`analysis/logs/events/`, once its C++ or Rust program is built.

For EMPIR, the file-based binaries require photon and event files between
commands. The existing `save_photon_files` and `save_event_files` fields control
whether those files remain after downstream success.

Always retain the original raw TPX3 files and the final output requested by the
user. Measure file reading and writing time before adding direct in-memory data
transfer between independently executed programs.
