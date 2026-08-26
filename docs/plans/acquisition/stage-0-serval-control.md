# Stage 0 — HERMES starts and stops SERVAL

**Status:** Complete — tested against the live camera 2026-08-25.

**Goal:** HERMES can launch the SERVAL server, wait until it answers, and shut it
down. Add the httpx client skeleton. The SERVAL jar path already lives in the
config as `config.serval.program_path`. No detector reads yet beyond the
readiness check.

## Why this is first

You asked HERMES to control SERVAL rather than attach to a server someone else
started. Every later stage needs a running server, so process control comes
first. The old prototype launched `java -jar <jar>` then slept 5 seconds with no
check (`tpx3Spider_lumacam.py:10-19`); we replace the blind sleep with a real
readiness poll.

## Work

1. **Add the dependency.** `pixi add httpx`. Confirm it resolves and imports.

2. **Jar path is already in the config.** `config.serval.program_path`
   (`ServalServer` in `src/hermes/state/models/acquisition/serval.py`) holds the
   SERVAL jar path. It is a local `Path` (not a host-resolved string) because
   HERMES launches SERVAL on the same machine. No model change is needed here;
   read it from the loaded record.

3. **Server process control** — new `src/hermes/runner/acquisition/serval/server.py`:
   - `start_serval(serval, log_dir)` — launch `java -jar <serval.program_path>`
     with `subprocess.Popen`, appending the server's own stdout/stderr to
     `<log_dir>/serval-server.log`. Return the process handle. `java` is taken
     from `PATH`. Camera-address flags: when `serval.tcp_ip` is set, pass
     `--tcpIp` (and `--tcpPort` when given); when it is unset, launch with no
     camera flag and let SERVAL autodiscover. `tcp_ip`/`tcp_port` are the SERVAL
     3.0+ flags, and the state model already rejects them on a declared 2.x
     version, so nothing here turns them into the older `spidrNet` form; add a
     `spidr_net` field and flag only if a 2.x camera ever needs an explicit
     address. See the "SERVAL versions" section of the README.
   - `wait_until_ready(client, timeout_s)` — poll `GET /dashboard` until it
     returns 200 or the timeout elapses; raise on timeout.
   - `stop_serval(client, handle)` — `GET /server/shutdown`, then terminate the
     process if it is still alive after a bounded wait.
   - Log `domain="acquisition", backend="serval"` events: server launch, server
     ready (with software version), server shutdown.

4. **HTTP client skeleton** — new `src/hermes/runner/acquisition/serval/client.py`:
   - Thin wrapper over `httpx.Client(base_url=serval_url, timeout=...)`.
   - `get_json(path)` / `put_json(path, body)` helpers that raise on non-200 and
     log each call (method, path, status code, elapsed time) in the acquisition
     domain.
   - One typed method for this stage: `get_dashboard() -> ServalDashboard`.

## Test against the real machine

- A small script (put it under `examples/acquisition/serval/`) with a
  `config.yaml` whose `acquisition.config.serval` sets
  `url: http://localhost:8080` and `program_path: <path to the jar on this Mac>`.
- The script: start SERVAL, wait until ready, print the software version from
  `/dashboard`, then shut it down.
- Confirm: `serval-server.log` is written, `acquisition.serval.jsonl` shows
  launch/ready/shutdown events, and the process is gone afterward.

## Open items

- **Jar path on this Mac — resolved.** The jar is
  `/Users/alexlong/Programs/tpx3_software/TPX3Cam/Serval/3.3.0/serval-3.3.0.jar`
  and `java` is Homebrew's openjdk 21 (`/opt/homebrew/opt/openjdk@21/bin/java`).
  The checked-in example (`examples/acquisition/serval/config.yaml`) keeps a
  placeholder `program_path`; the live-test config with the real path lives
  under `.scratch/stage0/` (not tracked).

## Notes / findings

- Built `client.py` (`ServalClient`: `get`/`put`, `get_json`/`put_json`,
  `get_dashboard`; raises `ServalClientError` on transport failure or non-200)
  and `server.py` (`start_serval`, `wait_until_ready`, `stop_serval`,
  `_build_launch_command`; raises `ServalServerError`). Added `httpx` via pixi.
- Ran end to end against the live camera on 2026-08-25: SERVAL launches, is
  ready ~0.6 s later (software version 3.3.0), and shuts down clean (exit 0).
  `serval-server.log` and `acquisition.serval.jsonl` are both written and the
  process is gone afterward.
- The first readiness poll hits "connection refused" while SERVAL is still
  starting; that is normal, so the client logs a failed send at **debug**, not
  error, and `wait_until_ready` retries until 200. Only a readiness **timeout**
  is an error.
- `wait_until_ready` reads the version loosely from the dashboard JSON and does
  not validate the strict `ServalDashboard` model, so readiness never breaks on
  a server whose dashboard carries extra fields. The typed `get_dashboard()` is
  there for stage 1, where the read-only models relax to `extra="ignore"`.
- Unit tests: `tests/unit/hermes/runner/acquisition/serval/` cover the
  version-aware launch flags, `start_serval` guards, `wait_until_ready` retry
  and timeout, `stop_serval` shutdown and terminate paths, and the client's
  dashboard parsing and non-200 handling (via `httpx.MockTransport`).
