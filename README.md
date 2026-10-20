# HERMES

HERMES processes data from a TPX3Cam read out by a SPIDR board. It turns raw
`.tpx3` files into Parquet tables in three steps:

1. **Unpacking:** raw `.tpx3` files become pixel hits and TDC trigger times.
2. **Photon reconstruction:** neighboring pixel hits are grouped into photons.
3. **Event reconstruction:** nearby photons are grouped into events.

Each step writes its own Parquet files, and every file uses the same clock, so
times from different signals can be subtracted directly (for example, photon
time minus TDC trigger time for time-of-flight).

HERMES is a Python package (`hermes`) plus three C++ programs that do the heavy
work: `hermes-tpx3-spidr` (unpacking), `hermes-photon-clusterer` (photons) and
`hermes-event-reconstructor` (events). There are no prebuilt programs. The C++
programs are compiled on your computer when you install HERMES, and the install
puts them on `PATH` so the Python code finds them by name.

- [Before you install](#before-you-install)
- [Install](#install): in your own project, or from a clone for development
- [Getting started](#getting-started): from a raw file to photons and events
- [Next steps](#next-steps)
- [Set up an LLM assistant](#set-up-an-llm-assistant)
- [Develop HERMES](#develop-hermes)

## Before you install

You need:

- **macOS (Apple silicon) or Linux (x86-64).** These are the systems HERMES is
  set up for.
- **[pixi](https://pixi.sh)**, which installs Python, the C++ compiler and
  every library HERMES needs:

  ```bash
  curl -fsSL https://pixi.sh/install.sh | sh
  ```

- **git**, which pixi uses to download HERMES from GitHub.
- **On macOS only: Apple's Command Line Tools**, which provide git and the
  macOS files the compiler needs:

  ```bash
  xcode-select --install
  ```

  If a command fails with "You have not agreed to the Xcode license
  agreements", run `sudo xcodebuild -license`, read to the end and type
  `agree`. This often happens after an Xcode update.

## Install

There are two ways to install HERMES:

- **In your own project**, to analyze data. Most users want this.
- **From a clone of this repository**, to change HERMES itself.

Either way, the first install takes a minute or so while the C++ programs
compile.

### Option 1: In your own project

Make a new pixi project, add the C++ build tools, then add HERMES:

```bash
pixi init my-analysis
cd my-analysis
pixi add cxx-compiler cmake ninja nlohmann_json pyarrow
pixi add --pypi "hermes @ git+https://github.com/lanl/HERMES.git@v3.3.8"
```

The first `pixi add` line installs the compiler and the libraries the C++
programs are built with. The second downloads HERMES at release `v3.3.8` and
compiles its programs.

To add HERMES to a project you already have, put these lines in its `pixi.toml`
and run `pixi install`. In a `pyproject.toml`, the sections are called
`[tool.pixi.dependencies]` and `[tool.pixi.pypi-dependencies]`.

```toml
[dependencies]
cxx-compiler = "*"
cmake = ">=3.20"
ninja = "*"
nlohmann_json = ">=3.11"
pyarrow = ">=18"

[pypi-dependencies]
hermes = { git = "https://github.com/lanl/HERMES.git", tag = "v3.3.8" }
```

Check that the programs were built:

```bash
pixi run which hermes-tpx3-spidr hermes-photon-clusterer hermes-event-reconstructor
```

Each one should print a path inside your project's `.pixi/` folder.

**To upgrade**, run the `pixi add --pypi` line again with the new release tag,
or change the tag in `pixi.toml` and run `pixi install`. Either one rebuilds the
C++ programs. Releases are listed on the
[releases page](https://github.com/lanl/HERMES/releases).

### Option 2: From a clone, for development

```bash
git clone https://github.com/lanl/HERMES.git
cd HERMES
pixi install
```

`pixi install` sets up the environment, installs HERMES so your edits to the
Python code take effect right away, and compiles the C++ programs.

Check the install by running the tests and an example:

```bash
pixi run python -m pytest tests/unit
pixi run python examples/analysis/unpacking/run_unpacking.py
```

> **After you change any C++ code, run `pixi reinstall hermes`.** The installed
> programs do not rebuild themselves, so until you do, HERMES keeps running the
> old ones. See [Develop HERMES](#develop-hermes).

## Getting started

This walkthrough takes one raw `.tpx3` file through all three steps. It uses a
4 MB sample file from this repository, so you don't need a camera.

Run these commands in the project from [Option 1](#option-1-in-your-own-project).
From a clone, run them in a folder under `data/`, which git ignores.

### 1. Put the raw file in a run folder

HERMES works inside one folder per run. Make one with a `raw/` folder inside it
and download the sample file there:

```bash
mkdir -p run-1/raw
curl -L -o run-1/raw/Tantalum_IronPowder.tpx3 \
  https://github.com/lanl/HERMES/raw/main/tests/data/tpx3/Tantalum_IronPowder.tpx3
```

For your own data, copy your `.tpx3` files into `run-1/raw/` instead.

### 2. Write a config file

A HERMES config is a YAML file that says where the files are and which steps to
run. Save this as `hermes-config.yaml` next to the `run-1` folder:

```yaml
measurement_info:
  measurement_id: my-first-measurement
  run: run-1                      # HERMES works inside the folder run-1/

environment:
  raw_data_directory: raw         # run-1/raw/ holds the .tpx3 files
  analysis_directory: analysis    # run-1/analysis/ gets the results

analysis:
  mode: hermes

  # Step 1: raw .tpx3 files -> pixel hits and TDC triggers
  unpacking:
    program:
      name: tpx3-spidr-cpp
      executable_path: hermes-tpx3-spidr
    tpx3_files: auto              # every .tpx3 file in run-1/raw/

  # Step 2: pixel hits -> photons
  photon_reconstruction:
    program:
      name: photon-clusterer-cpp
      executable_path: hermes-photon-clusterer
    pixel_files: auto
    clustering_algorithm:
      name: connected_components
      settings:
        max_time_spread_ticks: 491520   # 1 microsecond
        min_cluster_size: 2
        max_cluster_size: 64
        min_pixel_tot_raw: 1
        min_cluster_tot_raw: 2
        max_cluster_tot_raw: 65472
        max_aspect_ratio: 3.0
        min_filled_fraction: 0.5

  # Step 3: photons -> events
  event_reconstruction:
    program:
      name: event-reconstructor-cpp
      executable_path: hermes-event-reconstructor
    photon_parquet_files: auto
    clustering_algorithm: connected_components
    settings:
      spatial_link_radius_pixels: 10.0
      spatial_cells_per_axis: 5
      max_time_difference_ticks: 4915200.0   # 10 microseconds
      max_event_duration_ticks: 14745600.0   # 30 microseconds
      min_photon_count: 1
```

To run fewer steps, delete the sections you don't want. For example, keep only
`unpacking` to stop after step 1. Times in the config are in ticks of
25 ns / 12288, so 491520 ticks is 1 microsecond.

### 3. Run it

Save this as `run_hermes.py`:

```python
from hermes.state_service.state_io import load_hermes_record_from_yaml
from hermes.workflows.workflow import Workflow

record = load_hermes_record_from_yaml("hermes-config.yaml")
Workflow(record).run()
```

Then run it:

```bash
pixi run python run_hermes.py
```

It prints a line as each step finishes, such as
`Unpacking finished: 1 unpacked, 0 skipped, 0 failed of 1 raw files`.

### 4. Look at the results

The run folder now holds:

```text
run-1/
├── raw/                      your .tpx3 files (unchanged)
├── analysis/
│   ├── pixel_hits/           one row per pixel hit
│   ├── tdc_triggers/         one row per TDC trigger
│   ├── photons/              one row per photon
│   ├── events/               one row per event
│   ├── global_timestamps/    the camera's global time readings
│   ├── control_packets/      camera control messages
│   └── logs/                 a summary JSON for each file and step
├── HERMES_record.yaml        the config plus what happened in this run
└── HERMES-workflow.jsonl     one line per finished step
```

Read the photons and events with pandas, which is installed with HERMES. Save
this as `read_results.py`:

```python
import pandas as pd

photons = pd.read_parquet("run-1/analysis/photons")
events = pd.read_parquet("run-1/analysis/events")
print(len(photons), "photons and", len(events), "events")
print(events.head())
```

```bash
pixi run python read_results.py
```

For the sample file, this prints `92703 photons and 45122 events`, followed by
the first five events. Photons have the columns `photon_id`, `x`, `y`,
`timestamp_canonical`, `tot` and `quality_flags`. Events have `event_id`, `x`,
`y`, `timestamp_canonical`, `photon_count` and `quality_flags`. Every
`timestamp_canonical` column is in the same ticks of 25 ns / 12288.

### 5. Run it again

Running `run_hermes.py` again skips every file that is already finished, so
it's safe to rerun after adding more `.tpx3` files to `run-1/raw/`. To redo a
step, for example after changing its settings, add `overwrite: true` under that
step's `runtime_options`:

```yaml
  photon_reconstruction:
    runtime_options:
      overwrite: true
```

Redoing photon reconstruction also redoes event reconstruction.

## Next steps

- **[Photon timing](docs/photon-timing.md):** choose how each photon's time is
  set (`average`, `leading_edge` or `brightest`) and turn on time-walk
  correction.
- **[Output files](src/hermes/skills/hermes-config-and-files/output_files.md):**
  every folder and column HERMES writes, and how to compute time-of-flight.
- **[Taking data with a camera](examples/acquisition/serval/README.md):** HERMES
  can start ASI's SERVAL server, run a measurement and unpack each raw file as
  it is written.
- **EMPIR:** HERMES can also run an existing EMPIR installation if its programs
  are on `PATH`. HERMES does not install EMPIR. If a config names an EMPIR
  program that isn't on `PATH`, HERMES warns and stops.

## Set up an LLM assistant

HERMES includes an MCP server, so an assistant that supports MCP (Claude Code,
Claude Desktop, Cursor and others) can write and check configs for you and
look up what each setting does. It runs on your computer only and has no
network connection or login.

1. Install HERMES in your project ([Option 1](#option-1-in-your-own-project)).
2. In the folder where you do your analysis, run:

   ```bash
   pixi run hermes-mcp-setup
   ```

   This writes a `.mcp.json` file that tells the assistant how to start HERMES.
   If `.mcp.json` already exists, the HERMES entry is added and the others are
   kept. It also copies short HERMES guides into `.claude/skills/`, which the
   assistant reads when it needs them. Run it again after upgrading HERMES.
   Claude Desktop doesn't read `.mcp.json`, so copy the `mcpServers` entry from
   it into Claude Desktop's own config file.
3. Restart your assistant.
4. Ask it, for example:

   > Configure a HERMES analysis run for the data I have in ./run-1.

   It asks how many steps to run, then writes `hermes-config.yaml` and
   `run_hermes.py` into that folder. Run them with
   `pixi run python run_hermes.py`.

See [`examples/mcp/README.md`](examples/mcp/README.md) for the full walkthrough.

## Develop HERMES

Start from [Option 2](#option-2-from-a-clone-for-development). Then:

| To do this | Run |
| --- | --- |
| Run the Python tests | `pixi run python -m pytest tests/unit` |
| Run the known-good cases in `evals/` | `pixi run python evals/run_evals.py` |
| Build and test one C++ program | `pixi run test-cpp-unpacker`<br>`pixi run test-cpp-photon-clusterer`<br>`pixi run test-cpp-event-reconstructor` |
| Use your C++ changes in HERMES runs | `pixi reinstall hermes` |

The `test-cpp-*` commands build separate test copies under `build/`. They don't
update the programs HERMES runs. Only `pixi reinstall hermes` does that, so run
it after any C++ change and before running the evals.

`evals/` holds known-good cases that pin down exactly what HERMES should produce
for a given input. Run them after changing unpacking, reconstruction or
workflow code, and fix any difference before finishing.

## Citing HERMES

If you use HERMES in your research, please cite it. Use the "Cite this
repository" button on the GitHub page, or see [`CITATION.cff`](CITATION.cff).

## Copyright

© 2023. Triad National Security, LLC. All rights reserved.
This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
Department of Energy/National Nuclear Security Administration. All rights in the program are
reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
Security Administration. The Government is granted for itself and others acting on its behalf a
nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare 
derivative works, distribute copies to the public, perform publicly and display publicly, and to permit others to do so.

O4660
