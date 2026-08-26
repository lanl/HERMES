# HERMES Acquisition Build Plan

Living plan for building the data-acquisition side of HERMES against a real
TPX3Cam driven through the ASI SERVAL server. We build and test one stage at a
time. Update the **Status** column and the **Notes** at the bottom of each stage
file as work lands.

Started 2026-08-25.

## How we work

- One stage per step. Each stage is small, ends with something we can run against
  the real camera, and does not start until the previous stage is tested.
- Read-only calls first, camera commands later. No measurement is taken until the
  connect/snapshot, destination, and calibration stages are all working.
- New code lives in `src/hermes/runner/acquisition/serval/` and follows the
  boundaries in `docs/architecture/acquisition.md`.
- Every stage has a small runnable example under `examples/acquisition/serval/`
  with its own `config.yaml`, run through `pixi`.

## Locked decisions

| Decision | Choice |
| --- | --- |
| HTTP client | `httpx` (add via pixi) |
| Plan location | this folder, `docs/plans/acquisition/`, tracked in git |
| SERVAL lifecycle | HERMES launches and stops the SERVAL server itself (`java -jar`) |
| Config shape | one `config` loaded from the config file (`ServalAcquisitionConfig`): `serval`, `calibration_files`, `detector_config` or `detector_config_file`, `run_timing`. No requested/applied duality |
| SERVAL jar location | in the config as `config.serval.program_path` |
| Detector config | inline `detector_config` or `detector_config_file` (JSON); the file wins when both are set |
| Run timing | `run_timing` (trigger mode, exposure, trigger period, trigger count) overrides the matching detector-config fields |
| Backend selection | the acquisition backend is chosen by `acquisition.mode`. SERVAL is one backend today; pymepix (or any other) will be added later as a second one. See "Adding another acquisition backend" below |
| SERVAL versions | one SERVAL backend parameterized by `serval.version`, not a model tree per version (the versions are ~95% the same). Launch flags and a few option checks depend on `major_version`. See "SERVAL versions" below |
| First testable stage | read-only connect + detector snapshot, no camera commands |

## Adding another acquisition backend

The acquisition side is built so a second backend (pymepix, or anything else) is
purely additive — no restructuring, nothing to undo. The mechanism is already in
place and already proven on the analysis side, which has two backends
(`HermesTpx3AnalysisState`, `EmpirAnalysisState`) selected the same way.

How it works: each backend has its own state model with a fixed `mode` field
(`ServalAcquisitionState` has `mode: Literal["serval"] = "serval"`). The record's
`acquisition` field is chosen from these by `mode` — a Pydantic discriminated
union, exactly like `AnalysisState` in `src/hermes/state/state.py`. A config that
says `acquisition.mode: serval` loads the SERVAL models with SERVAL parameters; a
future `acquisition.mode: pymepix` loads the pymepix models with pymepix
parameters. The wrong or an unknown mode fails with a clear error at load time.

The split is along "detector vs. driver". These describe the Timepix3 detector
itself and are backend-neutral, so both backends reuse them: `DetectorConfiguration`
(in `detector.py`), `CalibrationFiles` (the SoPhy `.bpc`/`.dacs`), and the run
timing (trigger mode, exposure, period, count). Backend-specific pieces stay on
that backend's model: for SERVAL that is `ServalServer` (the jar to launch, the
HTTP url, the `--tcpIp`/`--tcpPort` it forwards to the SPIDR), the SERVAL
dashboard, and `DestinationConfiguration` (SERVAL's file-writer settings). pymepix
would instead carry a direct SPIDR address (no jar, no HTTP server) and its own
status and output fields.

To add pymepix later:

1. Add `PymepixAcquisitionState` with `mode: Literal["pymepix"] = "pymepix"`,
   reusing `DetectorConfiguration`, `CalibrationFiles`, and the run timing.
2. Make `AcquisitionState` in `src/hermes/state/state.py` a discriminated union,
   mirroring `AnalysisState`:

   ```python
   AcquisitionState: TypeAlias = Annotated[
       ServalAcquisitionState | PymepixAcquisitionState,
       Field(discriminator="mode"),
   ]
   ```
3. Add the pymepix runner under `src/hermes/runner/acquisition/pymepix/` and route
   to it in `run_acquisition()` on `mode`.

Until a second backend actually exists, `AcquisitionState` stays the plain alias
to `ServalAcquisitionState` (a one-member discriminated union is not idiomatic).
The `mode` field is the contract that makes the switch above a one-line change.
One neutrality nit worth fixing when pymepix work starts: `ServalRunTiming` is
just detector timing with nothing SERVAL about it — rename it `RunTiming` so both
backends share it without a SERVAL-named import.

## SERVAL versions

SERVAL versions differ in the options they expose, so `serval.version` (e.g.
"3.3.0") declares which version HERMES is driving. We handle this with **one**
SERVAL model tree parameterized by version — not a model tree per version —
because the versions are ~95% the same. `ServalServer.major_version` parses the
leading number ("3.3.0" -> 3) and drives the differences below.

What actually differs between the copies on this machine (2.1.6 and 3.3.0),
from each jar's `--help` and 3.3.0's `release_notes.txt`:

- **Launch flags.** `--tcpIp`/`--tcpPort` were added in SERVAL 3.0; 2.x points at
  the camera with `--spidrNet` alone. 2.x had `--packetBuffers`/`--deadTime`,
  both gone by 3.3.0, which instead adds pipeline autotuning flags
  (`--udpReceivers`, `--fileWriters`, …, all autotuning by default) and
  `--releaseResources`.
- **REST models (breaking at v3.0.0).** `/detector/config` dropped
  `DetectorOrientation` (moved to `/detector/layout`); `/detector/layout` JSON
  changed and became PUT-able; `/detector/info` moved `ChipboardId` into `Boards`;
  a Corrections framework was added to destination Image channels.

How HERMES handles it:

1. **Launch flags follow the version.** When it starts SERVAL (stage 0), HERMES
   emits only the flags that `major_version` accepts: `--tcpIp`/`--tcpPort` for
   3.0+, `--spidrNet` for older. This is the runner's job; build it there.
2. **Construction rejects version-illegal options.** Already in `ServalServer`:
   setting `tcp_ip`/`tcp_port` against a declared 2.x `version` fails validation
   at `Workflow(record)` construction with a clear message (unset version is not
   gated — HERMES cannot tell). Add further gates here as concrete version-only
   options appear.
3. **Reads tolerate version drift.** The read-only API models the runner records
   from SERVAL (`DetectorInfo`/`Health`/`Layout`, `ServalDashboard`) relax to
   `extra="ignore"` so a server's moved or added fields do not crash the
   read/record path. Apply this in stage 1 when the read path is built and tested
   against a real server — not speculatively now. `DetectorConfiguration` stays
   strict (it is also user input, where a typo should fail); the one known 2.x-only
   field, `DetectorOrientation`, is handled there only if we ever read a 2.x config
   back.
4. **Observed vs declared.** After launch, the running server's version is at
   `dashboard.server.software_version`. If it disagrees with the declared
   `serval.version`, warn (stage 1).

## What already exists (foundation we build on)

- State models: `src/hermes/state/models/acquisition/serval.py`
  (`ServalAcquisitionState`, `ServalAcquisitionConfig`, `ServalServer`,
  `CalibrationFiles`, `ServalRunTiming`, `DestinationConfiguration`,
  `CalibrationState`, `ServalDashboard`, `ServalAcquisitionResult`) and
  `.../detector.py` (`DetectorConfiguration`,
  `DetectorSnapshot`, `DetectorInfo/Health/Layout`). All carry the correct SERVAL
  JSON aliases and validation, including the 40 V bias ceiling on the manual and
  the wider API range on the model.
- `RuntimeEnvironment` resolves the run directories
  (`src/hermes/state/models/environment.py`).
- `HermesRecord.acquisition` field is already wired (`src/hermes/state/state.py`).
- `hermes.state_service` mediates all record changes; `configure_logging`
  already opens the `acquisition.serval.jsonl` sink filtered on
  `domain="acquisition", backend="serval"` (`src/hermes/logging.py`).
- `Workflow` runs an acquisition-only record by calling `run_acquisition()`,
  which currently raises `NotImplementedError`
  (`src/hermes/workflows/workflow.py`).
- Launch pattern: a `config.yaml` builds a `HermesRecord` through
  `load_hermes_record_from_yaml`, then `Workflow(record).run()`, then
  `save_hermes_record_to_yaml`. See `examples/analysis/unpacking/run_unpacking.py`.

## What we build

- `src/hermes/runner/acquisition/serval/server.py` — launch, readiness, and stop
  for the SERVAL server process.
- `src/hermes/runner/acquisition/serval/client.py` — httpx client for the SERVAL
  HTTP endpoints, returning the typed models above.
- `src/hermes/runner/acquisition/serval/destination.py` — build and check the raw
  `.tpx3` destination.
- `src/hermes/runner/acquisition/serval/calibration.py` — save, hash, and load the
  SoPhy `.bpc` / `.dacs` files.
- `src/hermes/runner/acquisition/serval/run.py` — the run function the workflow
  calls; grows one stage at a time.
- Wire `Workflow.run_acquisition()` to call the run function.

## Stages

| Stage | File | Goal | Status |
| --- | --- | --- | --- |
| 0 | `stage-0-serval-control.md` | HERMES starts, readiness-checks, and stops SERVAL from `config.serval.program_path`; httpx client skeleton | Complete (tested on live camera 2026-08-25) |
| 1 | `stage-1-connect-snapshot.md` | Read-only connect + detector/SERVAL snapshot into the record | Not started |
| 2 | `stage-2-destination-calibration.md` | Configure raw `.tpx3` destination; load `.bpc`/`.dacs`; preflight checks | Not started |
| 3 | `stage-3-measurement.md` | Apply detector config; take a short real measurement; monitor; record output files | Not started |
| 4 | `stage-4-integration.md` | Hand raw files to unpacking; robustness; clean shutdown on failure | Not started |

## SERVAL facts we rely on

- Base URL `http://localhost:8080`. SERVAL runs on the same machine HERMES runs
  on, because HERMES launches it.
- `GET /dashboard` returns server, measurement, and detector summary. Readiness =
  this returns 200. Measurement done = `Measurement.Status == "DA_IDLE"`.
- `GET /detector/info`, `/detector/health`, `/detector/layout`,
  `/detector/config`; `PUT /detector/config`.
- `GET /server/destination`, `PUT /server/destination`.
- `GET /config/load?format=pixelconfig&file=<abs path>` for `.bpc`,
  `format=dacs` for `.dacs`. Load is a GET, not a PUT. The `file` path is resolved
  by the SERVAL host (here, the local machine).
- `GET /measurement/start`, `GET /measurement/stop`, `GET /server/shutdown`.

## References

- `docs/architecture/acquisition.md` — the 15-step SERVAL workflow and boundaries.
- `docs/architecture/workflows.md` — the acquisition-to-analysis flow.
- `docs/architecture/state-model.md` — `ServalAcquisitionState`,
  `ServalAcquisitionConfig`, and related models.
- `docs/architecture/logging_instructions.md` — what to log in the acquisition
  domain.
- `.agent/resources/20231023_ASIServer_TPX3_manual_V3.3.pdf` — SERVAL manual.
- `.agent/resources/Python Serval Toolkit v0.0.5/serval_toolkit/camera.py` — ASI's
  own client; the most concrete endpoint reference.
- `.scratch/old_bad_acquisition/tpx3Spider_lumacam.py` — the old prototype. Only
  its SERVAL setup sequence (`setup_tpx3spidr`, lines 21-66) and server launch
  (`thread_Serval`, lines 10-19) are relevant; EPICS, Zaber, and EMPIR parts are
  out of scope.
- `.scratch/old_bad_acquisition/settings_installation.py` — example jar and
  calibration paths from the old Linux machine (do not reuse the paths).
