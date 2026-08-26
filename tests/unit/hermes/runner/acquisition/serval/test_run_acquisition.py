from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from hermes.runner.acquisition.serval import measurement as measurement_module
from hermes.runner.acquisition.serval import run as run_module
from hermes.runner.acquisition.serval.client import ServalClientError
from hermes.runner.acquisition.serval.run import (
    ServalAcquisitionError,
    run_serval_acquisition,
)
from hermes.runner.acquisition.serval.server import ServalServerError
from hermes.state.models.acquisition.serval import (
    CalibrationFiles,
    DestinationConfiguration,
    ServalAcquisitionConfig,
    ServalAcquisitionState,
    ServalDashboard,
    ServalDashboardDetector,
    ServalDashboardMeasurement,
    ServalDashboardServer,
    ServalRawDestination,
    ServalRunTiming,
    ServalServer,
)
from hermes.state.models.detector import (
    DetectorConfiguration,
    DetectorHealth,
    DetectorInfo,
    DetectorSnapshot,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_manager import StateManager


class _FakeAcquisitionClient:
    """A SERVAL client that answers reads from fixed in-memory values."""

    def __init__(
        self,
        *,
        server_up: bool,
        measurement_status: str = "DA_IDLE",
        measurement_statuses: list[str] | None = None,
        frame_count: int = 0,
        raw_dir: Path | None = None,
        tpx3_names: tuple[str, ...] = (),
    ) -> None:
        self.base_url = "http://serval.test"
        self._server_up = server_up
        self._measurement_status = measurement_status
        self._measurement_statuses = (
            list(measurement_statuses) if measurement_statuses is not None else None
        )
        self._frame_count = frame_count
        self._raw_dir = raw_dir
        self._tpx3_names = tpx3_names
        self._put_destination: DestinationConfiguration | None = None
        self.put_detector_config_arg: DetectorConfiguration | None = None
        self.loaded: list[tuple[str, str]] = []
        self.started = False
        self.stopped = False
        self.closed = False

    def get(self, path: str):
        if not self._server_up:
            raise ServalClientError("no server")
        return None

    def get_dashboard(self) -> ServalDashboard:
        if self._measurement_statuses:
            status = self._measurement_statuses.pop(0)
        else:
            status = self._measurement_status
        return ServalDashboard(
            server=ServalDashboardServer(software_version="3.3.0"),
            measurement=ServalDashboardMeasurement(
                status=status, frame_count=self._frame_count, dropped_frames=0
            ),
            detector=ServalDashboardDetector(detector_type="Tpx3"),
        )

    def get_detector_snapshot(self) -> DetectorSnapshot:
        return DetectorSnapshot(
            info=DetectorInfo(number_of_chips=1),
            health=DetectorHealth(bias_voltage_v=12.6),
        )

    def put_detector_config(self, config: DetectorConfiguration) -> None:
        self.put_detector_config_arg = config

    def get_detector_config(self) -> DetectorConfiguration | None:
        return self.put_detector_config_arg

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

    def put_destination(self, destination: DestinationConfiguration) -> None:
        self._put_destination = destination

    def get_destination(self) -> DestinationConfiguration:
        # Echo a destination that was set; otherwise a fixed pre-existing one.
        if self._put_destination is not None:
            return self._put_destination
        return DestinationConfiguration(
            raw=[ServalRawDestination(base="file:///data")]
        )

    def load_pixel_config(self, server_file_path: str) -> httpx.Response:
        self.loaded.append(("pixelconfig", server_file_path))
        return httpx.Response(200, text="Config loaded")

    def load_dacs(self, server_file_path: str) -> httpx.Response:
        self.loaded.append(("dacs", server_file_path))
        return httpx.Response(200, text="Config loaded")

    def close(self) -> None:
        self.closed = True


def _state_manager(
    tmp_path: Path,
    *,
    program_path: Path | None = None,
    raw_data_directory: Path | None = None,
    calibration_files: CalibrationFiles | None = None,
    run_timing: ServalRunTiming | None = None,
) -> StateManager:
    environment_kwargs: dict[str, object] = {
        "working_directory": tmp_path,
        "analysis_directory": tmp_path / "analysis",
    }
    if raw_data_directory is not None:
        environment_kwargs["raw_data_directory"] = raw_data_directory
    record = HermesRecord(
        measurement_info=MeasurementInfo(measurement_id="run-test", run="test-run"),
        environment=RuntimeEnvironment(**environment_kwargs),
        acquisition=ServalAcquisitionState(
            config=ServalAcquisitionConfig(
                serval=ServalServer(
                    url="http://localhost:8080",
                    program_path=program_path,
                ),
                calibration_files=calibration_files,
                run_timing=run_timing,
            ),
        ),
    )
    return StateManager(
        record,
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )


def _write_calibration_files(source_dir: Path) -> CalibrationFiles:
    source_dir.mkdir(parents=True, exist_ok=True)
    bpc = source_dir / "settings.bpc"
    dacs = source_dir / "settings.bpc.dacs"
    bpc.write_bytes(b"pixel-config-bytes")
    dacs.write_text("dac-values")
    return CalibrationFiles(pixel_config_file=bpc, dacs_file=dacs)


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: _FakeAcquisitionClient) -> None:
    monkeypatch.setattr(run_module, "ServalClient", lambda _url: client)
    monkeypatch.setattr(
        run_module, "wait_until_detector_connected", lambda _client, **_kw: None
    )


def test_records_dashboard_snapshot_and_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeAcquisitionClient(server_up=True)
    _patch_client(monkeypatch, client)
    started: list[str] = []
    monkeypatch.setattr(
        run_module, "start_serval", lambda *_a, **_k: started.append("start")
    )
    monkeypatch.setattr(
        run_module, "stop_serval", lambda *_a, **_k: started.append("stop")
    )

    state_manager = _state_manager(tmp_path)
    run_serval_acquisition(state_manager)

    acquisition = state_manager.get_state().acquisition
    assert acquisition.dashboard.server.software_version == "3.3.0"
    assert acquisition.initial_detector_snapshot.health.bias_voltage_v == 12.6
    assert acquisition.destination.raw[0].base == "file:///data"
    assert acquisition.status == "completed"
    # A server that was already answering is neither started nor stopped here.
    assert started == []
    assert client.closed is True


def test_launches_and_stops_serval_when_it_started_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jar = tmp_path / "serv.jar"
    jar.write_bytes(b"")
    client = _FakeAcquisitionClient(server_up=False)
    _patch_client(monkeypatch, client)

    process = object()
    calls: list[str] = []
    monkeypatch.setattr(
        run_module, "start_serval", lambda *_a, **_k: (calls.append("start"), process)[1]
    )
    monkeypatch.setattr(run_module, "wait_until_ready", lambda *_a, **_k: "3.3.0")

    def fake_stop(client_arg, process_arg, **_kw):
        calls.append("stop")
        assert process_arg is process

    monkeypatch.setattr(run_module, "stop_serval", fake_stop)

    state_manager = _state_manager(tmp_path, program_path=jar)
    run_serval_acquisition(state_manager)

    assert calls == ["start", "stop"]
    assert state_manager.get_state().acquisition.status == "completed"
    assert client.closed is True


def test_completes_when_destination_is_not_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeAcquisitionClient(server_up=True)

    def raise_not_set() -> DestinationConfiguration:
        raise ServalClientError(
            "SERVAL GET /server/destination returned 409: Destination is not set."
        )

    client.get_destination = raise_not_set  # type: ignore[method-assign]
    _patch_client(monkeypatch, client)
    monkeypatch.setattr(run_module, "start_serval", lambda *_a, **_k: None)
    monkeypatch.setattr(run_module, "stop_serval", lambda *_a, **_k: None)

    state_manager = _state_manager(tmp_path)
    run_serval_acquisition(state_manager)

    acquisition = state_manager.get_state().acquisition
    assert acquisition.destination is None
    assert acquisition.initial_detector_snapshot is not None
    assert acquisition.status == "completed"


def test_raises_when_server_down_and_no_program_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeAcquisitionClient(server_up=False)
    _patch_client(monkeypatch, client)

    state_manager = _state_manager(tmp_path)
    with pytest.raises(ServalServerError, match="no SERVAL server answers"):
        run_serval_acquisition(state_manager)

    assert client.closed is True


def test_configures_destination_and_calibration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeAcquisitionClient(server_up=True)
    _patch_client(monkeypatch, client)
    monkeypatch.setattr(run_module, "start_serval", lambda *_a, **_k: None)
    monkeypatch.setattr(run_module, "stop_serval", lambda *_a, **_k: None)

    raw_dir = tmp_path / "raw"
    calibration_files = _write_calibration_files(tmp_path / "sophy")
    state_manager = _state_manager(
        tmp_path,
        raw_data_directory=raw_dir,
        calibration_files=calibration_files,
    )
    run_serval_acquisition(state_manager)

    acquisition = state_manager.get_state().acquisition
    # The destination we PUT points at the raw data directory.
    assert acquisition.destination.raw[0].base == raw_dir.as_uri()
    # Calibration files were saved under the run's config directory and loaded.
    assert (tmp_path / "config" / "settings.bpc").is_file()
    assert acquisition.calibration.pixel_config_file.path == Path("config/settings.bpc")
    assert acquisition.calibration.dacs_load.http_status_code == 200
    assert client.loaded == [
        ("pixelconfig", str(tmp_path / "config" / "settings.bpc")),
        ("dacs", str(tmp_path / "config" / "settings.bpc.dacs")),
    ]
    # Configured, not completed: no measurement was taken.
    assert acquisition.status == "configured"


def test_preflight_refuses_to_configure_during_a_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeAcquisitionClient(server_up=True, measurement_status="DA_RECORDING")
    _patch_client(monkeypatch, client)
    monkeypatch.setattr(run_module, "start_serval", lambda *_a, **_k: None)
    monkeypatch.setattr(run_module, "stop_serval", lambda *_a, **_k: None)

    state_manager = _state_manager(tmp_path, raw_data_directory=tmp_path / "raw")
    with pytest.raises(ServalAcquisitionError, match="measurement is in progress"):
        run_serval_acquisition(state_manager)

    # It refused before writing a destination.
    assert client._put_destination is None
    assert client.closed is True


def test_takes_a_measurement_when_run_timing_is_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_dir = tmp_path / "raw"
    # DA_IDLE at connect, then recording, then idle again so the measurement
    # completes on its own.
    client = _FakeAcquisitionClient(
        server_up=True,
        measurement_statuses=["DA_IDLE", "DA_RECORDING", "DA_IDLE"],
        frame_count=5,
        raw_dir=raw_dir,
        tpx3_names=("run_0.tpx3",),
    )
    _patch_client(monkeypatch, client)
    monkeypatch.setattr(run_module, "start_serval", lambda *_a, **_k: None)
    monkeypatch.setattr(run_module, "stop_serval", lambda *_a, **_k: None)
    # Don't wait between dashboard polls.
    monkeypatch.setattr(measurement_module.time, "sleep", lambda _s: None)

    state_manager = _state_manager(
        tmp_path,
        raw_data_directory=raw_dir,
        run_timing=ServalRunTiming(
            trigger_mode="AUTOTRIGSTART_TIMERSTOP",
            exposure_time_s=0.1,
            trigger_period_s=0.2,
            trigger_count=5,
        ),
    )
    run_serval_acquisition(state_manager)

    acquisition = state_manager.get_state().acquisition
    assert acquisition.status == "completed"
    assert acquisition.result is not None
    assert acquisition.result.stop_reason == "completed"
    assert acquisition.result.frames == 5
    assert acquisition.result.errors == []
    assert len(acquisition.result.output_files) == 1
    assert acquisition.result.output_files[0].path.name == "run_0.tpx3"
    # The final snapshot was recorded and the trigger count reached SERVAL.
    assert acquisition.final_detector_snapshot is not None
    assert client.started is True
    assert client.put_detector_config_arg is not None
    assert client.put_detector_config_arg.n_triggers == 5


def test_raises_when_acquisition_is_not_serval(tmp_path: Path) -> None:
    record = HermesRecord(
        measurement_info=MeasurementInfo(measurement_id="run-test", run="test-run"),
        environment=RuntimeEnvironment(
            working_directory=tmp_path,
            analysis_directory=tmp_path / "analysis",
        ),
    )
    state_manager = StateManager(
        record,
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )
    with pytest.raises(ServalAcquisitionError, match="no valid SERVAL acquisition"):
        run_serval_acquisition(state_manager)
