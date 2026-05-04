# Acquisition

`src/hermes/acquisition/` owns runtime interaction with acquisition backends and
detector-facing APIs. Acquisition is mode-specific: each supported acquisition
mode should live in its own subpackage, with SERVAL implemented first and
PyMEPix and MCP2Hist left as future modes.

The acquisition package should provide focused client operations and small
runtime helpers. End-to-end orchestration belongs in `src/hermes/workflows/`.

The initial package shape should be:

## Acquisition Package Structure 

```text
src/
└── hermes/
    └── acquisition/
        ├── serval/
        │   ├── client.py          # SERVAL HTTP client operations
        │   ├── calibration.py     # helpers for loading SoPhy/ASI-generated BPC/DAC files into SERVAL
        │   ├── destination.py     # raw/image/preview destination helpers
        │   └── run.py             # start, stop, polling, and run snapshots
        ├── pymepix/               # reserved for a future PyMEPix acquisition mode
        └── mcp2hist/              # reserved for a future MCP2Hist acquisition mode
```

This layout is a target shape, not a requirement to create every file
immediately. Add modules when the first concrete workflow needs them.

Mode-specific code may use backend-native concepts directly. For example,
`hermes.acquisition.serval` may use ASI SERVAL endpoints and destination JSON
structures, while future `hermes.acquisition.pymepix` and
`hermes.acquisition.mcp2hist` packages can use their backend-native APIs and
concepts. The rest of the codebase should interact through HERMES models, state
services, and workflow functions.

The intended dependency direction is:

```text
hermes.workflows -> hermes.acquisition mode package
hermes.workflows -> hermes.state_service
hermes.state_service -> hermes.state
hermes.acquisition.serval -> SERVAL HTTP API
hermes.acquisition.pymepix -> PyMEPix API
hermes.acquisition.mcp2hist -> MCP2Hist API or file interface
```

`hermes.state_service` is the mutation, validation, approval policy, and audit
gate for the HERMES record. It should not own detector I/O or the full
acquisition procedure. The acquisition workflow should call
`hermes.state_service` whenever the run record needs to be initialized,
validated, updated, or persisted. Trusted workflow updates may be applied after
validation without per-change approval only when the state service approval
bypass setting allows it.

## Detector And SERVAL Boundary

TPX3Cam detector state is the durable description of the physical detector and
the detector configuration applied for a run. It should include hardware
identity, chip identity, layout, health readings, and detector configuration
values needed to reproduce or audit acquisition. Reproducibility-critical chip
configuration such as `PixelConfig` and DAC settings remains detector-owned
state, either inline when reasonably small or through `ExternalPayloadRef` when
the value is too large for the record or state log.

SERVAL state is the durable description of the acquisition backend session. It
should include SERVAL URL and version, `/dashboard` snapshots, destination
configuration, measurement lifecycle state, `/config/load` activity, polling
results, and produced artifacts. `/dashboard` is SERVAL-owned state because it
combines server, measurement, and detector summary fields and is designed as a
fast backend status endpoint. Detector summaries from `/dashboard` may be copied
into detector state only when they are confirmed by detector-specific endpoints
such as `/detector/info`, `/detector/health`, `/detector/layout`, or
`/detector/config`.

Acquisition code may read and write detector-facing SERVAL endpoints, but it
returns structured snapshots and results to the workflow. Durable HERMES record
updates still flow through `hermes.state_service`.

## Shared Responsibilities

Each acquisition mode package should expose the operations needed by workflows to
run that mode safely:

- connect to, initialize, or validate the external acquisition backend
- apply mode-specific acquisition configuration
- configure output destinations or data streams
- configure camera triggers, exposure timing, and other acquisition parameters
- snapshot backend, detector, configuration, layout, and health information
- emit structured acquisition log events for backend communication, snapshots,
  polling, warnings, and failures
- start and stop measurements
- poll acquisition status
- collect final acquisition status and artifact metadata for the workflow to
  record

Acquisition mode packages should return structured data that can be placed into
the HERMES record by the workflow through `hermes.state_service`. They should not
directly mutate the state record.

## SERVAL Mode

`src/hermes/acquisition/serval/` owns interaction with ASI SERVAL for TPX3Cam
acquisition.

Expected SERVAL responsibilities:

- connect to SERVAL
- read `/dashboard`
- read detector info, detector health, detector layout, and detector
  configuration
- read and write `/server/destination`
- load chip calibration files through `/config/load`, including `.bpc` pixel
  configuration and `.dacs` DAC files generated by SoPhy or supplied by ASI
- upload `/detector/config`
- configure SERVAL-native destinations for `Raw`, `Image`, and `Preview`
  outputs
- start and stop measurements through `/measurement/start` and
  `/measurement/stop`
- poll acquisition status through `/dashboard`
- collect final acquisition status and artifact metadata for the workflow to
  record

SERVAL destination configuration should preserve the `/server/destination`
payload shape: top-level `Raw` and `Image` channel lists, plus an optional
`Preview` object with `ImageChannels` and `HistogramChannels`. Destination
`Base` values should remain URI strings because `file:`, `http:`, and `tcp:`
destinations are all valid and are interpreted from the SERVAL host context.

## Calibration Boundary

HERMES should not generate detector calibration files. Chip calibration is done
outside HERMES in SoPhy, which produces `.dacs` and `.bpc` files. HERMES should
accept those files as acquisition-plan inputs, validate that the paths are
present and usable, record their provenance in the HERMES record, and provide
them to SERVAL through `/config/load`.

Calibration inputs should be treated as durable run configuration. The record
should capture the requested `.bpc` and `.dacs` paths, applied calibration status,
file sizes and hashes when practical, and any SERVAL response summaries. If the
calibration payloads are captured as state values rather than artifact
references, large values may be externalized through `hermes.state_service` and
represented by `ExternalPayloadRef`.

SERVAL loads calibration files with `GET /config/load?format=<format>&file=<filepath>`.
The relevant formats for TPX3Cam calibration are `pixelconfig` for `.bpc` files
and `dacs` for DAC JSON or `.dacs` files. `PUT` is not supported for
`/config/*`. The `file` value should be recorded as a string because the path is
resolved by the SERVAL host and may not be local to the HERMES process. The
HERMES record should keep both the HERMES-side `ArtifactRef` for the provided
file and the SERVAL-side load request/result, including bounded response text or
summary data.

SoPhy and SERVAL should not be run against the detector at the same time. A
HERMES acquisition workflow may require the user to provide existing SoPhy output
files before it configures SERVAL.

## SERVAL Logging

SERVAL communication belongs in the acquisition logging domain, not as free-form
notes in the HERMES state record. Use the shared Loguru configuration and bind
events with `domain="acquisition"` and `backend="serval"`.

SERVAL acquisition log events should include:

- measurement ID and run ID or run number
- workflow step
- acquisition mode
- SERVAL URL
- request ID
- HTTP method and endpoint path
- status code, elapsed time, and error text when relevant
- bounded request and response summaries
- dashboard, health, destination, and detector configuration summaries
- artifact paths or artifact IDs when communication creates files

The HERMES state record should contain durable run facts, including requested and
applied detector configuration, destination configuration, detector snapshots,
artifact references, final status, and PixelConfig or DAC settings if needed for
reproducibility. If PixelConfig or DAC settings are captured in the state record,
acquisition logs should reference them by state path, length, digest, or
`ExternalPayloadRef` rather than logging the full payload.

Do not log raw image data, decoded event tables, large raw detector payloads, or
large stdout/stderr streams. Store large data products as artifacts and log their
paths, sizes, hashes, formats, and concise summaries.

## SERVAL TPX3 Acquisition Workflow

The first concrete acquisition workflow should be narrow and explicit. It should
write raw `.tpx3` data, optionally expose previews, and produce enough state and
logs to reproduce or debug the run.

1. Create an acquisition plan.
   Include measurement metadata, SERVAL URL, trigger mode, trigger count,
   exposure timing, calibration file paths, output destinations, preview
   settings, and expected artifact names.
2. Resolve and create run directories.
   Directory defaults should come from the environment model, such as
   `working_dir`, `data_dir`, `raw_data_dir`, `log_dir`, and `preview_dir`.
   Models should validate paths, but workflow or I/O code should create the
   directories.
3. Initialize the HERMES record.
   Record the plan, resolved paths, requested acquisition mode, and initial run
   status before touching detector state.
4. Connect to SERVAL.
   SERVAL may already be running, or HERMES may start it if that becomes an
   explicit supported workflow. Verify connectivity with `/dashboard` and record
   the SERVAL software version and detector type.
5. Snapshot initial SERVAL and detector state.
   Read `/dashboard`, `/detector/info`, `/detector/health`,
   `/detector/layout`, `/detector/config`, and `/server/destination`. Durable
   detector fields needed for reproducibility, such as PixelConfig and DAC
   settings, should be recorded in the HERMES record rather than duplicated in
   acquisition logs. Large configuration fields may be externalized through
   `hermes.state_service` and represented by `ExternalPayloadRef`.
6. Validate pre-run conditions.
   Confirm a detector is present, the measurement status is idle, health
   readings are within configured limits, output paths are usable from the
   SERVAL host, disk space is sufficient, and the requested acquisition plan is
   compatible with the detected hardware.
7. Load chip calibration files.
   Load the user-provided `.bpc` pixel configuration and `.dacs` DAC files with
   SERVAL `/config/load`. These files are generated outside HERMES by SoPhy or
   supplied by ASI; HERMES is responsible for validating, recording, and handing
   them to SERVAL.
8. Apply detector acquisition configuration.
   Update `/detector/config` with the run-specific trigger mode, trigger count,
   exposure time, trigger period, bias settings, TDC settings, and any other
   explicitly modeled detector options.
9. Configure SERVAL destinations.
   For the first workflow, configure `Raw` output to write `.tpx3` files under
   `raw_data_dir`. Add `Preview` output only when live monitoring is needed.
   Remember that `file:` destinations are resolved on the machine running
   SERVAL, which may be different from the HERMES client host.
10. Read back and validate applied configuration.
    Re-read `/detector/config` and `/server/destination`, compare them with the
    requested plan, and update the HERMES record with the applied values. For
    large fields, record the durable value once in state or as an external state
    payload reference, then use summaries, digests, or state paths in operational
    logs.
11. Start measurement.
    Call `/measurement/start` only after the applied configuration and
    destinations have been validated.
12. Monitor acquisition.
    Poll `/dashboard` until `Measurement.Status` returns to `DA_IDLE` or the
    workflow fails, times out, or is explicitly stopped. Track frame count,
    dropped frames, elapsed time, time left, event rates, notifications, and
    health changes.
13. Snapshot final acquisition state.
    Read final `/dashboard` and `/detector/health` data. Record completion
    status, counts, warnings, errors, and any stop reason.
14. Discover and record artifacts.
    Locate raw `.tpx3` files and any preview or image files, then record paths,
    sizes, timestamps, and other useful metadata in the HERMES record.
15. Persist the acquisition record.
    Save the updated HERMES record before handing raw artifacts to unpacking or
    analysis workflows.

Each major step should produce structured Loguru events. Workflow progress should
use the `workflow` domain. SERVAL communication and polling should use the
`acquisition` domain with `backend="serval"`. State mutations should go through
`hermes.state_service` and be logged by `StateLogger`.

## PyMEPix Mode

`src/hermes/acquisition/pymepix/` is reserved for a future PyMEPix acquisition
mode. Do not build a broad PyMEPix abstraction until there is a concrete PyMEPix
workflow and known state requirements.

When that workflow exists, this package should follow the same boundary as
SERVAL:

- keep PyMEPix-specific API calls inside `hermes.acquisition.pymepix`
- return structured snapshots, configuration results, acquisition status, and
  artifact metadata to the workflow
- update the HERMES record only through `hermes.state_service`
- add PyMEPix-specific state models under `hermes.state.models.acquisition`

## MCP2Hist Mode

`src/hermes/acquisition/mcp2hist/` is reserved for a future MCP2Hist acquisition
mode. Do not build a broad MCP2Hist abstraction until there is a concrete
MCP2Hist workflow and known state requirements.

When that workflow exists, this package should follow the same boundary as
SERVAL:

- keep MCP2Hist-specific API calls or file-interface logic inside
  `hermes.acquisition.mcp2hist`
- return structured snapshots, configuration results, acquisition status, and
  artifact metadata to the workflow
- update the HERMES record only through `hermes.state_service`
- add MCP2Hist-specific state models under `hermes.state.models.acquisition`

## Boundary Notes

- Acquisition code should wrap backend operations such as SERVAL HTTP requests,
  future PyMEPix API calls, or future MCP2Hist calls/file operations, and should
  emit acquisition-domain log events.
- Workflow code should decide the order of operations, call `hermes.state_service`, and
  coordinate artifact discovery.
- State models should remain durable Pydantic records. They should not create
  directories, call SERVAL, or mutate detector state.
- `hermes.state_service` should validate and apply changes to the HERMES record, but it
  should not directly call detector APIs.
- Operational logs should summarize or reference large durable state fields such
  as PixelConfig. They should not duplicate those full payloads.
