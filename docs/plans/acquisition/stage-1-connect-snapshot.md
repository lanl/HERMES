# Stage 1 — Read-only connect and snapshot

**Status:** Done — verified end-to-end against the live camera (2026-08-26).
`get_destination`, the `run.py` run function, the workflow wiring, and the
3-line-`Workflow` example are in place and record the snapshot into the saved
`HERMES_record.yaml`.

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

- **Launching SERVAL alone does not connect the camera.** With no camera-address
  flag, `/dashboard` reports `Detector: null` and every `/detector/*` read
  returns 409 "Not connected. Please connect to a detector." SERVAL must be told
  the camera address at launch (or autodiscover it over a correctly-configured
  interface). On this Mac autodiscovery did not find the camera, so we pass the
  address explicitly.
- **Launch flags must use the `--flag=value` form.** `--tcpIp=192.168.100.10`
  works; the space-separated `--tcpIp 192.168.100.10` makes SERVAL log
  "Argument to 'tcpIp' is not provided." and never open its HTTP port. Fixed
  `_build_launch_command` (stage 0) to emit the equals form; tests updated.
- **The camera handshake takes several seconds after the HTTP server is up.**
  SERVAL answers `/dashboard` within ~1 s, but `Detector` stays null for ~6 s
  while the SPIDR link comes up. Added `wait_until_detector_connected` (polls
  `/dashboard` until `Detector` is non-null) so reads only run once the camera
  is connected. A "Connection to …:50001 failed" INFO line in SERVAL's own log
  during startup is non-fatal — the detector still enumerates over port 50000.
- **This machine's camera:** en10 is `192.168.100.1/24` (10 GB link, mtu 9000),
  the SPIDR/camera is at `192.168.100.10:50000`. `/detector/info` reports
  chipboard `2000164`, one active chip `W0062_B09`.
- **Read models validated cleanly under the strict schema on the real 3.3.0
  server** — `/dashboard` and all four `/detector/*` responses parsed with no
  extra fields. So the planned `extra="ignore"` relaxation was **deferred**: on
  this target it would guard against drift that does not exist, and the global
  rule is to keep it simple and not add speculative tolerance. Revisit if a 2.x
  camera or a drifting minor version is ever read; `DetectorConfiguration` stays
  strict regardless (it is user input).
- **`/server/destination` returns 409 "Destination is not set." on a fresh
  server.** Nothing has told SERVAL where to write yet on a read-only connect,
  so the destination read fails with 409. `run_serval_acquisition` catches the
  `ServalClientError`, logs a warning, and leaves `destination` unrecorded
  (the field is optional) rather than failing the whole read. The client stays
  thin (still raises on any non-200); the tolerance lives in the run function.
- **A fresh server's `/dashboard` has `Measurement: null`.** No measurement has
  been armed, so there is no measurement object and no status. That is the safe
  idle state for a read-only connect, so the presence check only warns when a
  measurement is actually in progress (status not in `None`/`DA_IDLE`), not when
  it is simply absent. Earlier the test fixture showed `DA_IDLE`; a truly fresh
  launch shows null.
- **The camera currently attached reports chipboard `2000188`, chip
  `W0082_J04` (id 21066)** — a different board/chip than the `2000164` /
  `W0062_B09` noted earlier. `NumberOfChips` is 1 while `Boards[].Chips` lists
  four entries (three are placeholders with id 0 and name `W0000_??00`); the
  models handle this without complaint.
- **Done so far:** client read methods `get_detector_info/health/layout/config`
  and `get_detector_snapshot` (reads all four into one `DetectorSnapshot`);
  `wait_until_detector_connected`; the example
  `examples/acquisition/serval/run_connect_snapshot.py` (+
  `connect_snapshot_config.yaml`) which launches SERVAL, waits for the detector,
  prints a snapshot, and shuts down. Verified live: connects, prints the
  snapshot, clean shutdown (exit 0); `acquisition.serval.jsonl` records the
  detector-connected event and one read per `/detector/*` endpoint. Unit tests
  cover the new client methods (incl. the 409 not-connected case) and the
  detector-connected poll (retry + timeout).
