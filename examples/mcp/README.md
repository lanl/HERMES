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

## Check a config

You can also ask the assistant to check an existing config before you run it:

> Validate my HERMES config.

It reports whether the config is valid — and, when it is, the stages it would run
— or, when it is not, a clear list of exactly what to fix (a missing field, a bad
value, an unknown key, or unparseable YAML).
