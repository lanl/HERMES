# Analysis

`src/hermes/analysis/` contains the Python code that runs analysis steps. The
unpacker selected by the user, not Python, reads the binary packets in raw TPX3
files.

Expected responsibilities:

- run the selected unpacker for raw `.tpx3` files
- load pixel-hit, TDC-hit, timestamp, or control-packet Parquet files
- group pixel hits into photons when photon clustering is requested
- group photons into events when event clustering is requested  
- write specific output files, such as photon and event Parquet files, images, or plots
- save analysis settings and results through `hermes.state_service`

Analysis workflows should accept explicitly named inputs, such as raw TPX3 files
or directories containing TPX3 Parquet files, together with typed Pydantic
settings. They should return explicitly named paths, such as the TPX3 Parquet
output directory, summary JSON file, image file, or plot file. Analysis code
must save changes through `hermes.state_service`; it should not change the
HERMES state directly.

Analysis workflows must not require acquisition state to be present. For
analysis-only use, raw TPX3 files, image files, or directories containing TPX3
Parquet files should be saved directly in the analysis section of the HERMES
state.

## C++ and Rust Backends

HERMES should allow more than one backend to perform each analysis step. For
example, a user may choose a C++ unpacker for one run and a Rust unpacker for
another run. The same choice should be possible when multiple photon or event
reconstruction programs are available.

Analysis backends should be grouped by the step they perform. C++ and Rust
versions of the same backend should live beside each other:

```text
HERMES/
├── Cargo.toml
└── backends/
    ├── unpackers/
    │   └── tpx3-spidr/
    │       ├── cpp/
    │       └── rust/
    ├── photon-reconstructors/
    └── event-reconstructors/
```

The top-level `Cargo.toml` should include the Rust directories that are part of
the Cargo workspace. Each C++ directory should contain its own CMake project.
A directory should be created only when its backend is being implemented.

HERMES should run the backend selected for each step using its executable path.
The selected backend may come from this repository or may be installed
somewhere else on the user's computer. HERMES should not require separate
Python code for C++ and Rust versions of the same step.

Backends that perform the same step must accept the same required input and
produce the same required output. This allows the user to change programs
without changing the rest of the analysis workflow.

For example, a user could select:

```yaml
analysis:
  unpacker:
    name: hermes-tpx3-spidr-cpp
    executable_path: /path/to/hermes-tpx3-spidr-cpp
  photon_reconstructor:
    name: hermes-photon-reconstructor-rust
    executable_path: /path/to/hermes-photon-reconstructor-rust
  event_reconstructor:
    name: another-event-program
    executable_path: /path/to/another-event-program
```

## Files Created Between Analysis Steps

The TPX3 analysis can run as three separate steps:

```text
raw TPX3 file
  -> unpacker
  -> pixel and timing Parquet files
  -> photon reconstruction
  -> photon Parquet files
  -> event reconstruction
  -> event Parquet files
```

The user should be able to choose the program used for each step. The output
from one step becomes the input to the next step.

HERMES should always keep the original raw TPX3 file and the output from the
last step requested by the user. Files created between steps do not always need
to be kept permanently. A single setting should control this behavior:

```yaml
keep_intermediate_files: false
```

When this setting is `false`, HERMES may write the files needed by the next step
to a temporary working directory. HERMES should delete those files only after
the next step finishes successfully. If a step fails, HERMES should leave the
temporary files in place so the user can inspect them and investigate the
failure.

When `keep_intermediate_files` is `true`, HERMES should keep the pixel, timing,
photon, and event Parquet files produced by the requested steps.

The first working version should use Parquet files between programs. The time
spent reading and writing each file should be measured. If these file operations
make the analysis too slow, a later version may pass data directly between
programs. This performance change should not alter the names, columns, timing
units, or meaning of the saved Parquet files.
