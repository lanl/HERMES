# HERMES Architecture

This directory captures the intended shape of HERMES while the first concrete
workflow is being built. The architecture should stay small and practical. It is
allowed to evolve as acquisition and analysis workflows become real code.

## Purpose

HERMES is an acquisition and analysis codebase centered on TPX3Cam detectors from
Amsterdam Scientific Instruments. It should support multiple acquisition and
analysis modalities while keeping one durable state of record for each run.

The central state object is described in [State Model](state-model.md). Details
for each major boundary live in separate files:

- [Environment](environment.md)
- [Acquisition](acquisition.md)
- [TPX3 SPIDR Unpacker](unpacker.md)
- [Analysis](analysis.md)
- [State](state-model.md)
- [State Services](state-service.md)
- [Workflows](workflows.md)
- [Logging](logging_instructions.md)
- [Open Questions](open-questions.md)

## Design Principles

- Start with one working acquisition-to-analysis workflow before adding broad
  abstractions.
- Keep state explicit, typed, serializable, and testable.
- Treat Pydantic models as durable records, not as runtime service objects.
- Keep detector I/O, file decoding, and analysis behavior outside the models.
- Store pixel-hit Parquet files, TDC-hit Parquet files, images, and plots on disk
  and record their paths in the state model.
- Keep generated output files, caches, raw detector data, and build products out
  of version control.
- Use Loguru for structured logs around acquisition, decoding, analysis, and
  state transitions.
- Prefer Pixi-managed Python environments and focused pytest coverage when
  Python code is added.

## Proposed Repository Layout

```text

HERMES/
├── Cargo.toml  # Rust workspace file for Rust analysis backends
├── backends/   # backends selected by HERMES for each analysis step
│   ├── unpackers/
│   │   └── tpx3-spidr/
│   │       ├── cpp/
│   │       │   ├── CMakeLists.txt
│   │       │   ├── include/
│   │       │   ├── src/
│   │       │   └── tests/
│   │       └── rust/
│   │           ├── Cargo.toml
│   │           ├── src/
│   │           │   ├── lib.rs
│   │           │   └── main.rs
│   │           └── tests/
│   ├── photon-reconstructors/
│   └── event-reconstructors/
│
├── src/
│   └── hermes/
│       ├── __init__.py         # makes hermes the Python import package
│       ├── state_service/      # state management, change proposal, validation, and approval workflow 
│       │   ├── __init__.py     # makes hermes.state_service a Python package. Keep __init__.py empty!
│       │   ├── state_manager.py    # core logic for managing state access, change proposals, validation, and approval workflow
│       │   ├── change_requests.py  # the ChangeRequest data model and related logic for tracking proposed changes
│       │   ├── state_io.py         # functions for loading and saving HermesRecord YAML files
│       │   ├── state_logger.py     # functions for logging state changes and maintaining an audit trail
│       │   └── shared_types.py     # shared types and enums for the state service
│       │
│       ├── state/
│       │   ├── __init__.py         # makes hermes.state a Python package. Keep __init__.py empty!
│       │   ├── state.py            # top-level aggregate model
│       │   │
│       │   └── models/
│       │       ├── __init__.py                 # makes models a Python package. Keep __init__.py empty!
│       │       ├── measurement.py              # measurement info and metadata
│       │       ├── analysis/                   # analysis environments that are unioned in the top-level record
│       │       │   ├── empir.py                # EMPIR analysis environment, configuration, and related settings
│       │       │   └── hermes_tpx3_spidr.py    # TPX3 SPIDR analysis environment, configuration, and related settings
│       │       ├── acquisition/                # acquisition environments that are unioned in the top-level record
│       │       │   ├── serval.py               # SERVAL acquisition environment, configuration, and related settings
│       │       │   ├── pymepix.py              # PyMEPIX acquisition environment, configuration, and related settings
│       │       │   └── mcp2hist.py             # MCP2Hist acquisition environment, configuration, and related settings
│       │       ├── detector.py                 # TPX3Cam chip, layout, health, and detector config metadata
│       │       ├── environment.py              # Path fields for working, data, raw data, analyzed data, log, preview, config, and tool paths
│       │       └── shared_models.py            # shared models and enums for the state models
│       │
│       ├── acquisition/        # acquisition mode packages such as hermes.acquisition.serval
│       ├── analysis/           # analysis mode execution and wrappers
│       ├── workflows/          # ordered acquisition and analysis steps
│       └── logging.py          # setup for Loguru logging across the codebase
│
├── tests/
├── docs/
│   ├── architecture/
│   │   ├── general.md
│   │   ├── state-model.md
│   │   ├── environment.md
│   │   ├── acquisition.md
│   │   ├── unpacker.md
│   │   ├── analysis.md
│   │   ├── state-service.md
│   │   ├── workflows.md
│   │   ├── logging_instructions.md
│   │   ├── open-questions.md
│   └── decisions/
│
├── .agent/
│   ├── resources/  # vendor manuals, SERVAL documentation, example unpacking code, and other reference materials for agents and developers
│   └── examples/   # example acquisition and analysis scripts, Jupyter notebooks, and other reference materials for agents and developers
│
└── .scratch/ # non-tracked files that are useful for development but not part of the core codebase
```

This layout is a target shape, not a requirement to create every file
immediately. Add a backend directory only when its first working version is
being implemented. Rust backends remain members of the top-level Cargo
workspace even though they are grouped by analysis step under `backends/`.

## External References

Vendor manuals, SERVAL documentation, and example unpacking code belong under
`.agent/resources/` and `.agent/examples/`. Agents and developers should consult
those files when implementing TPX3Cam, SPIDR, SERVAL, TDC, ToA, ToT, and global
timestamp behavior.
