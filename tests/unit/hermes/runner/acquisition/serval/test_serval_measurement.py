from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from loguru import logger

from hermes.runner.acquisition.serval import measurement as measurement_module
from hermes.runner.acquisition.serval.client import ServalClientError
from hermes.runner.acquisition.serval.measurement import (
    _wait_limit_s,
    build_effective_detector_config,
    run_measurement,
)
from hermes.state.models.acquisition.serval import (
    ServalAcquisitionConfig,
    ServalDashboard,
    ServalDashboardDetector,
    ServalDashboardDiskSpace,
    ServalDashboardMeasurement,
    ServalDashboardNotification,
    ServalDashboardServer,
    ServalRunTiming,
    ServalServer,
)
from hermes.state.models.detector import DetectorConfiguration, DetectorHealth


def _config(**kwargs: object) -> ServalAcquisitionConfig:
    return ServalAcquisitionConfig(
        serval=ServalServer(url="http://serval.test"), **kwargs
    )


def _install_fake_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make time deterministic: sleep advances a fake clock, monotonic reads it."""
    clock = {"t": 0.0}
    monkeypatch.setattr(measurement_module.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(
        measurement_module.time,
        "sleep",
        lambda seconds: clock.__setitem__("t", clock["t"] + seconds),
    )


class _FakeClient:
    """A SERVAL client that returns a scripted sequence of dashboard statuses."""

    def __init__(
        self,
        statuses: list[str],
        *,
        frame_count: int = 5,
        dropped_frames: int = 0,
        notifications: tuple[ServalDashboardNotification, ...] = (),
        disk_space: tuple[ServalDashboardDiskSpace, ...] = (),
        raw_dir: Path | None = None,
        tpx3_names: tuple[str, ...] = (),
        put_error: ServalClientError | None = None,
    ) -> None:
        self._statuses = list(statuses)
        self._frame_count = frame_count
        self._dropped_frames = dropped_frames
        self._notifications = list(notifications)
        self._disk_space = list(disk_space)
        self._raw_dir = raw_dir
        self._tpx3_names = tpx3_names
        self._put_error = put_error
        self.put_config: DetectorConfiguration | None = None
        self.started = False
        self.stopped = False

    def put_detector_config(self, config: DetectorConfiguration) -> None:
        if self._put_error is not None:
            raise self._put_error
        self.put_config = config

    def get_detector_config(self) -> DetectorConfiguration | None:
        return self.put_config

    def get_detector_health(self) -> DetectorHealth:
        return DetectorHealth(bias_voltage_v=12.6)

    def measurement_start(self) -> httpx.Response:
        self.started = True
        if self._raw_dir is not None:
            self._raw_dir.mkdir(parents=True, exist_ok=True)
            for name in self._tpx3_names:
                (self._raw_dir / name).write_bytes(b"tpx3")
        return httpx.Response(200, text="OK")

    def measurement_stop(self) -> httpx.Response:
        self.stopped = True
        return httpx.Response(200, text="OK")

    def get_dashboard(self) -> ServalDashboard:
        status = self._statuses.pop(0) if self._statuses else "DA_IDLE"
        return ServalDashboard(
            server=ServalDashboardServer(
                software_version="3.3.0",
                notifications=self._notifications,
                disk_space=self._disk_space,
            ),
            measurement=ServalDashboardMeasurement(
                status=status,
                frame_count=self._frame_count,
                dropped_frames=self._dropped_frames,
            ),
            detector=ServalDashboardDetector(detector_type="Tpx3"),
        )


def test_build_effective_detector_config_layers_timing_over_base() -> None:
    config = _config(
        detector_config=DetectorConfiguration(
            bias_voltage_v=12.0, trigger_mode="CONTINUOUS"
        ),
        run_timing=ServalRunTiming(
            trigger_mode="AUTOTRIGSTART_TIMERSTOP",
            exposure_time_s=0.1,
            trigger_period_s=0.2,
            trigger_count=5,
        ),
    )

    effective = build_effective_detector_config(config)

    # Untouched base field is kept; timing fields override.
    assert effective.bias_voltage_v == 12.0
    assert effective.trigger_mode == "AUTOTRIGSTART_TIMERSTOP"
    assert effective.exposure_time_s == 0.1
    assert effective.trigger_period_s == 0.2
    # trigger_count maps onto the detector's n_triggers.
    assert effective.n_triggers == 5


def test_build_effective_detector_config_file_wins_over_inline(tmp_path: Path) -> None:
    config_file = tmp_path / "detector.json"
    config_file.write_text('{"BiasVoltage": 30, "TriggerMode": "CONTINUOUS"}')
    config = _config(
        detector_config=DetectorConfiguration(bias_voltage_v=12.0),
        detector_config_file=config_file,
        run_timing=ServalRunTiming(trigger_count=3),
    )

    effective = build_effective_detector_config(config)

    # The file's 30 V wins over the inline 12 V.
    assert effective.bias_voltage_v == 30
    assert effective.n_triggers == 3


def test_build_effective_detector_config_from_timing_alone() -> None:
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.5, trigger_count=2)
    )

    effective = build_effective_detector_config(config)

    assert effective.exposure_time_s == 0.5
    assert effective.n_triggers == 2


def test_build_effective_detector_config_requires_trigger_period_for_sequential() -> None:
    # Automatic (sequential) mode with an exposure but no trigger period breaks
    # SERVAL's dead-time rule, so the effective config must refuse to build
    # rather than let SERVAL reject it after launch.
    config = _config(
        run_timing=ServalRunTiming(
            trigger_mode="AUTOTRIGSTART_TIMERSTOP",
            exposure_time_s=10.0,
        )
    )

    with pytest.raises(ValueError, match="trigger period"):
        build_effective_detector_config(config)


def test_build_effective_detector_config_rejects_exposure_too_close_to_period() -> None:
    # The exposure must be at least 0.002 s shorter than the trigger period.
    config = _config(
        run_timing=ServalRunTiming(
            trigger_mode="AUTOTRIGSTART_TIMERSTOP",
            exposure_time_s=10.0,
            trigger_period_s=10.001,
        )
    )

    with pytest.raises(ValueError, match="shorter than"):
        build_effective_detector_config(config)


def test_build_effective_detector_config_allows_compliant_sequential_timing() -> None:
    config = _config(
        run_timing=ServalRunTiming(
            trigger_mode="AUTOTRIGSTART_TIMERSTOP",
            exposure_time_s=10.0,
            trigger_period_s=10.5,
        )
    )

    effective = build_effective_detector_config(config)

    assert effective.exposure_time_s == 10.0
    assert effective.trigger_period_s == 10.5


def test_build_effective_detector_config_rejects_interval_over_half_a_pixel_wrap() -> None:
    # Pixels more than about 13.4 s after a global timestamp would come out
    # 26.84 s early, so an interval this long is refused even with long frames.
    config = _config(
        detector_config=DetectorConfiguration(global_timestamp_interval_s=20.0),
        run_timing=ServalRunTiming(
            trigger_mode="AUTOTRIGSTART_TIMERSTOP",
            exposure_time_s=10.0,
            trigger_period_s=50.0,
        ),
    )

    with pytest.raises(ValueError, match="longer than 13.0 s"):
        build_effective_detector_config(config)


def test_build_effective_detector_config_rejects_interval_over_half_the_trigger_period() -> None:
    # With one raw file per frame, and global timestamps a few ms off schedule,
    # an interval over half the trigger period can leave a file with none.
    config = _config(
        detector_config=DetectorConfiguration(global_timestamp_interval_s=1.5),
        run_timing=ServalRunTiming(
            trigger_mode="AUTOTRIGSTART_TIMERSTOP",
            exposure_time_s=1.95,
            trigger_period_s=2.0,
        ),
    )

    with pytest.raises(ValueError, match="longer than half the 2.0 s trigger period"):
        build_effective_detector_config(config)


@pytest.mark.parametrize("interval_s", [0.0, -1.0])
def test_build_effective_detector_config_refuses_global_timestamps_off(
    interval_s: float,
) -> None:
    config = _config(
        detector_config=DetectorConfiguration(global_timestamp_interval_s=interval_s),
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5),
    )

    with pytest.raises(ValueError, match="turns global timestamps off"):
        build_effective_detector_config(config)


@pytest.mark.parametrize("trigger_mode", ["AUTOTRIGSTART_TIMERSTOP", "CONTINUOUS"])
def test_build_effective_detector_config_rejects_frames_under_100_ms(
    trigger_mode: str,
) -> None:
    config = _config(
        detector_config=DetectorConfiguration(global_timestamp_interval_s=0.01),
        run_timing=ServalRunTiming(
            trigger_mode=trigger_mode,
            exposure_time_s=0.05,
            trigger_period_s=0.09,
        ),
    )

    with pytest.raises(ValueError, match="shorter than 0.1 s"):
        build_effective_detector_config(config)


def test_build_effective_detector_config_checks_interval_without_run_timing() -> None:
    config = _config(
        detector_config=DetectorConfiguration(global_timestamp_interval_s=14.0),
    )

    with pytest.raises(ValueError, match="GlobalTimestampInterval"):
        build_effective_detector_config(config)


@pytest.mark.parametrize(
    ("interval_s", "trigger_mode", "trigger_period_s"),
    [
        # The tested settings: 1 s global timestamps, 2 s or 10 s frames.
        (1.0, "AUTOTRIGSTART_TIMERSTOP", 2.0),
        (1.0, "AUTOTRIGSTART_TIMERSTOP", 10.1),
        # Exactly half the trigger period, at the shortest frame.
        (0.05, "CONTINUOUS", 0.1),
        # Externally triggered frames have no trigger period to compare with.
        (13.0, "PEXSTART_TIMERSTOP", 0.2),
    ],
)
def test_build_effective_detector_config_accepts_safe_intervals(
    interval_s: float, trigger_mode: str, trigger_period_s: float
) -> None:
    config = _config(
        detector_config=DetectorConfiguration(global_timestamp_interval_s=interval_s),
        run_timing=ServalRunTiming(
            trigger_mode=trigger_mode,
            exposure_time_s=0.01,
            trigger_period_s=trigger_period_s,
        ),
    )

    effective = build_effective_detector_config(config)

    assert effective.global_timestamp_interval_s == interval_s


@pytest.mark.parametrize(
    ("trigger_mode", "trigger_period_s", "expected_interval_s"),
    [
        # Frames of 2 s or longer get the 1 s default.
        ("AUTOTRIGSTART_TIMERSTOP", 2.0, 1.0),
        ("AUTOTRIGSTART_TIMERSTOP", 10.1, 1.0),
        # Shorter frames get half the frame length.
        ("AUTOTRIGSTART_TIMERSTOP", 0.2, 0.1),
        ("CONTINUOUS", 1.0, 0.5),
        # Externally triggered frames have no known length, so 1 s.
        ("PEXSTART_TIMERSTOP", 0.2, 1.0),
        (None, None, 1.0),
    ],
)
def test_build_effective_detector_config_fills_in_unset_interval(
    trigger_mode: str | None,
    trigger_period_s: float | None,
    expected_interval_s: float,
) -> None:
    config = _config(
        run_timing=ServalRunTiming(
            trigger_mode=trigger_mode,
            exposure_time_s=0.01,
            trigger_period_s=trigger_period_s,
        ),
    )

    effective = build_effective_detector_config(config)

    assert effective.global_timestamp_interval_s == expected_interval_s


def test_build_effective_detector_config_fills_in_unset_interval_without_run_timing() -> None:
    config = _config(detector_config=DetectorConfiguration(bias_voltage_v=12.0))

    effective = build_effective_detector_config(config)

    assert effective.global_timestamp_interval_s == 1.0
    assert effective.bias_voltage_v == 12.0


def test_detector_configuration_enforces_sequential_dead_time() -> None:
    # The rule lives on the model itself, so an inline detector_config is checked
    # at construction, not only once it reaches SERVAL.
    with pytest.raises(ValueError, match="shorter than"):
        DetectorConfiguration(
            trigger_mode="AUTOTRIGSTART_TIMERSTOP",
            exposure_time_s=10.0,
            trigger_period_s=10.001,
        )


def test_run_measurement_records_files_and_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(
        ["DA_RECORDING", "DA_IDLE"],
        frame_count=5,
        raw_dir=raw,
        tpx3_names=("a.tpx3", "b.tpx3"),
    )
    config = _config(
        run_timing=ServalRunTiming(
            trigger_mode="AUTOTRIGSTART_TIMERSTOP",
            exposure_time_s=0.1,
            trigger_period_s=0.2,
            trigger_count=5,
        )
    )

    outcome = run_measurement(client, config, raw)

    assert outcome.result.stop_reason == "completed"
    assert outcome.result.frames == 5
    assert outcome.result.errors == []
    assert client.started is True
    # The effective config we applied carried the trigger count.
    assert client.put_config is not None
    assert client.put_config.n_triggers == 5
    # Both raw files were gathered and the final health was read.
    assert len(outcome.result.output_files) == 2
    assert outcome.result.output_files[0].path.name == "a.tpx3"
    assert outcome.final_snapshot.health.bias_voltage_v == 12.6


def test_run_measurement_does_not_start_when_config_cannot_be_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    # SERVAL rejects the configuration, so recording would happen at unknown,
    # unverified settings. HERMES must not start the measurement or write files.
    client = _FakeClient(
        ["DA_IDLE"],
        raw_dir=raw,
        put_error=ServalClientError("config rejected"),
    )
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )

    outcome = run_measurement(client, config, raw)

    assert outcome.result.stop_reason == "config_not_applied"
    assert outcome.result.output_files == []
    assert outcome.result.errors
    assert client.started is False


def test_run_measurement_sends_the_default_global_timestamp_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(["DA_RECORDING", "DA_IDLE"], raw_dir=raw)
    # run_timing alone leaves GlobalTimestampInterval unset; a freshly started
    # SERVAL has global timestamps off, so HERMES must send one.
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )

    outcome = run_measurement(client, config, raw)

    assert outcome.result.stop_reason == "completed"
    assert client.put_config is not None
    assert client.put_config.global_timestamp_interval_s == 1.0


def test_run_measurement_does_not_start_with_global_timestamps_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(["DA_IDLE"], raw_dir=raw)
    config = _config(
        detector_config=DetectorConfiguration(global_timestamp_interval_s=0),
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5),
    )

    outcome = run_measurement(client, config, raw)

    assert outcome.result.stop_reason == "invalid_configuration"
    assert any("turns global timestamps off" in error for error in outcome.result.errors)
    assert client.put_config is None
    assert client.started is False


def test_warn_on_config_drift_reports_difference_without_crashing() -> None:
    # Regression: the drift warning template references {message}; the logging
    # call must supply it, or Loguru raises KeyError the moment a field drifts.
    sent = DetectorConfiguration(bias_voltage_v=12.0)
    applied = DetectorConfiguration(bias_voltage_v=30.0)
    warnings: list[str] = []

    records: list[dict[str, object]] = []
    sink_id = logger.add(
        lambda message: records.append(message.record),
        filter=lambda record: record["extra"].get("event_type")
        == "acquisition.serval.detector_config_drift",
    )
    try:
        measurement_module._warn_on_config_drift(sent, applied, warnings)
    finally:
        logger.remove(sink_id)

    assert any("BiasVoltage" in warning for warning in warnings)
    assert len(records) == 1
    assert records[0]["extra"]["field"] == "BiasVoltage"
    assert records[0]["extra"]["sent"] == 12.0
    assert records[0]["extra"]["applied"] == 30.0


def test_run_measurement_times_out_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    raw.mkdir()
    # The camera stays recording forever, so HERMES hits the wait limit.
    client = _FakeClient(["DA_RECORDING"] * 1000, raw_dir=raw)
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )

    outcome = run_measurement(client, config, raw)

    assert outcome.result.stop_reason == "stopped_after_timeout"
    assert client.stopped is True
    assert any("did not finish" in warning for warning in outcome.result.warnings)


def test_run_measurement_keeps_a_failed_stop_as_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    raw.mkdir()
    # The camera stays recording past the wait limit, and SERVAL then refuses
    # the stop request.
    client = _FakeClient(["DA_RECORDING"] * 1000, raw_dir=raw)

    def refuse_to_stop() -> httpx.Response:
        raise ServalClientError("SERVAL GET /measurement/stop could not be sent")

    client.measurement_stop = refuse_to_stop
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )

    outcome, _records, event_types = _run_and_capture_logs(client, config, raw)

    assert outcome.result.stop_reason == "stopped_after_timeout"
    assert outcome.exception is None
    assert outcome.result.warnings[-1] == (
        "could not stop the measurement cleanly: "
        "SERVAL GET /measurement/stop could not be sent"
    )
    assert "acquisition.serval.measurement_stop_failed" in event_types


_AUTO_TRIGGER_CONFIG = DetectorConfiguration(
    trigger_mode="AUTOTRIGSTART_TIMERSTOP",
    exposure_time_s=0.1,
    trigger_period_s=0.2,
    n_triggers=5,
)


def test_wait_limit_uses_configured_max_wait_s() -> None:
    # An explicit max_wait_s is used as-is, overriding the ~12 s estimate.
    timing = ServalRunTiming(max_wait_s=7200.0)
    assert _wait_limit_s(timing, _AUTO_TRIGGER_CONFIG) == 7200.0


def test_wait_limit_estimates_from_duration_without_max_wait_s() -> None:
    # Without an explicit limit HERMES estimates one: 5 triggers * 0.2 s * 2 + 10.
    assert _wait_limit_s(None, _AUTO_TRIGGER_CONFIG) == pytest.approx(12.0)


def test_wait_limit_is_not_capped_for_a_long_run() -> None:
    # Regression for #139: 31 triggers every 10.1 s is about 313 s, and the old
    # 300 s cap stopped the run before its last frame.
    applied = DetectorConfiguration(
        trigger_mode="AUTOTRIGSTART_TIMERSTOP",
        exposure_time_s=10.0,
        trigger_period_s=10.1,
        n_triggers=31,
    )
    assert _wait_limit_s(None, applied) == pytest.approx(31 * 10.1 * 2 + 10)


def test_wait_limit_for_continuous_mode_uses_the_trigger_period() -> None:
    applied = DetectorConfiguration(
        trigger_mode="CONTINUOUS", trigger_period_s=2.0, n_triggers=100
    )
    assert _wait_limit_s(None, applied) == pytest.approx(410.0)


def test_wait_limit_takes_a_trigger_count_of_zero_as_one() -> None:
    # SERVAL sends max(1, nTriggers) to the camera, so 0 is one frame.
    applied = _AUTO_TRIGGER_CONFIG.model_copy(update={"n_triggers": 0})
    assert _wait_limit_s(None, applied) == pytest.approx(10.4)


@pytest.mark.parametrize(
    "trigger_mode", ["PEXSTART_TIMERSTOP", "SOFTWARESTART_SOFTWARESTOP", None]
)
def test_wait_limit_uses_the_default_when_the_length_cannot_be_told(
    trigger_mode: str | None,
) -> None:
    # Frames that wait for an external or software trigger have no set length.
    applied = _AUTO_TRIGGER_CONFIG.model_copy(update={"trigger_mode": trigger_mode})
    assert _wait_limit_s(None, applied) == 300.0


def test_run_measurement_waits_for_timing_set_in_detector_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression for #139: timing set in detector_config (not run_timing) was
    # ignored, so this ~1,100 s run got a 12 s limit and was stopped as failed.
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    # 1,100 s of recording at one poll every 0.5 s, then idle.
    client = _FakeClient(["DA_RECORDING"] * 2200 + ["DA_IDLE"], raw_dir=raw)
    config = _config(
        detector_config=DetectorConfiguration(
            trigger_mode="AUTOTRIGSTART_TIMERSTOP",
            trigger_period_s=1.1,
            n_triggers=1000,
        ),
        run_timing=ServalRunTiming(exposure_time_s=1.0),
    )

    outcome = run_measurement(client, config, raw)

    assert outcome.result.stop_reason == "completed"
    assert client.stopped is False
    assert outcome.result.warnings == []


def test_run_timing_rejects_non_positive_max_wait_s() -> None:
    with pytest.raises(ValueError, match="max_wait_s"):
        ServalRunTiming(max_wait_s=0)


def test_run_measurement_honors_configured_max_wait_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    raw.mkdir()
    # The camera stays recording forever. The estimated limit would be ~12 s,
    # but max_wait_s raises it, so HERMES stops the run only at the configured 50 s.
    client = _FakeClient(["DA_RECORDING"] * 1000, raw_dir=raw)
    config = _config(
        run_timing=ServalRunTiming(
            trigger_mode="AUTOTRIGSTART_TIMERSTOP",
            exposure_time_s=0.1,
            trigger_period_s=0.2,
            trigger_count=5,
            max_wait_s=50.0,
        )
    )

    outcome = run_measurement(client, config, raw)

    assert outcome.result.stop_reason == "stopped_after_timeout"
    assert any("within 50 s" in warning for warning in outcome.result.warnings)


def test_run_measurement_reports_no_activity_when_never_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    raw.mkdir()
    # Always idle and no frames: the measurement never appears to start.
    client = _FakeClient(["DA_IDLE"] * 1000, frame_count=0, raw_dir=raw)
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )

    outcome = run_measurement(client, config, raw)

    assert outcome.result.stop_reason == "no_activity"
    # SERVAL answers a stop with "No measurement is running." when the camera
    # is idle, so HERMES asks anyway, in case the camera did start.
    assert client.stopped is True


def test_run_measurement_fails_when_every_frame_was_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    # Seen live: a 3-frame run whose files had no end-of-readout word came back
    # with 0 frames and 3 dropped.
    client = _FakeClient(
        ["DA_RECORDING", "DA_IDLE"],
        frame_count=0,
        dropped_frames=3,
        raw_dir=raw,
        tpx3_names=("a.tpx3", "b.tpx3", "c.tpx3"),
    )
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=3)
    )

    outcome = run_measurement(client, config, raw)

    # The camera finished on its own, but with no complete frames: an error,
    # with the raw files still recorded.
    assert outcome.result.stop_reason == "completed"
    assert outcome.result.frames == 0
    assert outcome.result.dropped_frames == 3
    assert outcome.result.errors == [
        "the measurement finished with no complete frames: SERVAL reports "
        "0 frames and 3 dropped"
    ]
    assert len(outcome.result.output_files) == 3


def test_run_measurement_warns_on_some_dropped_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(
        ["DA_RECORDING", "DA_IDLE"], frame_count=1, dropped_frames=1, raw_dir=raw
    )
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )

    outcome = run_measurement(client, config, raw)

    assert outcome.result.stop_reason == "completed"
    assert outcome.result.errors == []
    assert outcome.result.warnings == [
        "SERVAL reports 1 dropped frame (frames whose readout did not complete) "
        "and 1 complete frame"
    ]


_DISK_FULL_NOTICE = ServalDashboardNotification(
    type="severe",
    domain="server",
    message="Stopped writing to file channel because free disk space limit "
    "was reached (100.0 MB) in directory: /data/raw",
    reference_id="REF_ID_DISK_FULL",
)
_DISK_SPACE_FREED_NOTICE = ServalDashboardNotification(
    type="severe",
    domain="server",
    message="Noticed freed disk space of directory: /data/raw. Resuming "
    "writing to file channel.",
    reference_id="REF_ID_DISK_SPACE_FREED",
)


def test_run_measurement_fails_when_serval_runs_out_of_disk_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    # Space was freed again before the end, so DiskLimitReached is false, but
    # the raw files still miss the frames SERVAL did not write.
    client = _FakeClient(
        ["DA_RECORDING", "DA_IDLE"],
        notifications=(_DISK_FULL_NOTICE, _DISK_SPACE_FREED_NOTICE),
        disk_space=(
            ServalDashboardDiskSpace(path="/data/raw", disk_limit_reached=False),
        ),
        raw_dir=raw,
    )
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )

    records: list[dict[str, object]] = []
    sink_id = logger.add(
        lambda message: records.append(message.record),
        filter=lambda record: record["extra"].get("event_type")
        == "acquisition.serval.notification",
    )
    try:
        outcome = run_measurement(client, config, raw)
    finally:
        logger.remove(sink_id)

    assert outcome.result.stop_reason == "completed"
    assert outcome.result.errors == [
        "SERVAL ran out of disk space and stopped writing raw files: "
        + _DISK_FULL_NOTICE.message
    ]
    # The notice that space was freed is kept as a warning.
    assert outcome.result.warnings == [
        "SERVAL severe notice: " + _DISK_SPACE_FREED_NOTICE.message
    ]
    # Each notice was logged once while the measurement ran, though every
    # dashboard poll returned both.
    assert [record["extra"]["reference_id"] for record in records] == [
        "REF_ID_DISK_FULL",
        "REF_ID_DISK_SPACE_FREED",
    ]


def test_run_measurement_keeps_disk_full_notice_when_final_dashboard_read_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(
        ["DA_RECORDING", "DA_IDLE"],
        notifications=(_DISK_FULL_NOTICE,),
        raw_dir=raw,
    )
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )
    read_dashboard = client.get_dashboard
    dashboard_reads = 0

    def get_dashboard() -> ServalDashboard:
        nonlocal dashboard_reads
        dashboard_reads += 1
        if dashboard_reads == 3:
            raise ServalClientError("final dashboard unavailable")
        return read_dashboard()

    client.get_dashboard = get_dashboard

    outcome = run_measurement(client, config, raw)

    assert outcome.final_dashboard is None
    assert outcome.result.errors == [
        "SERVAL ran out of disk space and stopped writing raw files: "
        + _DISK_FULL_NOTICE.message
    ]
    assert outcome.result.warnings == [
        "could not read the final detector state: final dashboard unavailable"
    ]


def test_run_measurement_keeps_disk_limit_when_final_dashboard_read_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(
        ["DA_RECORDING", "DA_IDLE"],
        disk_space=(
            ServalDashboardDiskSpace(path="/data/raw", disk_limit_reached=True),
        ),
        raw_dir=raw,
    )
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )
    read_dashboard = client.get_dashboard
    dashboard_reads = 0

    def get_dashboard() -> ServalDashboard:
        nonlocal dashboard_reads
        dashboard_reads += 1
        if dashboard_reads == 3:
            raise ServalClientError("final dashboard unavailable")
        return read_dashboard()

    client.get_dashboard = get_dashboard

    outcome = run_measurement(client, config, raw)

    assert outcome.final_dashboard is None
    assert outcome.result.errors == [
        "SERVAL ran out of disk space and stopped writing raw files: "
        "DiskLimitReached is set for /data/raw"
    ]


def test_run_measurement_fails_when_the_disk_limit_is_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(
        ["DA_RECORDING", "DA_IDLE"],
        disk_space=(
            ServalDashboardDiskSpace(path="/data/raw", disk_limit_reached=True),
        ),
        raw_dir=raw,
    )
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )

    outcome = run_measurement(client, config, raw)

    assert outcome.result.errors == [
        "SERVAL ran out of disk space and stopped writing raw files: "
        "DiskLimitReached is set for /data/raw"
    ]


def test_run_measurement_keeps_info_notices_out_of_the_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(
        ["DA_RECORDING", "DA_IDLE"],
        notifications=(
            ServalDashboardNotification(
                type="info", domain="detector", message="Detector connected"
            ),
        ),
        disk_space=(
            ServalDashboardDiskSpace(path="/data/raw", disk_limit_reached=False),
        ),
        raw_dir=raw,
    )
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )

    outcome = run_measurement(client, config, raw)

    assert outcome.result.errors == []
    assert outcome.result.warnings == []


def test_run_measurement_calls_on_poll_each_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(
        ["DA_RECORDING", "DA_RECORDING", "DA_IDLE"], raw_dir=raw
    )
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )

    seen: list[str | None] = []

    def on_poll(measurement: ServalDashboardMeasurement | None) -> None:
        seen.append(measurement.status if measurement is not None else None)

    run_measurement(client, config, raw, on_poll)

    # One call per dashboard poll, including the final idle read that ends it.
    assert seen == ["DA_RECORDING", "DA_RECORDING", "DA_IDLE"]


def test_run_measurement_stops_the_camera_on_ctrl_c(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(
        ["DA_RECORDING"] * 1000, raw_dir=raw, tpx3_names=("a.tpx3",)
    )
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )
    polls: list[int] = []

    def press_ctrl_c(_measurement: ServalDashboardMeasurement | None) -> None:
        polls.append(1)
        if len(polls) == 3:
            raise KeyboardInterrupt

    outcome = run_measurement(client, config, raw, press_ctrl_c)

    # HERMES stopped the camera and still gathered what it recorded, and hands
    # Ctrl-C back for the caller to raise once the outcome is recorded.
    assert client.stopped is True
    assert isinstance(outcome.exception, KeyboardInterrupt)
    assert outcome.result.stop_reason == "interrupted"
    assert outcome.result.errors == []
    assert [file.path.name for file in outcome.result.output_files] == ["a.tpx3"]
    assert outcome.final_dashboard is not None


def test_run_measurement_stops_the_camera_on_an_unreadable_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(["DA_RECORDING"] * 1000, raw_dir=raw)
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )
    read_dashboard = client.get_dashboard
    polls: list[int] = []

    def get_dashboard() -> ServalDashboard:
        polls.append(1)
        if len(polls) == 2:
            # A reply HERMES cannot read raises ValidationError, not
            # ServalClientError.
            return ServalDashboard.model_validate(
                {"Server": {}, "Measurement": {"Status": "RUNNING"}}
            )
        return read_dashboard()

    client.get_dashboard = get_dashboard

    outcome = run_measurement(client, config, raw)

    assert client.stopped is True
    assert isinstance(outcome.exception, ValueError)
    assert outcome.result.stop_reason == "failed"
    assert outcome.result.errors[0].startswith("ValidationError: ")


def test_build_effective_detector_config_refuses_a_missing_file(
    tmp_path: Path,
) -> None:
    config = _config(
        detector_config_file=tmp_path / "missing.json",
        run_timing=ServalRunTiming(trigger_count=3),
    )

    with pytest.raises(ValueError, match="cannot read detector_config_file"):
        build_effective_detector_config(config)


def _fail_dashboard_reads(
    client: _FakeClient, failing, *, hang_s: float = 0.0
) -> None:
    """Make the dashboard reads whose 1-based number `failing` accepts fail.

    Each failed read first waits `hang_s` on the fake clock, like a read to a
    SERVAL that hangs until the client's timeout.
    """
    read_dashboard = client.get_dashboard
    reads = 0

    def get_dashboard() -> ServalDashboard:
        nonlocal reads
        reads += 1
        if failing(reads):
            # The fake clock's sleep moves the time forward.
            measurement_module.time.sleep(hang_s)
            raise ServalClientError("SERVAL GET /dashboard could not be sent")
        return read_dashboard()

    client.get_dashboard = get_dashboard


def _run_and_capture_logs(client, config, raw):
    records: list[dict] = []
    sink_id = logger.add(lambda message: records.append(message.record))
    try:
        outcome = run_measurement(client, config, raw)
    finally:
        logger.remove(sink_id)
    event_types = [record["extra"].get("event_type") for record in records]
    return outcome, records, event_types


def test_run_measurement_ends_as_lost_contact_when_serval_stops_answering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(["DA_RECORDING"] * 1000, raw_dir=raw)
    # Reads are 0.5 s apart; from the fifth (at 2 s) SERVAL never answers.
    _fail_dashboard_reads(client, lambda read: read >= 5)
    config = _config(
        run_timing=ServalRunTiming(
            exposure_time_s=0.1, trigger_count=5, max_wait_s=3600.0
        )
    )

    outcome, records, event_types = _run_and_capture_logs(client, config, raw)

    # HERMES gives up after 60 s with no answer, not at the hour-long wait
    # limit, and does not blame the camera for not finishing.
    assert outcome.result.stop_reason == "lost_contact"
    assert client.stopped is True
    assert outcome.result.warnings[0].startswith(
        "lost contact with SERVAL: it did not answer for 60 s"
    )
    assert not any(
        "did not finish" in warning for warning in outcome.result.warnings
    )
    assert event_types.count("acquisition.serval.not_answering") == 1
    not_answering = records[event_types.index("acquisition.serval.not_answering")]
    assert not_answering["level"].name == "WARNING"
    assert "keeps trying for up to 50 s more" in not_answering["message"]
    lost = records[event_types.index("acquisition.serval.lost_contact")]
    assert lost["level"].name == "ERROR"


def test_run_measurement_counts_the_time_a_hung_read_waits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(["DA_RECORDING"] * 1000, raw_dir=raw)
    # From the third read (sent at 1 s), each read hangs for the client's 10 s
    # timeout and then fails, so reads are sent at 1, 11.5, 22, ... s.
    _fail_dashboard_reads(client, lambda read: read >= 3, hang_s=10.0)
    config = _config(
        run_timing=ServalRunTiming(
            exposure_time_s=0.1, trigger_count=5, max_wait_s=3600.0
        )
    )

    outcome, records, event_types = _run_and_capture_logs(client, config, raw)

    # The time counts from when the first failed read was sent, so the wait
    # inside a hung read counts: HERMES warns once the first read fails, and
    # ends the run after six, at 62.5 s with no answer.
    not_answering = records[event_types.index("acquisition.serval.not_answering")]
    assert not_answering["extra"]["failed_reads"] == 1
    assert not_answering["extra"]["no_answer_s"] == 10.0
    lost = records[event_types.index("acquisition.serval.lost_contact")]
    assert lost["extra"]["failed_reads"] == 6
    assert lost["extra"]["no_answer_s"] == 62.5
    assert outcome.result.stop_reason == "lost_contact"


def test_run_measurement_does_not_call_an_unreachable_serval_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(["DA_RECORDING"] * 1000, raw_dir=raw)
    # SERVAL never answers a dashboard read, so HERMES cannot see the camera.
    _fail_dashboard_reads(client, lambda read: True)
    config = _config(
        run_timing=ServalRunTiming(
            exposure_time_s=0.1, trigger_count=5, max_wait_s=3600.0
        )
    )

    outcome, _records, _event_types = _run_and_capture_logs(client, config, raw)

    assert outcome.result.stop_reason == "lost_contact"
    assert client.stopped is True
    assert not any(
        "never left the idle state" in warning
        for warning in outcome.result.warnings
    )


def test_run_measurement_continues_when_serval_answers_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(["DA_RECORDING"] * 5 + ["DA_IDLE"], raw_dir=raw)
    # Reads 3 to 42 (sent from 1 s to 20.5 s) fail; read 43 at 21 s answers.
    _fail_dashboard_reads(client, lambda read: 3 <= read <= 42)
    config = _config(
        run_timing=ServalRunTiming(
            exposure_time_s=0.1, trigger_count=5, max_wait_s=3600.0
        )
    )

    outcome, _records, event_types = _run_and_capture_logs(client, config, raw)

    assert outcome.result.stop_reason == "completed"
    assert outcome.result.errors == []
    assert outcome.result.warnings == [
        "SERVAL did not answer for 20 s (40 dashboard reads in a row failed) "
        "during the measurement; it answered again and the measurement "
        "continued"
    ]
    assert "acquisition.serval.not_answering" in event_types


def test_run_measurement_does_not_warn_on_a_short_gap_in_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(["DA_RECORDING"] * 5 + ["DA_IDLE"], raw_dir=raw)
    # Reads 3 to 10 (4 s) fail, under the 10 s HERMES waits before warning.
    _fail_dashboard_reads(client, lambda read: 3 <= read <= 10)
    config = _config(
        run_timing=ServalRunTiming(exposure_time_s=0.1, trigger_count=5)
    )

    outcome, _records, event_types = _run_and_capture_logs(client, config, raw)

    assert outcome.result.stop_reason == "completed"
    assert outcome.result.warnings == []
    assert "acquisition.serval.not_answering" not in event_types


def test_run_measurement_ends_as_lost_contact_at_the_wait_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clock(monkeypatch)
    raw = tmp_path / "raw"
    client = _FakeClient(["DA_RECORDING"] * 1000, raw_dir=raw)
    # SERVAL stops answering at 5 s; the 30 s wait limit comes before the
    # 60 s HERMES would otherwise wait, so the run ends then.
    _fail_dashboard_reads(client, lambda read: read >= 11)
    config = _config(
        run_timing=ServalRunTiming(
            exposure_time_s=0.1, trigger_count=5, max_wait_s=30.0
        )
    )

    outcome, records, event_types = _run_and_capture_logs(client, config, raw)

    # The warning at 15 s gives the 15 s left until the wait limit, not the
    # 50 s left until HERMES would give up on its own.
    not_answering = records[event_types.index("acquisition.serval.not_answering")]
    assert "keeps trying for up to 15 s more" in not_answering["message"]
    assert outcome.result.stop_reason == "lost_contact"
    assert outcome.result.warnings[0].startswith(
        "lost contact with SERVAL: it did not answer for 25 s"
    )
    assert not any(
        "did not finish" in warning for warning in outcome.result.warnings
    )
