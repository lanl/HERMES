# MCP Server

`src/hermes/mcp/` provides one small MCP server so that any LLM assistant that
speaks MCP (Claude Code, Claude Desktop, Cursor, or anything else) can help a user
set up HERMES, acquire data from a TPX3Cam, and analyze `.tpx3` files. The server
ships inside the HERMES package and runs in the same pixi environment as HERMES,
so it imports `hermes` directly and reports true information about the installed
version and the user's working directory rather than guessing.

## Purpose

Users do not work inside the HERMES repository. They install HERMES with pixi,
write a short script in their own directory that imports `hermes`, and drive the
work from an LLM chat. The helper therefore has to travel with the installed
package, not the repository, so it can be reached from the user's own directory.

The server talks over standard input and output as a local subprocess. There is no
network listener and no login or authentication.

## Why one server

HERMES is a single pixi-installed package: the Python `hermes` package, the three
compiled C++ programs (`hermes-tpx3-spidr`, `hermes-photon-clusterer`,
`hermes-event-reconstructor`), and the SERVAL and camera acquisition code that
lives in the same package. Because it is one package, the helper is one bundled
MCP server, not three. One server means one console command, one pixi task, and
one line in the user's config.

The three areas become three groups of tools inside that one server, sharing a
common core:

- **Shared core** — report the installed version and environment (which HERMES and
  which C++ programs are actually present), report what is in the user's working
  directory, and diagnose a failure from the config and the workflow log.
- **Setup group** — confirm the three C++ programs compiled and are on `PATH`, the
  build dependencies are present, and whether EMPIR is available; explain a failed
  setup.
- **Acquisition group** — check the SERVAL server, report the camera connection and
  detector snapshot, validate an acquisition config, and help start a run. On a
  machine with no camera these tools report "no SERVAL or camera reachable", which
  is the correct answer rather than an error.
- **Analysis group** — generate a workflow config and a runnable script, validate a
  config, report how far a workflow has progressed, and diagnose a failed workflow.

The one reason to split this into separate servers is different machines:
acquisition runs at the instrument with the camera and SERVAL attached, while
analysis often runs later on a laptop or cluster with no camera. The single-server
design handles that by having the acquisition tools report "not reachable" on an
analysis machine. Start with one server; split only if that ever becomes a real
problem.

## Ground truth it relies on

The server imports `hermes` and uses its real models and functions, so anything it
generates is valid by construction and anything it reports is true of the installed
code:

- A workflow config is a `HermesRecord` YAML: `measurement_info`, `environment`,
  and `analysis` (see [State Model](state-model.md)). The analysis stages —
  unpacking, photon reconstruction, event reconstruction — are each optional and
  can run alone or as a chain.
- A config is loaded and validated with
  `hermes.state_service.state_io.load_hermes_record_from_yaml` and
  `HermesRecord.model_validate`.
- A run is driven by `hermes.workflows.workflow.Workflow`: build it from a record
  and call `run()`, which runs whatever stages the record configures (see
  [Workflows](workflows.md)).
- The installed version is read at run time with
  `importlib.metadata.version("hermes")`.

## Distribution and setup

- Two console commands are installed with the package (`[project.scripts]` in
  `pyproject.toml`): `hermes-mcp` runs the server, and `hermes-mcp-setup` writes
  the per-user config.
- A pixi task runs each, so a user starts the server with `pixi run hermes-mcp`
  and wires up their assistant with `pixi run hermes-mcp-setup`.
- The single per-user setup step is `pixi run hermes-mcp-setup`, run from the
  analysis folder. It writes a `.mcp.json` there pointing the LLM tool at
  `pixi run hermes-mcp`, keeping any servers the file already lists. The content
  travels in the installed package (`src/hermes/mcp/setup.py`), so a user who
  installed HERMES has it without checking out the repository;
  `examples/mcp/mcp.json` stays as the reference for that content and for Claude
  Desktop, whose config the user edits by hand.

## Phased build

The server is built in slices so each one maps to real HERMES steps and nothing is
gold-plated.

- **Phase 1 (first slice): configure an analysis run.** One analysis tool,
  `create_analysis_config`. The user says "configure a HERMES analysis run for the
  data I have", the assistant asks how far to run — unpacking, photon
  reconstruction, or event reconstruction — and the tool writes a `HermesRecord`
  YAML for the `.tpx3` files in the folder plus a short runnable script, filling in
  HERMES's standard defaults for the chosen stages.
- **Phase 2: validate a config.** `validate_config` loads a config YAML through
  the installed HERMES's real rules and reports either that it is valid, with the
  stages it would run, or a clear per-field list of what is wrong. It pairs with
  `create_analysis_config`: generate, then check.
- **Later:** the rest of the analysis group (report progress, diagnose a failure)
  and the shared core, then the acquisition group, then the setup group. The
  ordered "usual steps" for each area, and a short "if this breaks, check that"
  list, ship as MCP prompts and resources so the assistant can map a request onto
  the workflow without hard-coding it.

## Package structure

```text
src/
└── hermes/
    └── mcp/
        ├── __init__.py   # keep empty
        └── server.py     # the FastMCP server and its tools
```

The server uses the Python MCP SDK's `MCPServer` for the server and tool
definitions, Pydantic for the tool input models, and Loguru for structured
logging, consistent with the rest of HERMES.
