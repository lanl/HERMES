"""Read-only SERVAL acquisition: connect, read the detector, record it.

For this stage the run only reads. It makes sure SERVAL is running (launching
it when a program path is set and no server answers), waits for the camera to
connect, then reads the dashboard, the detector snapshot, and the current
destination and records them on the acquisition state. No configuration is
written and no measurement is taken.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from loguru import logger

from hermes.runner.acquisition.serval.client import ServalClient, ServalClientError
from hermes.runner.acquisition.serval.server import (
    ServalServerError,
    start_serval,
    stop_serval,
    wait_until_detector_connected,
    wait_until_ready,
)
from hermes.state.models.acquisition.serval import (
    ServalAcquisitionState,
    ServalServer,
)
from hermes.state_service.state_manager import StateManager

_ACQUISITION_LOGGER = logger.bind(
    domain="acquisition",
    backend="serval",
    step="serval_acquisition",
)

# How long to wait for the SERVAL HTTP server and then for the camera handshake.
_SERVER_READY_TIMEOUT_S = 60.0
_DETECTOR_CONNECT_TIMEOUT_S = 30.0


class ServalAcquisitionError(Exception):
    """Raised when the saved state cannot run a SERVAL acquisition."""


def run_serval_acquisition(state_manager: StateManager) -> None:
    """Connect to the camera through SERVAL and record what it reports.

    Reads the dashboard, the detector snapshot (info, health, layout, config),
    and the current destination, and records each through the state service.
    SERVAL is launched here only when HERMES had to start it, and is stopped
    again at the end in that case; a server that was already running is left
    running.
    """
    state = state_manager.get_state()
    acquisition = state.acquisition
    if not isinstance(acquisition, ServalAcquisitionState):
        error = "no valid SERVAL acquisition is configured"
        _ACQUISITION_LOGGER.error(
            "Cannot run SERVAL acquisition: {error}",
            event_type="acquisition.serval.invalid_mode",
            error=error,
            actual_acquisition_mode=getattr(acquisition, "mode", None),
        )
        raise ServalAcquisitionError(error)

    serval = acquisition.config.serval
    log_dir = (
        state.environment.log_directory.resolved_path
        or state.environment.working_directory.resolved_path
    )

    client = ServalClient(serval.url)
    process: subprocess.Popen[bytes] | None = None
    try:
        process = _ensure_serval_running(client, serval, log_dir)
        wait_until_detector_connected(client, timeout_s=_DETECTOR_CONNECT_TIMEOUT_S)

        dashboard = client.get_dashboard()
        _record(
            state_manager,
            "acquisition.dashboard",
            dashboard,
            justification="recorded the SERVAL dashboard read at connect time",
        )

        snapshot = client.get_detector_snapshot()
        _record(
            state_manager,
            "acquisition.initial_detector_snapshot",
            snapshot,
            justification="recorded the detector snapshot read at connect time",
        )

        # A fresh server that has not been told where to write answers
        # `/server/destination` with 409 "Destination is not set." That is
        # normal for a read-only connect, so warn and leave the destination
        # unrecorded rather than fail the whole read.
        try:
            destination = client.get_destination()
        except ServalClientError as error:
            _ACQUISITION_LOGGER.warning(
                "Could not read the SERVAL destination; leaving it unset: {error}",
                event_type="acquisition.serval.destination_unavailable",
                error=str(error),
            )
        else:
            _record(
                state_manager,
                "acquisition.destination",
                destination,
                justification="recorded the current SERVAL destination",
            )

        _check_presence(dashboard, snapshot)
        _check_version(serval, dashboard)

        _record(
            state_manager,
            "acquisition.status",
            "completed",
            justification="finished the read-only connect and snapshot",
        )
    finally:
        if process is not None:
            stop_serval(client, process)
        client.close()


def _ensure_serval_running(
    client: ServalClient,
    serval: ServalServer,
    log_dir: Path,
) -> subprocess.Popen[bytes] | None:
    """Make sure SERVAL answers, launching it if HERMES has to.

    Returns the launched process when HERMES started SERVAL, or None when a
    server was already answering. The caller stops only a server it started.
    """
    try:
        client.get("/dashboard")
    except ServalClientError:
        pass
    else:
        _ACQUISITION_LOGGER.info(
            "SERVAL is already running at {url}",
            event_type="acquisition.serval.server_already_running",
            url=serval.url,
        )
        return None

    if serval.program_path is None:
        msg = (
            f"no SERVAL server answers at {serval.url} and no program_path is set "
            "to launch one"
        )
        _ACQUISITION_LOGGER.error(
            msg,
            event_type="acquisition.serval.server_unavailable",
            url=serval.url,
        )
        raise ServalServerError(msg)

    process = start_serval(serval, log_dir)
    wait_until_ready(client, timeout_s=_SERVER_READY_TIMEOUT_S)
    return process


def _check_presence(dashboard, snapshot) -> None:
    """Warn (do not fail) if no detector is attached or a run is in progress."""
    info = snapshot.info
    detector_attached = dashboard.detector is not None or (
        info is not None
        and info.number_of_chips is not None
        and info.number_of_chips >= 1
    )
    if not detector_attached:
        _ACQUISITION_LOGGER.warning(
            "SERVAL reports no detector attached",
            event_type="acquisition.serval.no_detector",
        )

    # A null Measurement or DA_IDLE means nothing is running, which is the safe
    # state for a read-only connect. Only an active measurement is worth a warning.
    status = dashboard.measurement.status if dashboard.measurement else None
    if status not in (None, "DA_IDLE"):
        _ACQUISITION_LOGGER.warning(
            "SERVAL reports a measurement in progress (status {status})",
            event_type="acquisition.serval.measurement_in_progress",
            status=status,
        )


def _check_version(serval: ServalServer, dashboard) -> None:
    """Warn (do not fail) if the running version differs from the declared one."""
    observed = dashboard.server.software_version
    declared = serval.version
    if declared is not None and observed is not None and declared != observed:
        _ACQUISITION_LOGGER.warning(
            "SERVAL version {observed} differs from the configured {declared}",
            event_type="acquisition.serval.version_mismatch",
            observed=observed,
            declared=declared,
        )


def _record(
    state_manager: StateManager,
    path: str,
    value: object,
    *,
    justification: str,
) -> None:
    change = state_manager.propose_change(
        path,
        value,
        origin="trusted_workflow",
        proposer="serval_acquisition",
        justification=justification,
    )
    state_manager.apply_change(change.change_id)
