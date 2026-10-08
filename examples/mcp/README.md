# Set up HERMES from an LLM assistant

HERMES ships one small MCP server so an LLM assistant that speaks MCP — Claude
Code, Claude Desktop, Cursor, and others — can help you configure and run a
HERMES analysis or measurement in your own project. One command wires it up for you; this
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

It also copies the HERMES skills into `.claude/skills/` there. A skill is a
short guide the assistant opens only when it needs it. Older HERMES copies are
replaced and other skills are left alone, so rerun `hermes-mcp-setup` after
upgrading HERMES. Assistants that don't read `.claude/skills/` still get every
MCP tool; the skill files are plain markdown you can read too.

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
  JSON-lines files in the run's `logs/` folder (`log_directory: logs`), so
  nothing is lost — the setting only trims what prints to the screen.

## 3. Run it

```bash
pixi run python run_hermes.py
```

Each stage writes one Parquet file per signal so times from different signals
stay on one comparable clock. For what each stage produces, see the analysis
examples under [`examples/analysis/`](../analysis/).

## Set up a measurement

At the instrument, with the camera and SERVAL attached, say something like:

> Set up a HERMES measurement in ./beamtime.

The assistant asks for what it can't guess:

- **A measurement id and a run label.** The run label is also the name of the
  run's folder, so use a new one for each measurement.
- **SERVAL**: its URL, the path to the SERVAL `.jar`, and the camera's IP address
  and port.
- **The SoPhy calibration files**: the `.bpc` and `.dacs` files for your camera.
- **The timing**: trigger mode, exposure time, trigger period, and how many
  frames to take. Each frame is one raw `.tpx3` file.
- **How far to analyze while recording**: nothing, unpacking, photon
  reconstruction, or event reconstruction. Each raw file is analyzed once SERVAL
  has finished writing it, and a last pass after the recording picks up the
  rest. The analysis stages use the same defaults as an analysis run.

It writes `hermes-config.yaml` and `run_hermes.py` into that folder. The run
writes into its own folder under it, named after the run: raw files in `raw/`,
the calibration files copied into `config/`, and `analysis/`, `logs/` and
`HERMES_record.yaml`.

- **Global timestamps are on.** The config leaves the interval unset, so HERMES
  uses 1 s, or half the trigger period when frames are shorter than 2 s. The
  answer says which.
- **The run is quiet**, as for an analysis run.

Before writing anything, it makes the same checks as `validate_config` (see
"Check a config" below). When one fails, such as a missing calibration file or a
run folder that already has raw files in it, it writes nothing and says what to
fix. Warnings, such as a SERVAL `.jar` that is not found, are returned with the
config.

It does not contact SERVAL and does not start the measurement. You start it:

```bash
pixi run python run_hermes.py
```

## Check how a run went

During a run or after it, ask:

> How far did my HERMES run in ./my-run/run-1 get?

Give it the run folder: the one with `HERMES_record.yaml`, `analysis/` and
`logs/` in it. The assistant reports:

- **How the run ended**: completed, failed, or stopped by Ctrl-C. HERMES writes
  its workflow log and record only when a run ends, so while a run is still going
  the answer says it has not finished and is built from the summary and log
  files written so far.
- **The acquisition**, if the run had one: its status, why it stopped, and the
  frame and dropped-frame counts.
- **For each stage** (unpacking, photon reconstruction, event reconstruction):
  how many files succeeded, were skipped because their outputs already existed,
  failed, or have not run, and how many Parquet files are in its output folders.
- **The files that failed or have not run**, with their error text. A file that
  failed before writing a summary still gets its error from `logs/analysis.jsonl`.
- **Each kind of warning and error once, with a count**, so a warning repeated for
  every file shows up as one line rather than hundreds. Only lines from the last
  run are counted, since every run in a folder adds to the same log files.

It reports what HERMES saved without second-guessing it. Read the per-file
summaries under `analysis/logs/` for the full detail on any one file.

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
- **Files with problems**: a file it could not read, such as one still being
  written, is left out of the counts. A file with no `timestamp_canonical`
  statistics leaves out the folder's time range rather than giving a partial
  one.

It reads only the summary at the end of each file and a few rows, so it is quick
even when a run is many gigabytes. The assistant can then write its own pandas or
matplotlib code against the columns it found.

## Look up config fields and output files

The `hermes-config-and-files` skill lets the assistant look things up instead of
guessing. It is used when you ask it to write or explain a config, or to work
with the Parquet files:

> What does `max_time_spread_ticks` do?
>
> How do I get time-of-flight from the events and the TDC1 triggers?

- **Config fields**: a script prints one config section's fields, with each
  one's type, default, allowed values and meaning. It reads them from the
  HERMES you installed, so it matches your version. You can run it yourself:

  ```bash
  pixi run python .claude/skills/hermes-config-and-files/scripts/show_config_fields.py photon_reconstruction
  ```

  The sections are `measurement_info`, `environment`, `acquisition`, `analysis`,
  `unpacking`, `photon_reconstruction` and `event_reconstruction`.
- **Output files**: `output_files.md` describes each output folder and its
  columns, the time unit, the TDC1 and TDC2 offsets, the known timing limits,
  and what the summaries and logs hold.

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

For a config that runs an acquisition, it lists `acquisition` as the first stage
and also checks the things that would otherwise only go wrong once the camera is
running. It reads only the config and the files it names; it does not contact
SERVAL, so you can check a config on a machine with no camera.

These are problems, so the config is not valid:

- **A calibration file is missing**: the `.bpc` or `.dacs` file under
  `calibration_files`.
- **The detector configuration cannot be used**: a `detector_config_file` that
  is missing or cannot be read, or a setting the camera would refuse, such as an
  exposure time too close to the trigger period.
- **The global timestamp settings would give wrong times**: an interval of 0 or
  less (global timestamps turned off), an interval over 13 s, or, in
  `AUTOTRIGSTART_TIMERSTOP` and `CONTINUOUS`, an interval over half the trigger
  period or a trigger period under 0.1 s. These are the same checks the run
  makes before it starts. When the interval is left unset, the answer says the
  one HERMES will use.
- **A measurement has nowhere to write**: `run_timing` is set but
  `environment.raw_data_directory` is not.
- **The raw data folder already has `.tpx3` files** from an earlier run. The run
  refuses to measure into it, because the old and new files would be mixed.

These are warnings, so the config can still be valid:

- **The SERVAL `.jar` (`program_path`) is not found.** HERMES needs it only to
  start SERVAL when nothing is answering at `url` yet.
- **Less than 1 GB is free** where the raw files will be written.
