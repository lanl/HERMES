# Environment

The state of record should capture the runtime environment used for a run. This
includes the active working directory, the output directories used by
acquisition and analysis, and install-level provenance.

The runtime environment holds:

- directory state for the working directory, run directory, raw data directory,
  analysis directory, log directory, preview directory, and config file
- HERMES Python package version, Python version, and platform, for provenance
- whether overlapping output directories are allowed
- the log level for the run

A working directory is always required. Tool identities — the SERVAL URL and
version, the EMPIR path and version, and each analysis stage's program name,
executable path, and version — live on the acquisition and analysis stage models
that use them, not on the environment.

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
defaults from `working_directory`, such as:

```text
working_directory = /tmp/myfakemeasurements
run_directory = working_directory / "my_measurement_001"
raw_data_directory = run_directory / "rawTpx3"
analysis_directory = run_directory / "analysis"
log_directory = working_directory / "logs"
preview_directory = working_directory / "preview"
```

HERMES unpacking uses `analysis_directory` as one shared analysis directory that
lives under the run directory. Its unpacked data directories are `pixel_hits/`,
`tdc_triggers/`, `global_timestamps/`, `control_packets/`, and
`unrecognized_packets/`. Input-specific unpacker summaries are saved under
`analysis_directory/logs/unpacking/` and photon-reconstruction summaries under
`analysis_directory/logs/photon_reconstruction/`. The separate runtime
`log_directory` may still contain the overall HERMES process log.

If a user provides any field explicitly, that value should be used instead of the
default. For example, a run may use the default `run_directory` but send preview
images to a separate fast disk by setting only `preview_directory`.

When `run_directory` is omitted, it defaults to `measurement_info.run`, so the
run name becomes a directory level under the working directory and a config need
not repeat the name. An explicitly set `run_directory` still wins. The run name
is used as written, so set `run_directory` yourself when the run name would make
an awkward directory name.

The model should save concrete resolved paths for every directory used by the
run so the record is unambiguous later. The model may also record which paths
were user-specified versus defaulted, but the first requirement is that every
directory used by the run is visible in the saved state.

Path models should validate relationships and catch obvious mistakes:

- directory fields should validate into `Path` values in the Pydantic model, not
  remain loose strings
- relative paths should resolve against `working_directory`, or against
  `run_directory` when one is set; an omitted `working_directory` defaults to the
  current directory, and relative sub-directories still resolve against it
- `raw_data_directory`, `analysis_directory`, and `preview_directory` should not
  silently point to the same directory unless `allow_overlapping_output_dirs` is
  set
- the model should not create directories by itself; directory creation belongs
  in workflow or I/O code
