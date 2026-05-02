# Environment

The state of record should capture the runtime environment used for a run. This
includes the location and version of external tools, the active working
directory, and all output directories used by acquisition and analysis.

Important environment fields include:

- SERVAL URL or host/port
- SERVAL software version reported by `/dashboard`
- EMPIR installation path or executable path
- EMPIR version, when available
- HERMES Python package version
- `hermes-tpx3-spidr` binary path
- `hermes-tpx3-spidr` version
- Python version and platform, when useful for provenance
- working directory
- data directory
- raw TPX3 data directory
- analyzed data directory
- log directory
- preview image directory

Directory fields should be individually configurable, but they should default
from `working_dir` when not provided. A practical first path model is:

```text
working_dir = /tmp/myfakemeasurements
data_dir = working_dir / "data"
raw_data_dir = data_dir / "tpx3"
analyzed_data_dir = data_dir / "analyzed"
log_dir = working_dir / "logs"
preview_dir = working_dir / "preview"
```

If a user provides any field explicitly, that value should be used instead of the
default. For example, a run may use the default `data_dir` but send preview
images to a separate fast disk by setting only `preview_dir`.

The model should save concrete resolved paths in the run record so the record is
unambiguous later. It may also record which paths were user-specified versus
defaulted, but the first requirement is that every directory used by the run is
visible in the saved state.

Path models should validate relationships and catch obvious mistakes:

- directory fields should be paths, not loose strings
- relative paths should be resolved relative to `working_dir`
- `raw_data_dir`, `analyzed_data_dir`, and `preview_dir` should not silently
  point to the same directory unless explicitly allowed
- the model should not create directories by itself; directory creation belongs
  in workflow or I/O code
