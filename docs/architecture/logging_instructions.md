# Logging Design (Loguru)

HERMES uses Loguru for structured run logs. Logging should support two related
but separate needs:

- reconstruct and audit changes to the durable HERMES record
- debug acquisition, analysis, and workflow behavior without stuffing every
  operational detail into the state record

The state record remains the durable source of truth for a run. Logs explain how
that state was reached and what happened around it.

## Key Rule

Loguru exposes one global `logger`. Configure it exactly once during application
startup. Domain-specific loggers such as `StateLogger`, `AcquisitionLogger`, and
`AnalysisLogger` are thin wrappers around `logger.bind(...)`; they must not call
`logger.add(...)`.

It is acceptable for the single startup configuration function to call
`logger.add(...)` multiple times when adding filtered sinks. It is not acceptable
for individual modules, services, GUI components, request handlers, or wrappers
to configure sinks themselves.

## Log Domains

Use separate logging domains instead of separate Loguru instances:

```text
state
  canonical audit trail for HERMES record changes

workflow
  high-level run progress and step transitions

acquisition
  detector/backend communication and acquisition runtime detail

analysis
  unpacking, processing, external tool execution, and analysis runtime detail

app
  general application diagnostics that do not belong to a run-specific domain
```

A practical run directory layout is:

```text
working_dir/
└── logs/
    ├── state.jsonl
    ├── workflow.jsonl
    ├── acquisition.serval.jsonl
    ├── analysis.jsonl
    └── app.log
```

## Startup Configuration

Logging is initialized once at application startup:

```python
from pathlib import Path
from loguru import logger


def _domain_filter(domain: str):
    return lambda record: record["extra"].get("domain") == domain


def configure_logging(log_dir: Path) -> None:
    logger.remove()

    logger.add(
        log_dir / "state.jsonl",
        serialize=True,
        enqueue=True,
        rotation="50 MB",
        retention="90 days",
        filter=_domain_filter("state"),
    )
    logger.add(
        log_dir / "workflow.jsonl",
        serialize=True,
        enqueue=True,
        rotation="50 MB",
        retention="90 days",
        filter=_domain_filter("workflow"),
    )
    logger.add(
        log_dir / "acquisition.serval.jsonl",
        serialize=True,
        enqueue=True,
        rotation="100 MB",
        retention="90 days",
        filter=lambda record: (
            record["extra"].get("domain") == "acquisition"
            and record["extra"].get("backend") == "serval"
        ),
    )
    logger.add(
        log_dir / "analysis.jsonl",
        serialize=True,
        enqueue=True,
        rotation="100 MB",
        retention="90 days",
        filter=_domain_filter("analysis"),
    )
    logger.add(
        log_dir / "app.log",
        enqueue=True,
        rotation="20 MB",
        retention="30 days",
    )
```

The exact rotation and retention values can change, but the configuration should
remain centralized.

## Common Context

Every run-specific log event should include enough fields to correlate records
across domains:

```text
measurement_id
run_id or run_number
workflow_step
acquisition_mode
analysis_mode, when relevant
state_version or change_id, when relevant
artifact_id, when relevant
request_id, for backend calls
```

Bind common context once and pass domain wrappers into services:

```python
state_log = logger.bind(domain="state", measurement_id=measurement_id, run_id=run_id)
workflow_log = logger.bind(domain="workflow", measurement_id=measurement_id, run_id=run_id)
serval_log = logger.bind(
    domain="acquisition",
    backend="serval",
    measurement_id=measurement_id,
    run_id=run_id,
)
analysis_log = logger.bind(domain="analysis", measurement_id=measurement_id, run_id=run_id)
```

## StateLogger

`StateLogger` records the audit trail for HERMES record mutation.

Responsibilities:

- log proposed, approved, applied, rejected, and failed changes
- log state load and save events
- log validation failures tied to state paths
- include state paths, change IDs, status, proposer, approver, timestamps, and
  concise value summaries
- avoid configuring Loguru
- avoid mutating state

For small scalar or bounded structured values, state logs may include old and new
values. For large fields, state logs should include a summary, digest, size, and
state path instead of duplicating the full payload.

## WorkflowLogger

`WorkflowLogger` records high-level run progress.

Responsibilities:

- log step start, step completion, step failure, retry, timeout, abort, and
  cleanup events
- include current workflow step and relevant artifact or state paths
- provide the coarse timeline of a measurement

Workflow logs should answer: "Where was the run in the acquisition-to-analysis
procedure?"

## AcquisitionLogger

`AcquisitionLogger` records detector/backend communication and runtime detail.

For SERVAL, it should log structured events for:

- HTTP request start and completion
- method, endpoint path, status code, elapsed time, and request ID
- connection events and SERVAL version
- detector snapshots, health summaries, and dashboard summaries
- destination upload and readback summaries
- measurement start, stop, polling, timeout, and failure events
- warnings, notifications, dropped-frame counts, event-rate summaries, and final
  acquisition status

Acquisition logs should answer: "What happened while HERMES talked to the
acquisition backend?"

## AnalysisLogger

`AnalysisLogger` records unpacking and analysis runtime detail.

Responsibilities:

- log external tool start and completion
- include command identity, tool version, input artifact IDs, output artifact
  IDs, exit code, elapsed time, and bounded stdout/stderr summaries
- log analysis configuration summaries and metrics
- log failures with enough context to reproduce the command

Analysis logs should answer: "What happened while HERMES processed acquisition
artifacts?"

## State Record vs Logs

The HERMES record should contain durable run facts:

- measurement metadata
- resolved environment and output paths
- requested and applied acquisition configuration
- detector snapshots needed for provenance
- PixelConfig, if needed for reproducibility, recorded once under detector state
- artifact references, sizes, hashes, and summary metrics
- final acquisition and analysis status

Operational logs should contain process detail:

- backend request/response metadata
- polling observations
- workflow transitions
- external command execution summaries
- warnings, retries, failures, and timing

Do not duplicate large durable state payloads into operational logs. If
PixelConfig is part of the state record, acquisition logs should reference it by
state path, length, and digest rather than logging the full PixelConfig. State
change logs should follow the same rule for large fields.

## Payload Policy

Never write the following directly into logs or the HERMES record:

- raw image data
- decoded event tables
- large image stacks
- generated plot binaries
- raw detector data payloads
- large stdout or stderr streams

Store large data products as artifacts on disk and record references, sizes,
hashes, formats, and summaries. Logs may include bounded excerpts or summaries
when useful, but not full payloads.

## Anti-Patterns

Avoid:

- calling `logger.add(...)` outside centralized startup configuration
- creating sinks inside `StateLogger`, `AcquisitionLogger`, `AnalysisLogger`, or
  workflow code
- logging full SERVAL `PixelConfig` payloads in acquisition logs
- logging raw images, decoded event tables, or large stdout/stderr
- treating backend communication logs as state record fields
- relying on unstructured free-text messages when structured fields are known

## Summary

```text
Configure Loguru once.
Use domain wrappers for state, workflow, acquisition, and analysis.
Write each domain to filtered structured sinks.
Keep durable state in the HERMES record.
Keep operational detail in domain logs.
Reference large payloads by path, size, hash, and state path.
```
