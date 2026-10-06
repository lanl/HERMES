"""Apply the detector configuration, take one measurement, and record it.

The effective detector configuration is built from the run's config (the inline
`detector_config`, or the JSON at `detector_config_file` when that is set, with
the `run_timing` values layered on top), sent to SERVAL, and read back. SERVAL
then starts the measurement; HERMES watches the dashboard until the camera
reports it is idle again (or a wait limit is reached, at which point HERMES stops
it). Finally the raw `.tpx3` files SERVAL wrote are gathered into the result.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from loguru import logger

from hermes.runner.acquisition.serval.client import ServalClient, ServalClientError
from hermes.state.models.acquisition.serval import (
    ServalAcquisitionConfig,
    ServalAcquisitionResult,
    ServalDashboard,
    ServalDashboardMeasurement,
    ServalDashboardNotification,
    ServalRunTiming,
)
from hermes.state.models.detector import DetectorConfiguration, DetectorSnapshot
from hermes.state.models.shared_models import FileReference, utc_now

_MEASUREMENT_LOGGER = logger.bind(
    domain="acquisition",
    backend="serval",
    step="serval_measurement",
)

# How often to ask the dashboard whether the measurement has finished, and how
# often to write a progress line (every poll would flood the log).
_POLL_INTERVAL_S = 0.5
_PROGRESS_LOG_INTERVAL_S = 5.0

# The measurement should leave the idle state soon after it starts; if it never
# does (and produces no frames) within this window, HERMES stops waiting.
_START_TIMEOUT_S = 15.0

# These apply only when the run does not set its own wait limit
# (run_timing.max_wait_s). Then HERMES waits twice the run's expected length plus
# _WAIT_MARGIN_S; a run whose length cannot be told from the detector
# configuration (one whose frames wait for external or software triggers) waits
# _DEFAULT_WAIT_S before HERMES stops it.
_WAIT_MARGIN_S = 10.0
_DEFAULT_WAIT_S = 300.0

# Statuses that mean the camera is busy with the measurement (not idle).
_ACTIVE_STATUSES = ("DA_PREPARING", "DA_RECORDING", "DA_STOPPING")

# Unpacking places each pixel time using the global timestamp before it. The
# pixel clock wraps every 2**30 * 25 ns (about 26.84 s), so a pixel more than
# half a wrap (about 13.42 s) after that timestamp comes out one wrap early, with
# no error. The longest interval HERMES accepts stays a little under half a wrap.
_MAX_GLOBAL_TIMESTAMP_INTERVAL_S = 13.0

# The global timestamp interval HERMES sends when the config leaves it unset.
# One second is the tested setting.
_DEFAULT_GLOBAL_TIMESTAMP_INTERVAL_S = 1.0

# Trigger modes in which the trigger period sets how often a new raw file
# starts. HERMES writes one raw file per frame, so in these modes the interval
# must be at most half the trigger period for every file to hold a global
# timestamp. Half, not all, because SERVAL writes them up to about 18 ms off
# schedule.
_TRIGGER_PERIOD_MODES = ("AUTOTRIGSTART_TIMERSTOP", "CONTINUOUS")

# The shortest frame (trigger period) HERMES accepts in those modes.
_MIN_TRIGGER_PERIOD_S = 0.1

# SERVAL notice types that HERMES logs and records as warnings. The others are
# "info" and "update".
_SERIOUS_NOTIFICATION_TYPES = ("severe", "error")


class ServalMeasurementError(Exception):
    """Raised when a measurement cannot be run at all."""


class MeasurementOutcome(NamedTuple):
    """What one measurement produced, for the run to record.

    `exception` is set when Ctrl-C or an error HERMES did not expect ended the
    measurement early. HERMES has already stopped the camera by then; the caller
    records the outcome and then raises `exception` again.
    """

    result: ServalAcquisitionResult
    final_snapshot: DetectorSnapshot
    final_dashboard: ServalDashboard
    exception: BaseException | None = None


def build_effective_detector_config(
    config: ServalAcquisitionConfig,
) -> DetectorConfiguration:
    """Compose the detector configuration to send to SERVAL.

    Start from the JSON at `detector_config_file` when it is set (it wins over
    the inline `detector_config`), otherwise the inline `detector_config`, or an
    empty configuration when neither is given. Then layer the `run_timing`
    values on top: trigger mode, exposure time, trigger period, and trigger
    count (which maps to the detector's `n_triggers`). When the global timestamp
    interval is unset, HERMES fills it in (see `_with_global_timestamp_interval`).
    Raises ValueError when `detector_config_file` cannot be read or the result is
    invalid, including global timestamp settings that would give wrong times (see
    `_check_global_timestamp_interval`).
    """
    base = _load_base_config(config)
    timing = config.run_timing
    if timing is None:
        effective = _with_global_timestamp_interval(base)
        _check_global_timestamp_interval(effective)
        return effective

    updates: dict[str, object] = {}
    if timing.trigger_mode is not None:
        updates["trigger_mode"] = timing.trigger_mode
    if timing.exposure_time_s is not None:
        updates["exposure_time_s"] = timing.exposure_time_s
    if timing.trigger_period_s is not None:
        updates["trigger_period_s"] = timing.trigger_period_s
    if timing.trigger_count is not None:
        updates["n_triggers"] = timing.trigger_count

    merged = base.model_copy(update=updates)
    # model_copy does not re-run validators, so validate the merged configuration
    # to apply the cross-field rules (like the sequential dead-time rule) to the
    # effective config before it is sent to SERVAL.
    effective = DetectorConfiguration.model_validate(merged.model_dump())
    effective = _with_global_timestamp_interval(effective)
    _check_global_timestamp_interval(effective)
    return effective


def _with_global_timestamp_interval(
    effective: DetectorConfiguration,
) -> DetectorConfiguration:
    """Fill in the global timestamp interval when the config leaves it unset.

    Global timestamps are always on, so HERMES never leaves the interval to
    whatever SERVAL last held (a freshly started SERVAL has them off). It uses
    `_DEFAULT_GLOBAL_TIMESTAMP_INTERVAL_S`, or half the trigger period when the
    trigger period sets the frame length and frames are shorter than twice that.
    """
    if effective.global_timestamp_interval_s is not None:
        return effective
    interval = _DEFAULT_GLOBAL_TIMESTAMP_INTERVAL_S
    period = effective.trigger_period_s
    if effective.trigger_mode in _TRIGGER_PERIOD_MODES and period is not None:
        interval = min(interval, period / 2)
    _MEASUREMENT_LOGGER.info(
        "GlobalTimestampInterval is not set; HERMES uses {interval} s",
        event_type="acquisition.serval.global_timestamp_interval_default",
        interval=interval,
        trigger_mode=effective.trigger_mode,
        trigger_period_s=period,
    )
    return effective.model_copy(update={"global_timestamp_interval_s": interval})


def _check_global_timestamp_interval(effective: DetectorConfiguration) -> None:
    """Raise ValueError when the global timestamp settings would give wrong times.

    Unpacking adds back the wraps a pixel or TDC time has lost by comparing it
    with the global timestamp before it. These settings break that:

    - An interval of 0 or less, which turns global timestamps off.
    - An interval over `_MAX_GLOBAL_TIMESTAMP_INTERVAL_S`: pixels more than about
      13.4 s after a global timestamp come out exactly 26.84 s early, with no
      error.
    - In a mode where the trigger period sets the frame length, a trigger period
      under `_MIN_TRIGGER_PERIOD_S`, or an interval over half the trigger
      period: some raw files could get no global timestamp of their own.

    The SERVAL API accepts all of these, so this is a HERMES check, not a limit
    on the detector configuration model (which also reads back what SERVAL
    holds). That model already refuses an interval between 0 and 1 ms.
    """
    period = effective.trigger_period_s
    frames_from_period = (
        effective.trigger_mode in _TRIGGER_PERIOD_MODES and period is not None
    )
    if frames_from_period and period < _MIN_TRIGGER_PERIOD_S:
        msg = (
            f"trigger period of {period} s is shorter than "
            f"{_MIN_TRIGGER_PERIOD_S} s, the shortest frame HERMES accepts in "
            f"{effective.trigger_mode} mode"
        )
        raise ValueError(msg)
    interval = effective.global_timestamp_interval_s
    if interval is None:
        return
    if interval <= 0:
        msg = (
            f"GlobalTimestampInterval of {interval} s turns global timestamps "
            "off, and unpacking needs them to place pixel, TDC, and event times "
            "on one time axis; leave it unset or use 1 s"
        )
        raise ValueError(msg)
    if interval > _MAX_GLOBAL_TIMESTAMP_INTERVAL_S:
        msg = (
            f"GlobalTimestampInterval of {interval} s is longer than "
            f"{_MAX_GLOBAL_TIMESTAMP_INTERVAL_S} s: the pixel clock wraps every "
            "26.84 s, so pixels more than about 13.4 s after a global timestamp "
            "would come out 26.84 s early with no error; use a shorter interval, "
            "such as 1 s"
        )
        raise ValueError(msg)
    if frames_from_period and interval > period / 2:
        msg = (
            f"GlobalTimestampInterval of {interval} s is longer than half the "
            f"{period} s trigger period: HERMES writes one raw file per frame, "
            "and SERVAL writes global timestamps a few ms off schedule, so some "
            "files could get no global timestamp of their own; set it to at most "
            f"{period / 2} s"
        )
        raise ValueError(msg)


def _load_base_config(config: ServalAcquisitionConfig) -> DetectorConfiguration:
    if config.detector_config_file is not None:
        try:
            text = config.detector_config_file.read_text()
        except OSError as error:
            msg = (
                f"cannot read detector_config_file {config.detector_config_file}: "
                f"{error.strerror or error}"
            )
            raise ValueError(msg) from error
        return DetectorConfiguration.model_validate(json.loads(text))
    if config.detector_config is not None:
        return config.detector_config
    return DetectorConfiguration()


def run_measurement(
    client: ServalClient,
    config: ServalAcquisitionConfig,
    raw_data_directory: Path,
    on_poll: Callable[[ServalDashboardMeasurement | None], None] | None = None,
) -> MeasurementOutcome:
    """Apply the configuration, start the measurement, and record what it made.

    Sends the effective detector configuration, reads it back (warning on any
    difference), starts the measurement, and watches the dashboard until the
    camera is idle again or the wait limit is reached. Always tries to stop the
    measurement and read a final snapshot, even when a step fails, so the record
    reflects what happened. The run's status is decided by the caller from the
    result's `errors` and `stop_reason`.

    Ctrl-C or an error HERMES did not expect while the camera records does not
    leave it recording: HERMES stops the measurement, gathers what it made, and
    returns the outcome with the error in `exception` (stop reason `interrupted`
    for Ctrl-C, `failed` otherwise) for the caller to record and raise again.

    ``on_poll``, when given, is called once per dashboard poll with the current
    measurement (or ``None`` when that poll's read failed). The caller uses this
    to unpack raw files as new frames land during the recording; it must not
    raise, and it must be quick since it runs between polls.
    """
    warnings: list[str] = []
    errors: list[str] = []

    try:
        effective = build_effective_detector_config(config)
    except ValueError as error:
        errors.append(str(error))
        _MEASUREMENT_LOGGER.error(
            "Not starting the measurement: the detector configuration is "
            "invalid: {error}",
            event_type="acquisition.serval.measurement_not_started",
            stop_reason="invalid_configuration",
            error=str(error),
        )
        return _not_started_outcome(
            client, None, warnings, errors, stop_reason="invalid_configuration"
        )

    applied = _apply_config(client, effective, warnings, errors)
    if errors:
        # The configuration could not be applied, so the camera would record at
        # its previous, unverified settings. Do not start the measurement: a run
        # with no provenance over its settings is worse than no run at all.
        _MEASUREMENT_LOGGER.error(
            "Not starting the measurement: the detector configuration was not "
            "applied",
            event_type="acquisition.serval.measurement_not_started",
            stop_reason="config_not_applied",
            errors=errors,
        )
        return _not_started_outcome(
            client, applied, warnings, errors, stop_reason="config_not_applied"
        )

    wait_limit_s = _wait_limit_s(config.run_timing, applied)
    started_at = utc_now()
    stop_reason = "completed"
    exception: BaseException | None = None
    try:
        client.measurement_start()
        _MEASUREMENT_LOGGER.info(
            "Measurement started; HERMES waits up to {wait_limit_s:.0f} s for it "
            "to finish",
            event_type="acquisition.serval.measurement_start",
            trigger_mode=applied.trigger_mode,
            n_triggers=applied.n_triggers,
            exposure_time_s=applied.exposure_time_s,
            trigger_period_s=applied.trigger_period_s,
            wait_limit_s=wait_limit_s,
        )
        stop_reason = _monitor(client, wait_limit_s, warnings, on_poll)
    except ServalClientError as error:
        errors.append(str(error))
        stop_reason = "failed"
        _MEASUREMENT_LOGGER.error(
            "Measurement failed to run: {error}",
            event_type="acquisition.serval.measurement_failed",
            error=str(error),
        )
        _safe_stop(client, warnings)
    except BaseException as error:
        # Ctrl-C, or an error HERMES did not expect (such as a dashboard it
        # cannot read). Stop the camera so it does not keep recording, and keep
        # the error for the caller to raise once the outcome is recorded.
        exception = error
        if isinstance(error, KeyboardInterrupt):
            stop_reason = "interrupted"
            warnings.append("measurement was interrupted (Ctrl-C); stopping it")
            _MEASUREMENT_LOGGER.warning(
                "Measurement interrupted (Ctrl-C); stopping it",
                event_type="acquisition.serval.measurement_interrupted",
            )
        else:
            stop_reason = "failed"
            errors.append(f"{type(error).__name__}: {error}")
            _MEASUREMENT_LOGGER.error(
                "Measurement failed to run: {error_type}: {error}",
                event_type="acquisition.serval.measurement_failed",
                error_type=type(error).__name__,
                error=str(error),
            )
        _safe_stop(client, warnings)
    completed_at = utc_now()

    final_dashboard, final_snapshot = _read_final_state(client, applied, warnings)
    measurement = final_dashboard.measurement if final_dashboard is not None else None
    output_files = _collect_output_files(raw_data_directory)

    _MEASUREMENT_LOGGER.info(
        "Measurement finished ({stop_reason}): {file_count} raw files, "
        "{frames} frames, {dropped} dropped",
        event_type="acquisition.serval.measurement_done",
        stop_reason=stop_reason,
        file_count=len(output_files),
        frames=measurement.frame_count if measurement else None,
        dropped=measurement.dropped_frames if measurement else None,
    )
    if measurement is not None:
        _check_frames(stop_reason, measurement, warnings, errors)
    if final_dashboard is not None:
        _check_notifications(final_dashboard, warnings, errors)

    result = ServalAcquisitionResult(
        started_at=started_at,
        completed_at=completed_at,
        stop_reason=stop_reason,
        frames=measurement.frame_count if measurement else None,
        dropped_frames=measurement.dropped_frames if measurement else None,
        warnings=warnings,
        errors=errors,
        output_files=output_files,
    )
    return MeasurementOutcome(result, final_snapshot, final_dashboard, exception)


def _apply_config(
    client: ServalClient,
    effective: DetectorConfiguration,
    warnings: list[str],
    errors: list[str],
) -> DetectorConfiguration:
    """Send the configuration and read it back, warning on any difference.

    A reply HERMES cannot read (bad JSON or values its models refuse) counts as
    not applied, like a failed request.
    """
    _MEASUREMENT_LOGGER.info(
        "Applying detector configuration",
        event_type="acquisition.serval.detector_config_apply",
        trigger_mode=effective.trigger_mode,
        n_triggers=effective.n_triggers,
        exposure_time_s=effective.exposure_time_s,
        trigger_period_s=effective.trigger_period_s,
        global_timestamp_interval_s=effective.global_timestamp_interval_s,
    )
    try:
        client.put_detector_config(effective)
        applied = client.get_detector_config()
    except (ServalClientError, ValueError) as error:
        errors.append(str(error))
        _MEASUREMENT_LOGGER.error(
            "Could not apply detector configuration: {error}",
            event_type="acquisition.serval.detector_config_failed",
            error=str(error),
        )
        return effective

    _warn_on_config_drift(effective, applied, warnings)
    return applied


def _warn_on_config_drift(
    sent: DetectorConfiguration,
    applied: DetectorConfiguration,
    warnings: list[str],
) -> None:
    sent_fields = sent.model_dump(by_alias=True, exclude_none=True)
    applied_fields = applied.model_dump(by_alias=True, exclude_none=True)
    for key, value in sent_fields.items():
        if applied_fields.get(key) != value:
            message = (
                f"detector config {key} was set to {value!r} but SERVAL reports "
                f"{applied_fields.get(key)!r}"
            )
            warnings.append(message)
            _MEASUREMENT_LOGGER.warning(
                "Detector config drift: {message}",
                event_type="acquisition.serval.detector_config_drift",
                message=message,
                field=key,
                sent=value,
                applied=applied_fields.get(key),
            )


def _monitor(
    client: ServalClient,
    wait_limit_s: float,
    warnings: list[str],
    on_poll: Callable[[ServalDashboardMeasurement | None], None] | None = None,
) -> str:
    """Watch the dashboard until the measurement is idle again or times out.

    Returns "completed" when the camera returned to idle on its own,
    "stopped_after_timeout" when the wait limit was reached and HERMES stopped
    the measurement, or "no_activity" when the camera never left idle and made
    no frames within the start window. Each notice SERVAL adds is logged once,
    when it first appears; `_check_notifications` checks them all at the end.
    Transient dashboard read failures are tolerated: the poll simply retries
    until the deadline. When ``on_poll`` is given it is called with the
    measurement each poll, before the idle/timeout checks, so the caller can
    act on new frames as they land.
    """
    start = time.monotonic()
    deadline = start + wait_limit_s
    start_deadline = start + min(_START_TIMEOUT_S, wait_limit_s)
    last_progress_log = start
    seen_active = False
    notifications_seen = 0

    while True:
        dashboard = _read_dashboard(client)
        measurement = dashboard.measurement if dashboard is not None else None
        if dashboard is not None:
            notifications = dashboard.server.notifications
            for notification in notifications[notifications_seen:]:
                _log_notification(notification)
            notifications_seen = len(notifications)
        if on_poll is not None:
            on_poll(measurement)
        status = measurement.status if measurement is not None else None
        frames = measurement.frame_count if measurement is not None else None
        if status in _ACTIVE_STATUSES or frames:
            seen_active = True

        if status == "DA_IDLE" and seen_active:
            return "completed"

        now = time.monotonic()
        # Decide "never started" before "timed out": when the camera never left
        # idle and made no frames, that is the more accurate reason even if the
        # wait limit was reached at the same time.
        if not seen_active and now >= start_deadline:
            warning = "measurement never left the idle state and made no frames"
            warnings.append(warning)
            _MEASUREMENT_LOGGER.warning(
                warning,
                event_type="acquisition.serval.measurement_no_activity",
            )
            return "no_activity"

        if now >= deadline:
            warning = f"measurement did not finish within {wait_limit_s:.0f} s; stopping it"
            warnings.append(warning)
            _MEASUREMENT_LOGGER.warning(
                warning,
                event_type="acquisition.serval.measurement_timeout",
                wait_limit_s=wait_limit_s,
            )
            _safe_stop(client, warnings)
            return "stopped_after_timeout"

        if now - last_progress_log >= _PROGRESS_LOG_INTERVAL_S and measurement is not None:
            _MEASUREMENT_LOGGER.info(
                "Measurement running: status {status}, {frames} frames, "
                "{elapsed} s elapsed, {time_left} s left",
                event_type="acquisition.serval.measurement_progress",
                status=status,
                frames=measurement.frame_count,
                dropped_frames=measurement.dropped_frames,
                elapsed=measurement.elapsed_time_s,
                time_left=measurement.time_left_s,
                pixel_event_rate=measurement.pixel_event_rate,
            )
            last_progress_log = now

        time.sleep(_POLL_INTERVAL_S)


def _read_dashboard(client: ServalClient) -> ServalDashboard | None:
    try:
        return client.get_dashboard()
    except ServalClientError as error:
        _MEASUREMENT_LOGGER.debug(
            "Dashboard read failed mid-measurement; will retry: {error}",
            event_type="acquisition.serval.measurement_poll_failed",
            error=str(error),
        )
        return None


def _check_frames(
    stop_reason: str,
    measurement: ServalDashboardMeasurement,
    warnings: list[str],
    errors: list[str],
) -> None:
    """Fail a finished measurement with no complete frames; warn on dropped ones.

    SERVAL counts a frame as dropped when it cannot build a complete frame from
    the readout (in the runs seen so far, its raw file had no end-of-readout
    word), and leaves it out of `FrameCount`. Its raw file is still written,
    but a measurement the camera finished with no complete frames did not work,
    so that is an error.
    """
    frames = measurement.frame_count
    dropped = measurement.dropped_frames or 0
    if stop_reason == "completed" and frames == 0:
        error = (
            f"the measurement finished with no complete frames: SERVAL reports "
            f"0 frames and {dropped} dropped"
        )
        errors.append(error)
        _MEASUREMENT_LOGGER.error(
            "Measurement failed: {error}",
            event_type="acquisition.serval.no_frames",
            error=error,
            dropped_frames=dropped,
        )
    elif dropped > 0:
        warning = (
            f"SERVAL reports {dropped} dropped frames (frames whose readout did "
            f"not complete) and {frames} complete frames"
        )
        warnings.append(warning)
        _MEASUREMENT_LOGGER.warning(
            warning,
            event_type="acquisition.serval.dropped_frames",
            frames=frames,
            dropped_frames=dropped,
        )


def _log_notification(notification: ServalDashboardNotification) -> None:
    """Log a notice SERVAL raised during the measurement; a warning when serious."""
    level = "WARNING" if notification.type in _SERIOUS_NOTIFICATION_TYPES else "INFO"
    _MEASUREMENT_LOGGER.log(
        level,
        "SERVAL {notification_type} notice: {message}",
        event_type="acquisition.serval.notification",
        notification_type=notification.type,
        domain=notification.domain,
        message=notification.message,
        reference_id=notification.reference_id,
    )


def _check_notifications(
    dashboard: ServalDashboard,
    warnings: list[str],
    errors: list[str],
) -> None:
    """Fail a measurement whose disk filled up; warn on other serious notices.

    SERVAL clears its notices when a measurement starts, so the final dashboard
    holds every notice from this one. When free disk space falls below its
    limit, SERVAL stops writing raw files and adds a `REF_ID_DISK_FULL` notice
    that stays in the list even after space is freed, so a missing stretch of
    data is never recorded as a working run.
    """
    detail = None
    for notification in dashboard.server.notifications:
        if notification.reference_id == "REF_ID_DISK_FULL":
            detail = detail or notification.message
        elif notification.type in _SERIOUS_NOTIFICATION_TYPES:
            warnings.append(
                f"SERVAL {notification.type} notice: {notification.message}"
            )
    for disk in dashboard.server.disk_space:
        if disk.disk_limit_reached:
            detail = detail or f"DiskLimitReached is set for {disk.path}"
    if detail is None:
        return
    error = f"SERVAL ran out of disk space and stopped writing raw files: {detail}"
    errors.append(error)
    _MEASUREMENT_LOGGER.error(
        "Measurement failed: {error}",
        event_type="acquisition.serval.disk_full",
        error=error,
    )


def _not_started_outcome(
    client: ServalClient,
    applied: DetectorConfiguration | None,
    warnings: list[str],
    errors: list[str],
    *,
    stop_reason: str,
) -> MeasurementOutcome:
    """Build a failed outcome for a measurement that was never started.

    Used when the effective configuration is invalid or could not be applied:
    nothing was recorded, so there are no output files, but the final detector
    state is still read so the record shows what the camera looked like.
    """
    final_dashboard, final_snapshot = _read_final_state(client, applied, warnings)
    result = ServalAcquisitionResult(
        started_at=None,
        completed_at=utc_now(),
        stop_reason=stop_reason,
        frames=None,
        dropped_frames=None,
        warnings=warnings,
        errors=errors,
        output_files=[],
    )
    return MeasurementOutcome(result, final_snapshot, final_dashboard)


def _read_final_state(
    client: ServalClient,
    applied: DetectorConfiguration | None,
    warnings: list[str],
) -> tuple[ServalDashboard | None, DetectorSnapshot]:
    """Read the final dashboard and health for the record, tolerating failures.

    A reply HERMES cannot read (bad JSON or values its models refuse) raises a
    ValueError; that is tolerated too, so the outcome is still recorded.
    """
    dashboard: ServalDashboard | None = None
    health = None
    try:
        dashboard = client.get_dashboard()
        health = client.get_detector_health()
    except (ServalClientError, ValueError) as error:
        warnings.append(f"could not read the final detector state: {error}")
        _MEASUREMENT_LOGGER.warning(
            "Could not read the final detector state: {error}",
            event_type="acquisition.serval.final_state_failed",
            error=str(error),
        )
    return dashboard, DetectorSnapshot(configuration=applied, health=health)


def _collect_output_files(raw_data_directory: Path) -> list[FileReference]:
    """Gather the raw `.tpx3` files SERVAL wrote."""
    if not raw_data_directory.is_dir():
        return []
    return [
        FileReference(path=path.resolve())
        for path in sorted(raw_data_directory.glob("*.tpx3"))
    ]


def _safe_stop(client: ServalClient, warnings: list[str]) -> None:
    """Ask SERVAL to stop the measurement, recording (not raising) any failure."""
    try:
        client.measurement_stop()
    except ServalClientError as error:
        warnings.append(f"could not stop the measurement cleanly: {error}")
        _MEASUREMENT_LOGGER.warning(
            "Could not stop the measurement cleanly: {error}",
            event_type="acquisition.serval.measurement_stop_failed",
            error=str(error),
        )


def _wait_limit_s(
    timing: ServalRunTiming | None, applied: DetectorConfiguration
) -> float:
    """How long HERMES waits for the measurement before it stops it.

    `run_timing.max_wait_s` when it is set. Otherwise twice the run's expected
    length plus `_WAIT_MARGIN_S`, using the detector configuration SERVAL reports
    after HERMES sent it (so timing from `detector_config`, `detector_config_file`,
    or `run_timing` all count). When that length cannot be told, `_DEFAULT_WAIT_S`.
    """
    if timing is not None and timing.max_wait_s is not None:
        return timing.max_wait_s
    expected = _expected_duration_s(applied)
    if expected is not None:
        return expected * 2 + _WAIT_MARGIN_S
    _MEASUREMENT_LOGGER.warning(
        "HERMES cannot tell how long a {trigger_mode} run takes, so it stops the "
        "run after {wait_limit_s:.0f} s; set run_timing.max_wait_s for a longer run",
        event_type="acquisition.serval.wait_limit_default",
        trigger_mode=applied.trigger_mode,
        wait_limit_s=_DEFAULT_WAIT_S,
    )
    return _DEFAULT_WAIT_S


def _expected_duration_s(applied: DetectorConfiguration) -> float | None:
    """Estimate how long the run takes from the detector configuration.

    This can be told only in the modes where the camera triggers itself every
    trigger period: the trigger count times the trigger period. SERVAL takes a
    trigger count of 0 as 1. In the other modes each frame waits for an external
    or software trigger, so this returns None.
    """
    if applied.trigger_mode not in _TRIGGER_PERIOD_MODES:
        return None
    if applied.n_triggers is None or not applied.trigger_period_s:
        return None
    return max(applied.n_triggers, 1) * applied.trigger_period_s
