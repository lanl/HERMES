# Stage 1 — Read-only connect and snapshot

**Status:** Not started (needs stage 0)

**Goal:** With SERVAL running, read the server and detector state and record it in
the HERMES record. This is the first stage that talks to the camera, and it only
reads — no configuration is written, no measurement is taken. It proves the whole
path from `config.yaml` to a saved record works against real hardware, safely.

## Work

1. **Client reads** — extend `serval/client.py`:
   - `get_detector_info() -> DetectorInfo`
   - `get_detector_health() -> DetectorHealth`
   - `get_detector_layout() -> DetectorLayout`
   - `get_detector_config() -> DetectorConfiguration`
   - `get_destination() -> DestinationConfiguration`

   Version tolerance: set `extra="ignore"` on the read-only models recorded here
   (`DetectorInfo`/`Health`/`Layout`, `ServalDashboard`) so a server on a different
   version (moved or added JSON fields, e.g. 2.x's `DetectorOrientation`) does not
   crash the read. Leave `DetectorConfiguration` strict — it is also user input.
   See the README's "SERVAL versions" section. Test this against the real server;
   do not change it blindly.

2. **Run function** — new `src/hermes/runner/acquisition/serval/run.py` with
   `run_serval_acquisition(state_manager)`. For this stage it does only:
   - Ensure SERVAL is running: if `config.serval.program_path` is set and the
     server does not answer, start it and wait until ready (stage 0 helpers).
   - Read `/dashboard`; record it into the state's `dashboard` field (the software
     version is then at `dashboard.server.software_version`).
   - Read the four detector endpoints into a `DetectorSnapshot` and record it as
     `initial_detector_snapshot`.
   - Read `/server/destination` and record the current destination.
   - Basic presence checks: a detector is attached (`/dashboard` detector is not
     null, or `/detector/info` reports at least one chip) and the measurement
     status is `DA_IDLE`. Log a clear warning if not; do not fail the read.
   - Apply every record change through `hermes.state_service`.

3. **Wire the workflow.** Replace the `NotImplementedError` in
   `Workflow.run_acquisition()` (`src/hermes/workflows/workflow.py`) with a call
   to `run_serval_acquisition(self._state_manager)`. `Workflow.run()` already
   routes an acquisition-only record to `run_acquisition()`.

4. **Example** — `examples/acquisition/serval/connect_and_snapshot.py` plus
   `connect_and_snapshot.yaml`, mirroring the analysis examples: load the record,
   run the workflow, save the final record, print a short summary (chip id,
   temperatures, layout size, trigger mode).

## Test against the real machine

- Run the example against the connected camera.
- Confirm the saved `HERMES_record.yaml` holds the detector snapshot (chip
  identity, temperatures, bias reading, layout, current detector config) and the
  SERVAL version and dashboard.
- Confirm `acquisition.serval.jsonl` shows one read event per endpoint and that
  no `PUT` or `/measurement/*` call was made.

## Notes / findings

(update as we build and test)
