# Stage 0 — HERMES starts and stops SERVAL

**Status:** Not started

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
     with `subprocess.Popen`, sending stdout/stderr to
     `<log_dir>/serval-server.log`. Return the process handle. Assume `java` is on
     `PATH` (add a knob only if the camera machine needs one). Build the launch
     flags from the version: use `--tcpIp`/`--tcpPort` from `serval.tcp_ip`/
     `tcp_port` only when `serval.major_version >= 3`; older versions take
     `--spidrNet` instead. When no camera flags are set, launch with none and let
     SERVAL autodiscover. See the "SERVAL versions" section of the README.
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

- **Jar path on this Mac.** The old path was a Linux box
  (`/home/ni_user/.../serv-2.1.6.jar`, `settings_installation.py:3`). Need the
  real jar location here, and confirmation that `java` runs on this machine.
  Supplied through `config.yaml` at test time, not hardcoded.

## Notes / findings

(update as we build and test)
