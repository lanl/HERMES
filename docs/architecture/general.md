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
- [Artifacts](artifacts.md)
- [I/O](io.md)
- [Workflows](workflows.md)
- [Open Questions](open-questions.md)

## Design Principles

- Start with one working acquisition-to-analysis workflow before adding broad
  abstractions.
- Keep state explicit, typed, serializable, and testable.
- Treat Pydantic models as durable records, not as runtime service objects.
- Keep detector I/O, file decoding, and analysis behavior outside the models.
- Store large data products as artifacts on disk and reference them from the
  state model.
- Keep generated artifacts, caches, raw detector data, and build products out of
  version control.
- Use Loguru for structured logs around acquisition, decoding, analysis, and
  state transitions.
- Prefer Pixi-managed Python environments and focused pytest coverage when
  Python code is added.

## Proposed Repository Layout

```text
Cargo.toml
crates/
  hermes-tpx3-spidr/
    Cargo.toml
    src/
      lib.rs
      main.rs
    tests/

src/
  hermes/
    acquisition/
      serval_client.py
      workflows.py
    analysis/
      tpx3_spidr.py
      workflows.py
    io/
      paths.py
      records.py
    models/
      acquisition.py
      analysis.py
      artifacts.py
      detector.py
      environment.py
      enums.py
      record.py
    logging.py

tests/
docs/
  architecture.md
  architecture/
    general.md
    state-model.md
    environment.md
    acquisition.md
    unpacker.md
    analysis.md
    artifacts.md
    io.md
    workflows.md
    open-questions.md
  decisions/

.agent/
  resources/
  examples/

.scratch/
```

This layout is a target shape, not a requirement to create every file
immediately. Add modules only when the first workflow needs them.

## External References

Vendor manuals, SERVAL documentation, and example unpacking code belong under
`.agent/resources/` and `.agent/examples/`. Agents and developers should consult
those files when implementing TPX3Cam, SPIDR, SERVAL, TDC, ToA, ToT, and global
timestamp behavior.
