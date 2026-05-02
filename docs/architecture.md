# HERMES Architecture

The architecture notes are split by boundary under `docs/architecture/`.

- [General](architecture/general.md): overview, principles, and repository shape
- [State Model](architecture/state-model.md): Pydantic state-of-record boundary
- [Environment](architecture/environment.md): runtime paths, tool locations, and versions
- [Acquisition](architecture/acquisition.md): SERVAL and detector-facing workflows
- [TPX3 SPIDR Unpacker](architecture/unpacker.md): Rust decoder, Parquet output, native timestamps, and photon clustering
- [Analysis](architecture/analysis.md): analysis orchestration boundary
- [Artifacts](architecture/artifacts.md): generated data products and provenance
- [I/O](architecture/io.md): record persistence and path handling
- [Workflows](architecture/workflows.md): first acquisition-to-analysis workflow
- [Open Questions](architecture/open-questions.md): decisions still pending

Start with [General](architecture/general.md), then read the boundary document
for the part of the system you are working on.
