HERMES — AI Assistant Instructions
==================================

Repository Overview
-------------------
- Primary project location: `src/hermes/`
- Python targets 3.10+, uses Pydantic v2, and prefers pure functions with explicit dependencies.
- C++ Timepix utilities live under `src/chermes/`; invoke `pixi run build-cpp` (Makefile backed) for builds.
- Generated artifacts, notebooks, and large binaries must not be committed.

Acquisition Stack
-----------------

**Models** (`src/hermes/acquisition/models/`)
- **Read-only** unless a maintainer explicitly requests changes: `common.py`, `detector.py`, `dashboard.py`, `destinations.py`, `measurement.py`.
- Inherit from `HermesBaseModel` variants defined in `common.py`; keep aliases matching Serval JSON keys and internal names snake_case with unit suffixes.
- No network/file I/O, logging, or orchestration; validation only with strict config (`extra="forbid"`, `ser_json_inf_nan=False`, `validate_assignment=True`).
- Centralize enums/type aliases in `common.py`; re-export public types via package `__init__.py`.

**Services** (`src/hermes/acquisition/services/`)
- Encapsulate side-effecting work (HTTP, filesystem, hardware). Keep modules single-responsibility and lean on dependency injection.
- Accept and return Pydantic models; convert raw Serval responses into models as soon as practical and surface `.model_dump(by_alias=True)` payloads when sending.
- Use `loguru` for logging via project utilities; avoid direct `print`. Guard retry/timeout logic and document assumptions about Serval firmware versions.
- Do not import controllers; expose service interfaces that controllers can orchestrate.

**Controllers** (`src/hermes/acquisition/controllers/`)
- Coordinate services and models; no direct HTTP calls—delegate to services. Maintain deterministic flows suitable for unit testing (mock services).
- Keep async usage explicit; document expected side-effects (start/stop acquisition, calibration sequences).
- Reject unknown kwargs and validate inputs with existing models before invoking services.

**Factories & Registries** (`src/hermes/acquisition/factories/`)
- Provide construction helpers for services/controllers; centralize wiring so scripts/tests can swap implementations.
- Avoid hidden global state; prefer passing dependencies explicitly or via lightweight registries.

**Supporting Utilities**
- Prefer placing acquisition-domain helpers in dedicated modules under `acquisition/utils` (if present) rather than inside models/services.
- Shared cross-layer helpers belong in `src/hermes/utils/` with clear separation between logging, config loading, and general utilities.

Contribution Guardrails
-----------------------
- Preserve SI units (`*_s`, `*_ns`, `*_c`) and describe them in `Field(..., description="...")` when adding new fields.
- Keep `__init__.py` files empty; import exports explicitly to avoid circular dependencies.
- Document Serval manual references in docstrings when modeling new payloads; cite section/table where possible.
- Consult a maintainer before altering acquisition models or shared enums
- All `__init__.py` files must remain empty and imports must be explicit to avoid circular dependencies.

Python Patterns
---------------
- Prefer precise literals/enums over wide `Union`s; raise `ValueError` with actionable context in validators.
- Use Pydantic validators for cross-field checks and `model_dump(by_alias=True)` before emitting JSON.
- Keep orchestration, I/O, and logging outside models; services may perform side-effects but must remain testable (inject transport/session objects).

C++ Notes
---------
- Build with `pixi run build-cpp`; keep compatibility with the existing `Makefile` and C++17 standard.
- Place new headers in `src/chermes/inc` and sources in `src/chermes/src`; ensure the Makefile picks them up.

Testing Expectations
--------------------
- Python tests live under `tests/unit/hermes/`; extend coverage alongside new functionality.
- Acquisition model tests should verify alias round-trips, enum/numeric bounds, rejection of unknown fields, and immutability (`HermesImmutableModel`).
- Service/controller tests must isolate external dependencies (mocks/fakes) and cover error paths, retries, and telemetry handling.
- C++ changes require rebuildable artifacts via `pixi run build-cpp`; add sanity checks or sample data runs where feasible.

Development Workflow
--------------------
- Use Pixi (`pixi install`, `pixi shell`) to manage dependencies and Python versions.
- Run `pixi run lint` (Ruff) and `pixi run format` before sending patches.
- Coordinate changes to docs in `docs/` when behavior or configuration steps evolve.

Support References
------------------
- Serval Manuals (v2.1.5, v3.3) define payload schemas mirrored by acquisition models; keep implementation aligned with documented tables/examples.
- Review existing controllers/services before adding new interfaces to maintain consistency.

This instruction file is the canonical reference for AI assistants working on HERMES.