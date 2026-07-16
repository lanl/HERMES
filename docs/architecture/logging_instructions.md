# Logging Design (Loguru)

HERMES uses Loguru for structured run logs. Logging should support two related
but separate needs:

- reconstruct and audit changes to the durable HERMES record
- debug acquisition, analysis, and workflow behavior without stuffing every
  operational detail into the state record

The state record remains the durable source of truth for a run. Logs explain how
that state was reached and what happened around it.

## Key Rule

Loguru exposes one global `logger`. Configure it exactly once during HERMES
process startup. Domain-specific loggers such as `StateLogger`, `AcquisitionLogger`, and
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
  canonical audit trail for the initial HERMES record and later record changes

workflow
  high-level run progress and step transitions

acquisition
  detector/backend communication and acquisition runtime detail

analysis
  unpacking, processing, external tool execution, and analysis runtime detail
```

Do not define a catch-all `app` domain or unfiltered `app.log` sink. A future web
GUI launched for HERMES may add a dedicated GUI logging domain and filtered sink,
but only when that GUI workflow exists and through the same centralized Loguru
configuration.

A practical run directory layout is:

```text
working_dir/
└── logs/
    ├── hermes-record.initial.yaml  # initial HermesRecord snapshot
    ├── hermes-record.final.yaml    # final HermesRecord snapshot
    ├── state.jsonl                 # live log with all appended state events
    ├── acquisition.serval.jsonl    # acquisition logs filtered for acquisition backend
    ├── workflow.jsonl              # workflow logs filtered for workflow domain  
    ├── analysis.jsonl              # analysis logs filtered for analysis domain  
    └── payloads/                   # all external payload files referenced by the state record and state log
        ├── detector_pixel_config_<hash>.bpc
        └── detector_dacs_<hash>.json
```

## Startup Configuration

Logging is initialized once at HERMES process startup:

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
input_file or output_path, when relevant
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

- log the initial `HermesRecord`
- log proposed, approved, applied, rejected, and failed changes
- log state load and save events
- log validation failures tied to state paths
- include state paths, change IDs, status, proposer, origin, approver or
  approval-bypass marker, timestamps, and concise value summaries
- avoid configuring Loguru
- avoid mutating state

For small scalar or bounded structured values, state logs may include old and
new values inline. Large durable values, such as PixelConfig or DAC structures,
should be logged inline only when that is practical. Otherwise, the state value
should be externalized first and the state log should record the resulting
`ExternalPayloadRef`.

## WorkflowLogger

`WorkflowLogger` records high-level run progress.

Responsibilities:

- log step start, step completion, step failure, retry, timeout, abort, and
  cleanup events
- include current workflow step and relevant input, output, or state paths
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
- calibration file load request and result summaries for SERVAL `/config/load`
- measurement start, stop, polling, timeout, and failure events
- warnings, notifications, dropped-frame counts, event-rate summaries, and final
  acquisition status

Acquisition logs should answer: "What happened while HERMES talked to the
acquisition backend?"

## AnalysisLogger

`AnalysisLogger` records unpacking and analysis runtime detail.

Responsibilities:

- log external tool start and completion
- include command identity, tool version, input file paths, output directory or
  file paths, exit code, elapsed time, and bounded stdout/stderr summaries
- log analysis configuration summaries and metrics
- log failures with enough context to reproduce the command

Analysis logs should answer: "What happened while HERMES processed raw TPX3,
decoded event, or image files?"

## State Record vs Logs

The HERMES record should contain durable run facts:

- measurement metadata
- resolved environment and output paths
- requested and applied acquisition configuration
- detector snapshots needed for provenance
- SERVAL calibration load requests and results for `.bpc` and `.dacs` files
- PixelConfig and DAC settings, if needed for reproducibility, recorded once
  under detector state and recorded again only if changed
- raw TPX3, image, decoded output, summary, and plot paths with sizes, hashes,
  and summary metrics where applicable
- final acquisition and analysis status

Operational logs should contain process detail:

- backend request/response metadata
- polling observations
- workflow transitions
- external command execution summaries
- warnings, retries, failures, and timing

Do not duplicate large durable state payloads into operational logs. If
PixelConfig or DAC settings are part of the state record, acquisition logs should
reference them by state path, length, digest, or `ExternalPayloadRef` rather than
logging the full payload.

State logs are different: they record state values. If a large value is stored
inline in the state, it may appear in the initial state log or in the change log
when that field changes. If the value is externalized, the state log records the
`ExternalPayloadRef` instead of the full payload.

The state service should decide whether to store a value inline or externalize
it before applying and logging the state change.

## Payload Policy

Never write the following directly into logs or the HERMES record:

- raw image data
- decoded event tables
- large image stacks
- generated plot binaries
- raw detector data payloads
- large stdout or stderr streams

Store decoded tables, images, plots, and other large outputs in files or
directories on disk. Record their paths, sizes, hashes, formats, and summaries.
Logs may include bounded excerpts or summaries when useful, but not full file
contents.

Large configuration values are handled differently. If they are needed for
reproducibility, they are saved state values and may be stored inline or in files
under `logs/payloads/` referenced by `ExternalPayloadRef`. HERMES should not
define a separate `state_payload_dir`.

## Anti-Patterns

Avoid:

- calling `logger.add(...)` outside centralized startup configuration
- creating sinks inside `StateLogger`, `AcquisitionLogger`, `AnalysisLogger`, or
  workflow code
- logging full SERVAL `PixelConfig` or DAC payloads in acquisition logs
- logging raw images, decoded event tables, or large stdout/stderr
- treating backend communication logs as state record fields
- adding a catch-all `app` logging domain or unfiltered `app.log` sink
- relying on unstructured free-text messages when structured fields are known

## Summary

```text
Configure Loguru once.
Use domain wrappers for state, workflow, acquisition, and analysis.
Write each domain to filtered structured sinks.
Keep durable state in the HERMES record.
Keep operational detail in domain logs.
Use ExternalPayloadRef for large state-owned payload files.
Reference large operational payloads by path, size, hash, and state path.
```
