# Set up HERMES from an LLM assistant

HERMES ships one small MCP server so an LLM assistant that speaks MCP — Claude
Code, Claude Desktop, Cursor, and others — can help you configure and run a
HERMES analysis in your own project. One command wires it up for you; this
folder also holds [`mcp.json`](mcp.json) as a reference for what that command
writes, plus this walkthrough.

The server runs as a local subprocess and talks over standard input and output.
There is no network listener and no login.

## Before you start

Install HERMES in your own pixi project (see "Use HERMES in your own pixi
project" in the top-level [README](../../README.md)). Installing HERMES puts the
`hermes-mcp` command on `PATH` in your environment, so there is nothing else to
install.

## 1. Point your assistant at HERMES

Run this once from the folder where you do your analysis:

```bash
pixi run hermes-mcp-setup
```

It writes a `.mcp.json` there with the HERMES server entry below. If that folder
already has a `.mcp.json`, it keeps the servers already listed and just adds the
HERMES one.

```json
{ "mcpServers": { "hermes": { "command": "pixi", "args": ["run", "hermes-mcp"] } } }
```

Claude Code and other tools that read a project `.mcp.json` are ready after
that. Claude Desktop has no project `.mcp.json`, so add the same `mcpServers`
block to its own config file by hand.

Your assistant launches `pixi run hermes-mcp` from your project, which starts the
server using the HERMES you installed. Start (or restart) your assistant so it
picks up the new config.

## 2. Ask it to configure a run

Put your `.tpx3` files in a folder, then say something like:

> Configure a HERMES analysis run for the data I have in ./my-run.

The assistant asks how far you want to go:

- **unpacking** — raw `.tpx3` into pixel-hit and TDC Parquet files.
- **photon reconstruction** — also group pixel hits into photons.
- **event reconstruction** — also group photons into events.

It may also ask for a measurement id and run label to record with the data. It
then writes two files into that folder, filled in with HERMES's standard defaults
for the stages you chose:

- `hermes-config.yaml` — the workflow config.
- `run_hermes.py` — a short script that loads the config and runs the workflow.

Two of those defaults are worth calling out:

- **Time-walk correction is on**, using the calibration HERMES ships with
  (`timewalk_calibration_file: default` under photon reconstruction).
- **The run is quiet**, showing only errors on your terminal
  (`log_level: ERROR`). HERMES still writes its full, structured logs to
  JSON-lines files on disk, so nothing is lost — the setting only trims what
  prints to the screen.

## 3. Run it

```bash
pixi run python run_hermes.py
```

Each stage writes one Parquet file per signal so times from different signals
stay on one comparable clock. For what each stage produces, see the analysis
examples under [`examples/analysis/`](../analysis/).

## Describe the output files

Once a run has finished, ask the assistant what it wrote before you start
looking at the data:

> Describe the output files in ./my-run/analysis.

For each folder in the run's `analysis/` folder (`pixel_hits/`, `tdc_triggers/`,
`photons/`, `events/`, and the rest), the assistant reports:

- **How many Parquet files** there are and their total size.
- **The columns and their types.**
- **The number of rows.**
- **The first and last `timestamp_canonical`**, and the time between them in
  seconds. Every `timestamp_canonical` counts the same ticks of 25 ns / 12288
  (about 2.03 ps), so times from different folders can be subtracted directly.
- **A few example rows** from one file.
- **Files it could not read**, such as one still being written.

It reads only the summary at the end of each file and a few rows, so it is quick
even when a run is many gigabytes. The assistant can then write its own pandas or
matplotlib code against the columns it found.

## Check the installation

When something doesn't work, start by asking:

> Check my HERMES installation.

The assistant reports:

- **The HERMES version**, and where it was installed from: the git URL and
  commit for an install from git, or the folder for a clone you are editing.
  Both are empty for an install from a package index.
- **The three C++ programs** (`hermes-tpx3-spidr`, `hermes-photon-clusterer`,
  `hermes-event-reconstructor`): whether each is on `PATH`, where it is, and when
  it was built. HERMES looks them up the same way a run does, so the answer
  matches what a run would find.
- **Out-of-date programs.** If you edit HERMES's C++ source in a clone,
  the installed programs are not rebuilt, so they keep running the old code
  until you run `pixi reinstall hermes`. The assistant names the source file that
  changed after the program was built.
- **The default time-walk calibration** that `timewalk_calibration_file: default`
  uses.
- **EMPIR** (`empir_pixel2photon_tpx3spidr`, `empir_photon2event`,
  `empir_event2image`). HERMES doesn't install EMPIR and needs it only for an
  EMPIR analysis, so "not on `PATH`" isn't an error.
- **The versions of the main Python packages**: pydantic, pyarrow, numpy, and
  mcp.

## Check a config

You can also ask the assistant to check an existing config before you run it:

> Validate my HERMES config.

It reports whether the config is valid — and, when it is, the stages it would run
— or, when it is not, a clear list of exactly what to fix (a missing field, a bad
value, an unknown key, or unparseable YAML).
