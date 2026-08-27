# Set up HERMES from an LLM assistant

HERMES ships one small MCP server so an LLM assistant that speaks MCP — Claude
Code, Claude Desktop, Cursor, and others — can help you configure and run a
HERMES analysis in your own project. This folder holds the one file you copy to
wire it up, [`mcp.json`](mcp.json), and this walkthrough.

The server runs as a local subprocess and talks over standard input and output.
There is no network listener and no login.

## Before you start

Install HERMES in your own pixi project (see "Use HERMES in your own pixi
project" in the top-level [README](../../README.md)). Installing HERMES puts the
`hermes-mcp` command on `PATH` in your environment, so there is nothing else to
install.

## 1. Point your assistant at HERMES

Copy `mcp.json` into your project:

- **Claude Code** — save it as `.mcp.json` at your project root.
- **Claude Desktop** — add the same `mcpServers` block to its config file.

```json
{ "mcpServers": { "hermes": { "command": "pixi", "args": ["run", "hermes-mcp"] } } }
```

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

## 3. Run it

```bash
pixi run python run_hermes.py
```

Each stage writes one Parquet file per signal so times from different signals
stay on one comparable clock. For what each stage produces, see the analysis
examples under [`examples/analysis/`](../analysis/).
