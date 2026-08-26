from __future__ import annotations

import subprocess
import time
from pathlib import Path

from loguru import logger

from hermes.runner.acquisition.serval.client import ServalClient, ServalClientError
from hermes.state.models.acquisition.serval import ServalServer

_SERVER_LOGGER = logger.bind(domain="acquisition", backend="serval", step="serval_server")

# How often the readiness poll asks the server whether it is up yet.
_POLL_INTERVAL_S = 0.5


class ServalServerError(Exception):
    """Raised when HERMES cannot launch, reach, or stop the SERVAL server."""


def _build_launch_command(serval: ServalServer) -> list[str]:
    """Build the `java -jar` command line, including any camera-address flags.

    `tcp_ip`/`tcp_port` are the SERVAL 3.0+ flags that point the server at one
    camera. The state model already rejects them on a declared 2.x version, so
    when they are set here the server is 3.0+ (or its version is undeclared).
    When no camera address is given, SERVAL is launched with none and
    autodiscovers the camera. HERMES has no field for the older `spidrNet`
    address form yet; add one here if a 2.x camera ever needs an explicit
    address.

    SERVAL parses these flags in the `--flag=value` form only; the space-
    separated form (`--tcpIp 192.168.100.10`) makes SERVAL report the argument
    as missing and refuse to open its HTTP port.
    """
    command = ["java", "-jar", str(serval.program_path)]
    if serval.tcp_ip is not None:
        command.append(f"--tcpIp={serval.tcp_ip}")
        if serval.tcp_port is not None:
            command.append(f"--tcpPort={serval.tcp_port}")
    return command


def start_serval(serval: ServalServer, log_dir: Path) -> subprocess.Popen[bytes]:
    """Launch the SERVAL server and return its process handle.

    `java -jar <serval.program_path>` is started with `java` taken from PATH.
    The server's own stdout and stderr are appended to
    `<log_dir>/serval-server.log`. This only launches the process; use
    `wait_until_ready` to confirm it is answering before talking to it.
    """
    program_path = serval.program_path
    if program_path is None:
        msg = "config.serval.program_path must be set to launch SERVAL"
        raise ServalServerError(msg)
    if not program_path.exists():
        msg = f"SERVAL jar not found: {program_path}"
        raise ServalServerError(msg)

    log_dir.mkdir(parents=True, exist_ok=True)
    server_log = log_dir / "serval-server.log"
    command = _build_launch_command(serval)

    _SERVER_LOGGER.info(
        "Launching SERVAL: {command}",
        event_type="acquisition.serval.server_launch",
        command=command,
        program_path=str(program_path),
        server_log=str(server_log),
        url=serval.url,
        version=serval.version,
    )

    # The child inherits a duplicate of the log file descriptor, so the parent
    # closes its own copy right away; the file stays open until the child exits.
    log_handle = server_log.open("ab")
    try:
        process = subprocess.Popen(
            command,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
    except OSError as error:
        log_handle.close()
        msg = f"could not start SERVAL with {command!r}: {error}"
        raise ServalServerError(msg) from error
    finally:
        log_handle.close()

    return process


def wait_until_ready(client: ServalClient, *, timeout_s: float = 30.0) -> str | None:
    """Poll `GET /dashboard` until the server answers, or raise on timeout.

    Returns the running server's software version (from the dashboard) when it
    becomes ready. Readiness is a plain 200 answer; the dashboard is read
    loosely here so a server whose JSON has extra fields still counts as ready.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            response = client.get("/dashboard")
        except ServalClientError:
            response = None

        if response is not None:
            software_version = (
                response.json().get("Server", {}).get("SoftwareVersion")
            )
            _SERVER_LOGGER.info(
                "SERVAL is ready (version {software_version})",
                event_type="acquisition.serval.server_ready",
                software_version=software_version,
                url=client.base_url,
            )
            return software_version

        if time.monotonic() >= deadline:
            msg = (
                f"SERVAL did not become ready within {timeout_s} s "
                f"at {client.base_url}"
            )
            _SERVER_LOGGER.error(
                msg,
                event_type="acquisition.serval.server_ready_timeout",
                url=client.base_url,
                timeout_s=timeout_s,
            )
            raise ServalServerError(msg)

        time.sleep(_POLL_INTERVAL_S)


def wait_until_detector_connected(
    client: ServalClient,
    *,
    timeout_s: float = 30.0,
) -> None:
    """Poll `GET /dashboard` until SERVAL reports a connected detector.

    A running SERVAL answers `/dashboard` within a second, but the camera
    handshake over the SPIDR link takes several seconds more. Until it
    finishes the dashboard's `Detector` is null and every `/detector/*` read
    returns 409 "Not connected". This waits for `Detector` to appear so callers
    read the detector only once the camera is actually connected. Raises on
    timeout.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            detector = client.get_json("/dashboard").get("Detector")
        except ServalClientError:
            detector = None

        if detector is not None:
            _SERVER_LOGGER.info(
                "SERVAL reports a connected detector ({detector_type})",
                event_type="acquisition.serval.detector_connected",
                detector_type=detector.get("DetectorType"),
                url=client.base_url,
            )
            return

        if time.monotonic() >= deadline:
            msg = (
                f"SERVAL did not report a connected detector within "
                f"{timeout_s} s at {client.base_url}"
            )
            _SERVER_LOGGER.error(
                msg,
                event_type="acquisition.serval.detector_connect_timeout",
                url=client.base_url,
                timeout_s=timeout_s,
            )
            raise ServalServerError(msg)

        time.sleep(_POLL_INTERVAL_S)


def stop_serval(
    client: ServalClient,
    process: subprocess.Popen[bytes],
    *,
    timeout_s: float = 10.0,
) -> int | None:
    """Ask SERVAL to shut down, then make sure its process is gone.

    First `GET /server/shutdown` asks the server to stop cleanly. Whether or
    not that call answers, HERMES then waits for the process to exit and
    terminates (and finally kills) it if it is still alive. Returns the
    process exit code.
    """
    try:
        client.get("/server/shutdown")
    except ServalClientError as error:
        # The server often drops the connection as it shuts down, so a failed
        # shutdown call is expected; fall through to waiting on the process.
        _SERVER_LOGGER.warning(
            "SERVAL shutdown request did not answer cleanly: {error}",
            event_type="acquisition.serval.server_shutdown_request_failed",
            error=str(error),
        )

    try:
        process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _SERVER_LOGGER.warning(
            "SERVAL did not exit after shutdown; terminating the process",
            event_type="acquisition.serval.server_terminate",
        )
        process.terminate()
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _SERVER_LOGGER.warning(
                "SERVAL did not respond to terminate; killing the process",
                event_type="acquisition.serval.server_kill",
            )
            process.kill()
            process.wait()

    _SERVER_LOGGER.info(
        "SERVAL server stopped (exit code {exit_code})",
        event_type="acquisition.serval.server_shutdown",
        exit_code=process.returncode,
    )
    return process.returncode
