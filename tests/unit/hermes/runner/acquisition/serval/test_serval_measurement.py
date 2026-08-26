from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from hermes.runner.acquisition.serval import measurement as measurement_module
from hermes.runner.acquisition.serval.measurement import (
    build_effective_detector_config,
    run_measurement,
)
from hermes.state.models.acquisition.serval import (
    ServalAcquisitionConfig,
    ServalDashboard,
    ServalDashboardDetector,
    ServalDashboardMeasurement,
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
        raw_dir: Path | None = None,
        tpx3_names: tuple[str, ...] = (),
    ) -> None:
        self._statuses = list(statuses)
        self._frame_count = frame_count
        self._raw_dir = raw_dir
        self._tpx3_names = tpx3_names
        self.put_config: DetectorConfiguration | None = None
        self.started = False
        self.stopped = False

    def put_detector_config(self, config: DetectorConfiguration) -> None:
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
            server=ServalDashboardServer(software_version="3.3.0"),
            measurement=ServalDashboardMeasurement(
                status=status, frame_count=self._frame_count, dropped_frames=0
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
    # Both raw files were gathered with sizes and the final health was read.
    assert len(outcome.result.output_files) == 2
    assert outcome.result.output_files[0].size_bytes == 4
    assert outcome.result.output_files[0].path.name == "a.tpx3"
    assert outcome.final_snapshot.health.bias_voltage_v == 12.6


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
