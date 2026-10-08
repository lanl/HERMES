"""SERVAL acquisition: connect, read the detector, configure it, then measure.

The run makes sure SERVAL is running (launching it when a program path is set
and no server answers), waits for the camera to connect, and reads the
dashboard and detector snapshot into the record. When the config names a raw
data directory it then tells SERVAL where to write, and when it names SoPhy
calibration files it saves and loads them. Finally, when the config includes a
`run_timing` section it applies the detector configuration, takes one
measurement, and records the raw files it produced; without `run_timing` the
run stops once the detector is configured.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from hermes.runner.acquisition.serval.calibration import load_calibration
from hermes.runner.acquisition.serval.client import (
    ServalClient,
    ServalClientError,
    ServalConnectError,
)
from hermes.runner.acquisition.serval.destination import (
    configure_raw_destination,
    raw_destination_points_to,
)
from hermes.runner.acquisition.serval.measurement import (
    build_effective_detector_config,
    run_measurement,
)
from hermes.runner.acquisition.serval.server import (
    ServalServerError,
    start_serval,
    stop_serval,
    wait_until_detector_connected,
    wait_until_ready,
)
from hermes.runner.analysis.run import run_analysis
from hermes.state.models.acquisition.serval import (
    CalibrationState,
    DestinationConfiguration,
    ServalAcquisitionState,
    ServalDashboardMeasurement,
    ServalServer,
)
from hermes.state.models.analysis.hermes_tpx3_spidr import HermesTpx3AnalysisState
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
# space to warn below before a run writes raw data. The bias SERVAL reads back
# wanders a little around the set value (40.027 V seen at a 40 V setting), so
# the warning allows that much above the maximum.
_BIAS_MAX_V = 40.0
_BIAS_READ_BACK_MARGIN_V = 0.1
MIN_FREE_DISK_BYTES = 1 * 1024**3


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

    # Check before contacting SERVAL, so a run that cannot proceed never
    # launches the server or touches the detector.
    if acquisition.config.run_timing is not None:
        _refuse_raw_directory_with_old_files(
            state.environment.raw_data_directory.resolved_path
        )
        _refuse_invalid_detector_config(acquisition)

    serval = acquisition.config.serval
    log_dir = (
        state.environment.log_directory.resolved_path
        or state.environment.working_directory.resolved_path
    )

    client = ServalClient(serval.url)
    process: subprocess.Popen[bytes] | None = None
    try:
        process = _start_serval_unless_running(client, serval, log_dir)
        if process is not None:
            # `process` is set before the wait, so the `finally` below also
            # stops a SERVAL that exits or never becomes ready.
            wait_until_ready(
                client, process, log_dir, timeout_s=_SERVER_READY_TIMEOUT_S
            )
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
            _refuse_wrong_destination(applied_destination, raw_data_directory)
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
            _refuse_failed_calibration(calibration)

        run_timing = acquisition.config.run_timing
        if run_timing is not None:
            _run_measurement(state_manager, client, acquisition, raw_data_directory)
        elif will_configure:
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


def _refuse_raw_directory_with_old_files(raw_data_directory: Path | None) -> None:
    """Fail when the raw data directory already holds `.tpx3` files.

    The measurement result and an `auto` unpacking both take every `.tpx3` in
    the raw data directory, so files left there by an earlier run would be
    recorded and unpacked as part of this one, with both runs' times mixed on
    one time axis. The user must choose a new run directory or move the old
    files away first.
    """
    if raw_data_directory is None or not raw_data_directory.is_dir():
        return
    old_files = sorted(raw_data_directory.glob("*.tpx3"))
    if not old_files:
        return
    error = (
        f"the raw data directory {raw_data_directory} already holds "
        f"{len(old_files)} .tpx3 files from an earlier run; choose a new run "
        "directory or move those files away before measuring again"
    )
    _ACQUISITION_LOGGER.error(
        "Refusing to measure: {error}",
        event_type="acquisition.serval.raw_directory_not_empty",
        error=error,
        directory=str(raw_data_directory),
        file_count=len(old_files),
        first_file=old_files[0].name,
    )
    raise ServalAcquisitionError(error)


def _refuse_invalid_detector_config(acquisition: ServalAcquisitionState) -> None:
    """Fail when the detector configuration this run would send is invalid.

    Builds the same configuration the measurement sends to SERVAL, so a setting
    that would be refused there (such as a global timestamp interval that gives
    wrong times), or a `detector_config_file` that is missing or cannot be read,
    stops the run before SERVAL is launched or calibration loaded.
    """
    try:
        build_effective_detector_config(acquisition.config)
    except ValueError as error:
        _ACQUISITION_LOGGER.error(
            "Refusing to measure: the detector configuration is invalid: {error}",
            event_type="acquisition.serval.invalid_detector_config",
            error=str(error),
        )
        raise ServalAcquisitionError(str(error)) from error


def _run_measurement(
    state_manager: StateManager,
    client: ServalClient,
    acquisition: ServalAcquisitionState,
    raw_data_directory: Path | None,
) -> None:
    """Take one measurement and record its result and final detector state.

    A measurement needs somewhere to write, so a run that asks for one without a
    raw data directory is a configuration error. The measurement itself records
    its own outcome; the run status is `completed` only when the camera finished
    on its own with no errors, `stopped` when Ctrl-C ended it, and `failed`
    otherwise. When Ctrl-C or an unexpected error ended the measurement, that
    error is raised again once the outcome is recorded. A second Ctrl-C while
    HERMES stops the camera still records the status and asks SERVAL to stop
    again before it is raised.
    """
    if raw_data_directory is None:
        msg = (
            "config.run_timing is set but no raw_data_directory is configured; "
            "SERVAL would have nowhere to write the measurement"
        )
        _ACQUISITION_LOGGER.error(
            msg, event_type="acquisition.serval.no_raw_directory"
        )
        raise ServalAcquisitionError(msg)

    _record(
        state_manager,
        "acquisition.status",
        "running",
        justification="starting the measurement",
    )

    analysis_warnings: list[str] = []
    on_poll = _interleaved_analysis_callback(
        state_manager, raw_data_directory, analysis_warnings
    )
    try:
        outcome = run_measurement(
            client, acquisition.config, raw_data_directory, on_poll
        )
    except BaseException as error:
        # Ended before run_measurement could return an outcome: Ctrl-C before
        # the camera started, or a second Ctrl-C while HERMES was stopping it.
        # Record the status first, so the record does not say the measurement
        # is still running, then ask SERVAL to stop once more. SERVAL answers
        # "No measurement is running." when the camera is already idle.
        _record(
            state_manager,
            "acquisition.status",
            "stopped" if isinstance(error, KeyboardInterrupt) else "failed",
            justification=(
                f"the measurement ended before its outcome was recorded: {error!r}"
            ),
        )
        _stop_measurement(client)
        raise

    _record(
        state_manager,
        "acquisition.final_detector_snapshot",
        outcome.final_snapshot,
        justification="recorded the detector snapshot read after the measurement",
    )
    if outcome.final_dashboard is not None:
        _record(
            state_manager,
            "acquisition.dashboard",
            outcome.final_dashboard,
            justification="recorded the SERVAL dashboard read after the measurement",
        )
    outcome.result.warnings.extend(analysis_warnings)
    _record(
        state_manager,
        "acquisition.result",
        outcome.result,
        justification="recorded the measurement result",
    )

    if outcome.result.stop_reason == "interrupted":
        status = "stopped"
    elif not outcome.result.errors and outcome.result.stop_reason == "completed":
        status = "completed"
    else:
        status = "failed"
    _record(
        state_manager,
        "acquisition.status",
        status,
        justification="finished the measurement",
    )
    if outcome.exception is not None:
        raise outcome.exception


def _stop_measurement(client: ServalClient) -> None:
    """Ask SERVAL to stop the measurement, logging (not raising) any failure."""
    try:
        client.measurement_stop()
    except ServalClientError as error:
        _ACQUISITION_LOGGER.warning(
            "Could not stop the measurement: {error}",
            event_type="acquisition.serval.measurement_stop_failed",
            error=str(error),
        )


def _interleaved_analysis_callback(
    state_manager: StateManager,
    raw_data_directory: Path,
    warnings: list[str],
) -> Callable[[ServalDashboardMeasurement | None], None] | None:
    """Build a poll callback that unpacks raw files as new frames land.

    Returns None when the record has no HERMES analysis to run alongside the
    recording. SERVAL creates each raw file under its final name and can keep
    writing to it for seconds, so the callback runs the analysis only when no
    `.tpx3` file has changed size since the previous poll and something is new
    since the last successful run. Files already unpacked on an earlier poll
    are not unpacked again by the analysis itself, so it stays incremental.

    An analysis failure never stops the recording. The first one is logged with
    its traceback and added to `warnings`, and no more analysis runs during
    this recording; the analysis after recording handles every file.
    """
    if not isinstance(
        state_manager.get_state().analysis, HermesTpx3AnalysisState
    ):
        return None

    previous_sizes: dict[Path, int] = {}
    analyzed_sizes: dict[Path, int] = {}
    analysis_failed = False

    def on_poll(measurement: ServalDashboardMeasurement | None) -> None:
        nonlocal previous_sizes, analyzed_sizes, analysis_failed
        if analysis_failed:
            return
        try:
            current_sizes = {
                path: path.stat().st_size
                for path in raw_data_directory.glob("*.tpx3")
            }
        except OSError as error:
            # A file can vanish between the listing and its size read; try
            # again on the next poll rather than stop the recording.
            _ACQUISITION_LOGGER.warning(
                "Could not read the raw file sizes; trying again on the next "
                "poll: {error}",
                event_type="acquisition.serval.raw_file_sizes_unreadable",
                error=str(error),
            )
            return
        unchanged = current_sizes == previous_sizes
        previous_sizes = current_sizes
        if not unchanged or current_sizes == analyzed_sizes:
            return
        try:
            run_analysis(state_manager)
        except Exception as error:
            analysis_failed = True
            message = (
                "Analysis during recording failed, so no more analysis runs "
                f"until the recording ends: {type(error).__name__}: {error}"
            )
            warnings.append(message)
            _ACQUISITION_LOGGER.opt(exception=error).warning(
                "{message}",
                event_type="acquisition.serval.interleaved_analysis_failed",
                message=message,
                error=str(error),
            )
            return
        analyzed_sizes = current_sizes

    return on_poll


def _start_serval_unless_running(
    client: ServalClient,
    serval: ServalServer,
    log_dir: Path,
) -> subprocess.Popen[bytes] | None:
    """Start SERVAL when nothing is listening at its URL.

    Returns the started process, or None when a server already answers. The
    caller waits for a started server to answer and stops only a server it
    started. HERMES starts SERVAL only when it cannot connect at all: when
    something is there but answers with an error, or does not answer, a second
    SERVAL could not use the port, so HERMES raises instead.
    """
    try:
        client.get("/dashboard")
    except ServalConnectError:
        pass
    except ServalClientError as error:
        msg = (
            f"a server at {serval.url} did not answer /dashboard normally "
            f"({error}); HERMES will not start a second SERVAL there. Check "
            "that SERVAL is working, then run again"
        )
        _ACQUISITION_LOGGER.error(
            msg,
            event_type="acquisition.serval.server_not_answering_normally",
            url=serval.url,
            error=str(error),
        )
        raise ServalServerError(msg) from error
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

    return start_serval(serval, log_dir)


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
    if bias is not None and bias > _BIAS_MAX_V + _BIAS_READ_BACK_MARGIN_V:
        _ACQUISITION_LOGGER.warning(
            "Detector bias {bias} V exceeds the {maximum} V manual maximum",
            event_type="acquisition.serval.preflight_bias_high",
            bias=bias,
            maximum=_BIAS_MAX_V,
        )

    _warn_if_low_disk(disk_directory)


def _refuse_wrong_destination(
    applied: DestinationConfiguration,
    raw_data_directory: Path,
) -> None:
    """Fail when SERVAL does not report the raw destination HERMES just set.

    HERMES sets one raw output, writing to the raw data directory. Any other
    read-back means SERVAL would write raw files somewhere else as well, or
    instead. The destination SERVAL reports is already in the record by now,
    so the record shows where it points.
    """
    if raw_destination_points_to(applied, raw_data_directory):
        _ACQUISITION_LOGGER.info(
            "SERVAL destination confirmed at {directory}",
            event_type="acquisition.serval.destination_confirmed",
            directory=str(raw_data_directory),
        )
        return
    applied_bases = [entry.base for entry in applied.raw]
    error = (
        f"HERMES set the raw destination to {raw_data_directory}, but SERVAL "
        f"reports {applied_bases}, so the raw files would not go only there"
    )
    _ACQUISITION_LOGGER.error(
        "The SERVAL raw destination is wrong: {error}",
        event_type="acquisition.serval.destination_mismatch",
        error=error,
        directory=str(raw_data_directory),
        applied_bases=applied_bases,
    )
    raise ServalAcquisitionError(error)


def _refuse_failed_calibration(calibration: CalibrationState) -> None:
    """Fail when SERVAL did not load the pixel config or the DACs.

    The calibration is already in the record by now, so the record shows which
    file SERVAL loaded and what it answered for the one it did not. A run must
    not go on with a detector that is not calibrated, or only half calibrated.
    """
    loads = [
        ("pixel config", calibration.pixel_config_load),
        ("DACs", calibration.dacs_load),
    ]
    for name, load in loads:
        if load is None or load.status != "failed":
            continue
        answer = load.server_response_body or "SERVAL did not answer"
        error = (
            f"SERVAL did not load the {name} file {load.server_file_path}: {answer}"
        )
        _ACQUISITION_LOGGER.error(
            "The SERVAL calibration did not load: {error}",
            event_type="acquisition.serval.calibration_not_loaded",
            error=error,
            http_status_code=load.http_status_code,
        )
        raise ServalAcquisitionError(error)


def _warn_if_low_disk(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(directory).free
    if free_bytes < MIN_FREE_DISK_BYTES:
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
