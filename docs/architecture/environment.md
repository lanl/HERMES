# Environment

The state of record should capture the runtime environment used for a run. This
includes the location and version of external tools, the active working
directory, and all output directories used by acquisition and analysis.

Important environment fields include:

- SERVAL URL or host/port
- SERVAL software version reported by `/dashboard`
- EMPIR installation path or executable path as a `Path`
- EMPIR version, when available
- HERMES Python package version
- selected unpacker name, executable path as a `Path`, and version
- selected photon reconstruction backend name, executable path, and version
- selected event reconstruction backend name, executable path, and version
- Python version and platform, when useful for provenance
- A working directory is required to be defined in HERMES

## Directory State

Directory fields should use a reusable model instead of bare path values. YAML
may still represent paths as readable scalar strings, but loading a
`HermesRecord` should validate them into `Path` values.

A practical first directory model is:

```text
DirectoryState
  path: Path | None
  required: bool
  resolved_path: Path | None
```

`path` is the user- or configuration-provided path, if any. `resolved_path` is
the concrete path HERMES will actually use for the run. A separate stored
`resolved` flag should be avoided because it can drift from `resolved_path`; code
can derive `resolved` from `resolved_path is not None`, or expose it as a
computed field if it is useful in serialized output.

Only `working_directory` is intrinsically required by the base environment model. If a
user does not provide it, `working_directory` should default to the current process
directory where HERMES was called. Other directories should default to
`required = false` so users can decide what a run needs:

```text
working_directory.required = true
run_directory.required = false
raw_data_directory.required = false
analysis_directory.required = false
log_directory.required = false
preview_directory.required = false
config_file.required = false
```

A directory that is not marked required may remain unresolved in a partially
specified record. Before acquisition starts, any directory required by the active
workflow must have a `resolved_path`. For example, a raw SERVAL acquisition
workflow needs a raw data directory, while preview output needs a preview
directory and analysis needs an analyzed data directory. If HERMES needs a
directory for the selected workflow and it has no `resolved_path`, the workflow
or state service should raise a validation error before starting acquisition. A
warning is appropriate only when HERMES can safely choose and record a default.

Directory fields should be individually configurable. When a workflow needs a
directory and the user has not provided one, HERMES may resolve practical
defaults from `working_dir`, such as:

```text
working_directory = /tmp/myfakemeasurements
run_directory = working_directory / "my_measurement_001"
raw_data_directory = run_directory / "rawTpx3"
analysis_directory = run_directory / "analysis"
log_directory = working_directory / "logs"
preview_directory = working_directory / "preview"
```

HERMES unpacking uses `analysis_directory` as one shared analysis directory for
The `analysis_directory` lives under the 
run directory. Its unpacked data directories are `pixel_hits/`, `tdc_triggers/`, 
`global_timestamps/`, `control_packets/`, and`unknown_packets/`. Input-specific 
unpacker summaries are saved under `analysis_directory/logs/unpacker/`. The separate 
runtime `log_directory` may still contain the overall HERMES process log.

If a user provides any field explicitly, that value should be used instead of the
default. For example, a run may use the default `run_directory` but send preview
images to a separate fast disk by setting only `preview_directory`.

The model should save concrete resolved paths for every directory used by the
run so the record is unambiguous later. The model may also record which paths
were user-specified versus defaulted, but the first requirement is that every
directory used by the run is visible in the saved state.

Path models should validate relationships and catch obvious mistakes:

- directory and executable path fields should validate into `Path` values in the
  Pydantic model, not remain loose strings
- relative paths should be resolved relative to `working_directory`
`raw_data_directory`, `analysis_directory`, and `preview_directory` should not silently
  point to the same directory unless explicitly allowed
- the model should not create directories by itself; directory creation belongs
  in workflow or I/O code
