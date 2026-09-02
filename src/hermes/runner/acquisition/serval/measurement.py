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
# (run_timing.max_wait_s). Then HERMES estimates a limit from the run's expected
# duration and caps it at _MAX_WAIT_S; a run whose length cannot be computed (for
# example a continuous run) waits _DEFAULT_WAIT_S before HERMES stops it.
_MAX_WAIT_S = 300.0
_DEFAULT_WAIT_S = 300.0

# Statuses that mean the camera is busy with the measurement (not idle).
_ACTIVE_STATUSES = ("DA_PREPARING", "DA_RECORDING", "DA_STOPPING")


class ServalMeasurementError(Exception):
    """Raised when a measurement cannot be run at all."""


class MeasurementOutcome(NamedTuple):
    """What one measurement produced, for the run to record."""

    result: ServalAcquisitionResult
    final_snapshot: DetectorSnapshot
    final_dashboard: ServalDashboard


def build_effective_detector_config(
    config: ServalAcquisitionConfig,
) -> DetectorConfiguration:
    """Compose the detector configuration to send to SERVAL.

    Start from the JSON at `detector_config_file` when it is set (it wins over
    the inline `detector_config`), otherwise the inline `detector_config`, or an
    empty configuration when neither is given. Then layer the `run_timing`
    values on top: trigger mode, exposure time, trigger period, and trigger
    count (which maps to the detector's `n_triggers`).
    """
    base = _load_base_config(config)
    timing = config.run_timing
    if timing is None:
        return base

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
    return DetectorConfiguration.model_validate(merged.model_dump())


def _load_base_config(config: ServalAcquisitionConfig) -> DetectorConfiguration:
    if config.detector_config_file is not None:
        text = config.detector_config_file.read_text()
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

    started_at = utc_now()
    stop_reason = "completed"
    try:
        client.measurement_start()
        _MEASUREMENT_LOGGER.info(
            "Measurement started",
            event_type="acquisition.serval.measurement_start",
            trigger_mode=effective.trigger_mode,
            n_triggers=effective.n_triggers,
            exposure_time_s=effective.exposure_time_s,
        )
        stop_reason = _monitor(
            client, _wait_limit_s(config.run_timing), warnings, on_poll
        )
    except ServalClientError as error:
        errors.append(str(error))
        stop_reason = "failed"
        _MEASUREMENT_LOGGER.error(
            "Measurement failed to run: {error}",
            event_type="acquisition.serval.measurement_failed",
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
    return MeasurementOutcome(result, final_snapshot, final_dashboard)


def _apply_config(
    client: ServalClient,
    effective: DetectorConfiguration,
    warnings: list[str],
    errors: list[str],
) -> DetectorConfiguration:
    """Send the configuration and read it back, warning on any difference."""
    _warn_if_global_timestamps_disabled(effective, warnings)
    _MEASUREMENT_LOGGER.info(
        "Applying detector configuration",
        event_type="acquisition.serval.detector_config_apply",
        trigger_mode=effective.trigger_mode,
        n_triggers=effective.n_triggers,
        exposure_time_s=effective.exposure_time_s,
        trigger_period_s=effective.trigger_period_s,
    )
    try:
        client.put_detector_config(effective)
        applied = client.get_detector_config()
    except ServalClientError as error:
        errors.append(str(error))
        _MEASUREMENT_LOGGER.error(
            "Could not apply detector configuration: {error}",
            event_type="acquisition.serval.detector_config_failed",
            error=str(error),
        )
        return effective

    _warn_on_config_drift(effective, applied, warnings)
    return applied


def _warn_if_global_timestamps_disabled(
    effective: DetectorConfiguration,
    warnings: list[str],
) -> None:
    """Warn when this run's configuration does not enable global timestamps.

    SERVAL writes periodic global timestamps only when GlobalTimestampInterval
    is a positive number of seconds. When this run leaves it unset HERMES sends
    nothing for it, so SERVAL keeps whatever it had; when this run sets it to
    zero or a negative value HERMES sends that and SERVAL turns them off. Either
    way, unless SERVAL already has them on the raw `.tpx3` will have none, and
    unpacking then cannot place pixel, TDC, and event times on one comparable
    time axis for time-of-flight. This is a valid configuration, so it is a
    warning, not a failure.
    """
    interval = effective.global_timestamp_interval_s
    if interval is not None and interval > 0:
        return
    if interval is None:
        cause = (
            "; this run leaves GlobalTimestampInterval unset, so unless SERVAL "
            "already has them on the raw .tpx3 will have none"
        )
    else:
        cause = (
            f"; this run sets GlobalTimestampInterval to {interval!r}, which turns "
            "them off on SERVAL, so the raw .tpx3 will have none"
        )
    warning = (
        "this run does not enable global timestamps" + cause + ", and unpacking "
        "cannot place pixel, TDC, and event times on one comparable time axis for "
        "time-of-flight"
    )
    warnings.append(warning)
    _MEASUREMENT_LOGGER.warning(
        warning,
        event_type="acquisition.serval.global_timestamp_disabled",
        global_timestamp_interval_s=interval,
    )


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
    no frames within the start window. Transient dashboard read failures are
    tolerated: the poll simply retries until the deadline. When ``on_poll`` is
    given it is called with the measurement each poll, before the idle/timeout
    checks, so the caller can act on new frames as they land.
    """
    start = time.monotonic()
    deadline = start + wait_limit_s
    start_deadline = start + min(_START_TIMEOUT_S, wait_limit_s)
    last_progress_log = start
    seen_active = False

    while True:
        measurement = _read_measurement(client)
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


def _read_measurement(client: ServalClient):
    try:
        return client.get_dashboard().measurement
    except ServalClientError as error:
        _MEASUREMENT_LOGGER.debug(
            "Dashboard read failed mid-measurement; will retry: {error}",
            event_type="acquisition.serval.measurement_poll_failed",
            error=str(error),
        )
        return None


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
    """Read the final dashboard and health for the record, tolerating failures."""
    dashboard: ServalDashboard | None = None
    health = None
    try:
        dashboard = client.get_dashboard()
        health = client.get_detector_health()
    except ServalClientError as error:
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


def _wait_limit_s(timing: ServalRunTiming | None) -> float:
    if timing is not None and timing.max_wait_s is not None:
        return timing.max_wait_s
    expected = _expected_duration_s(timing)
    if expected is None:
        return _DEFAULT_WAIT_S
    return min(expected * 2 + 10.0, _MAX_WAIT_S)


def _expected_duration_s(timing: ServalRunTiming | None) -> float | None:
    """Estimate how long the run should take from its timing, if it can be told."""
    if timing is None:
        return None
    count = timing.trigger_count
    if count:
        per_trigger = timing.trigger_period_s or timing.exposure_time_s
        if per_trigger:
            return count * per_trigger
    return timing.exposure_time_s
