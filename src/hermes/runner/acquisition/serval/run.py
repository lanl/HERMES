"""SERVAL acquisition: connect, read the detector, then configure it.

The run makes sure SERVAL is running (launching it when a program path is set
and no server answers), waits for the camera to connect, and reads the
dashboard and detector snapshot into the record. When the config names a raw
data directory it then tells SERVAL where to write, and when it names SoPhy
calibration files it saves and loads them. No measurement is taken here: the
run stops once the detector is configured.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from loguru import logger

from hermes.runner.acquisition.serval.calibration import load_calibration
from hermes.runner.acquisition.serval.client import ServalClient, ServalClientError
from hermes.runner.acquisition.serval.destination import configure_raw_destination
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

# The manual's maximum bias for normal operation, and a floor of free disk
# space to warn below before a run writes raw data.
_BIAS_MAX_V = 40.0
_MIN_FREE_DISK_BYTES = 1 * 1024**3


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

        _check_presence(dashboard, snapshot)
        _check_version(serval, dashboard)

        environment = state.environment
        raw_data_directory = environment.raw_data_directory.resolved_path
        calibration_files = acquisition.config.calibration_files
        run_directory = (
            environment.run_directory.resolved_path
            or environment.working_directory.resolved_path
        )
        will_configure = (
            raw_data_directory is not None or calibration_files is not None
        )

        if will_configure:
            _preflight_for_writes(
                dashboard, snapshot, raw_data_directory or run_directory
            )

        if raw_data_directory is not None:
            applied_destination = configure_raw_destination(
                client, raw_data_directory
            )
            _record(
                state_manager,
                "acquisition.destination",
                applied_destination,
                justification="recorded the SERVAL raw destination after setting it",
            )
        else:
            _record_existing_destination(client, state_manager)

        if calibration_files is not None:
            calibration = load_calibration(
                client,
                calibration_files,
                run_directory / "config",
                run_directory,
            )
            _record(
                state_manager,
                "acquisition.calibration",
                calibration,
                justification="recorded the saved and loaded SoPhy calibration files",
            )

        if will_configure:
            _record(
                state_manager,
                "acquisition.status",
                "configured",
                justification="finished configuring the destination and calibration",
            )
        else:
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


def _preflight_for_writes(dashboard, snapshot, disk_directory: Path) -> None:
    """Fail before writing if the detector is missing or busy; warn on the rest.

    A missing detector or a measurement in progress is a hard stop: HERMES must
    not reconfigure in those states. A bias above the manual maximum and low
    free disk are warnings, since the run can still proceed.
    """
    info = snapshot.info
    detector_attached = dashboard.detector is not None or (
        info is not None
        and info.number_of_chips is not None
        and info.number_of_chips >= 1
    )
    if not detector_attached:
        msg = "no detector is attached; cannot configure SERVAL"
        _ACQUISITION_LOGGER.error(
            msg, event_type="acquisition.serval.preflight_no_detector"
        )
        raise ServalAcquisitionError(msg)

    status = dashboard.measurement.status if dashboard.measurement else None
    if status not in (None, "DA_IDLE"):
        msg = f"a measurement is in progress (status {status}); refusing to reconfigure"
        _ACQUISITION_LOGGER.error(
            msg,
            event_type="acquisition.serval.preflight_not_idle",
            status=status,
        )
        raise ServalAcquisitionError(msg)

    health = snapshot.health
    bias = health.bias_voltage_v if health is not None else None
    if bias is not None and bias > _BIAS_MAX_V:
        _ACQUISITION_LOGGER.warning(
            "Detector bias {bias} V exceeds the {maximum} V manual maximum",
            event_type="acquisition.serval.preflight_bias_high",
            bias=bias,
            maximum=_BIAS_MAX_V,
        )

    _warn_if_low_disk(disk_directory)


def _warn_if_low_disk(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(directory).free
    if free_bytes < _MIN_FREE_DISK_BYTES:
        _ACQUISITION_LOGGER.warning(
            "Only {free_bytes} bytes free at {directory} for raw data",
            event_type="acquisition.serval.preflight_low_disk",
            free_bytes=free_bytes,
            directory=str(directory),
        )


def _record_existing_destination(
    client: ServalClient,
    state_manager: StateManager,
) -> None:
    """Record the destination SERVAL already has, tolerating an unset one.

    Used on a read-only connect (no raw data directory configured). A fresh
    server answers `/server/destination` with 409 "Destination is not set.";
    that is normal here, so warn and leave the destination unrecorded.
    """
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
