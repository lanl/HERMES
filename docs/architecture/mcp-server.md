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

- **Shared core** — `check_installation` reports which HERMES is installed and
  whether everything it needs is present. `report_run_status` reports how far a
  run got and why anything failed. `start_run` and `stop_run` start and stop a run
  the user has approved. These serve setup, acquisition, and analysis alike.
- **Setup group** — `check_installation` covers setup: whether the three C++
  programs are on `PATH` and when they were built, whether the default time-walk
  calibration is present, and whether EMPIR is available.
- **Acquisition group** — `check_camera` reports whether SERVAL answers and a
  detector is connected, without changing anything. `create_acquisition_config`
  writes a measurement config, and `validate_config` checks it. On a machine with
  no camera, `check_camera` reports "no SERVAL reachable", which is the correct
  answer rather than an error.
- **Analysis group** — `create_analysis_config` writes a workflow config and a
  runnable script, `validate_config` checks it, and `describe_output_files`
  reports what is in a run's Parquet files.

The one reason to split this into separate servers is different machines:
acquisition runs at the instrument with the camera and SERVAL attached, while
analysis often runs later on a laptop or cluster with no camera. The single-server
design handles that by having the acquisition tools report "not reachable" on an
analysis machine. Start with one server; split only if that ever becomes a real
problem.

## MCP tools and skills

To keep the assistant's context small, the work is split between MCP tools and
skills.

**MCP tools** are for small checks that give short answers. Every MCP assistant
can use them. A tool that reads a large file returns a summary of it, not the
file. `start_run` and `stop_run` are tools too, because a tool gets its own
permission rule in the assistant, which keeps approval clear.

**Skills** are for guides and long jobs. Only a skill's short description is
always loaded. The rest of `SKILL.md` loads when the skill is used, and the other
files in its folder load only if the assistant opens them. Scripts in a skill run
in the shell, only what they print enters the conversation, and long jobs can run
in the background. The skills are:

- `hermes-config-and-files` — the config field guide (one section of the
  installed `HermesRecord` models at a time) and the output file guide.
- `hermes-analyze-run`, `hermes-set-up-measurement`, and `hermes-fix-a-problem`
  — the usual steps in order, which tool or script to use at each step, and an
  "if this breaks, check that" list.
- `hermes-firework-movies` and `hermes-find-clustering-settings` — each asks the
  user its questions, runs a built-in HERMES function from a script, and reports a
  short summary. `hermes-firework-movies` also holds the steps for making movies
  of a run, so there is no separate movie guide.

Skills follow the open Agent Skills standard. An assistant that does not support
skills still gets every MCP tool and loses only the guides and the two analysis
skills; the skill files are plain markdown a person can read too.

## Starting runs

The assistant can start a run once the user approves. Approval is the
assistant's own permission prompt for the `start_run` tool, or auto-approve if
the user has turned it on; HERMES adds no approval step of its own. A user who
wants to be asked every time, even with auto-approve on, adds
`mcp__hermes__start_run` to the `ask` list in their assistant's settings.
Approving one `start_run` call counts as approval for that whole run (see
[State Services](state-service.md)).

`start_run` takes a config that passes `validate_config`, starts the run script
in the background, and returns right away. It saves the run's process ID in the
run folder and refuses to start a second run in a folder where one is still
going. `stop_run` stops the run the same way Ctrl-C does, so the camera is
stopped and the record is saved.

## Built-in analyses

Analysis goes past the event Parquet files. HERMES gets built-in analyses that
follow the time-walk calibration pattern (see [Analysis](analysis.md)): one plain
function under `src/hermes/runner/analysis/hermes/`, run after a finished
analysis, that writes a short report, with no change to the pipeline and no
registry. A skill asks the questions, runs the function from a script, and
reports a short summary; these analyses get no MCP tool. The first two are:

- `make_firework_movies` — movies of the bursts after each TDC1 trigger, or of
  the continuous photon stream when there is no TDC1 signal.
- `find_clustering_settings` — scans photon clustering and event reconstruction
  settings and recommends values, which the user approves before the config is
  changed.

For questions no built-in analysis covers, `describe_output_files` tells the
assistant what is in the Parquet files, and the assistant writes its own pandas
or matplotlib code.

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
  `examples/mcp/mcp.json` stays as an example of that content and for Claude
  Desktop, whose config the user edits by hand.
- The skills ship inside the package in `src/hermes/skills/<skill name>/`.
  `hermes-mcp-setup` also copies every HERMES skill into `.claude/skills/` in the
  user's folder, next to the `.mcp.json` it writes. It replaces older copies of
  HERMES skills and leaves other skills alone, so users rerun it after upgrading
  HERMES.

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
- **Phase 3: the rest of the tools and skills.** The order follows what each
  piece uses:
  - `check_installation`, `describe_output_files`, `report_run_status`,
    `check_camera`, and `start_run` with `stop_run` use only existing HERMES code
    and can be built in any order.
  - The `hermes-config-and-files` skill comes before any other skill, because it
    adds `src/hermes/skills/` and the copying in `hermes-mcp-setup`.
  - The acquisition checks in `validate_config` come before
    `create_acquisition_config`, which runs the same checks on the config it
    writes.
  - The firework movies and the clustering settings finder come after the first
    skill.
  - Each step-by-step guide skill ships once the tools and scripts it names
    exist. `hermes-analyze-run` can ship first.

**Out of scope:** tools that change the bias voltage or DACs directly, making
calibration files (SoPhy does that), and a network server or login.

## Package structure

```text
src/
└── hermes/
    ├── mcp/
    │   ├── __init__.py   # keep empty
    │   ├── server.py     # the MCP server and its tools
    │   └── setup.py      # hermes-mcp-setup: writes .mcp.json and copies the skills
    └── skills/           # one folder per skill, copied into .claude/skills/
        └── <skill name>/
            ├── SKILL.md  # when to use the skill, and which file or script to open
            ├── *.md      # longer guides SKILL.md points to, such as output_files.md
            └── scripts/  # scripts the assistant runs in the shell
```

The server uses the Python MCP SDK's `MCPServer` for the server and tool
definitions, Pydantic for the tool input models, and Loguru for structured
logging, consistent with the rest of HERMES.
