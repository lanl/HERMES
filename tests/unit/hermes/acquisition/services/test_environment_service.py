from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from hermes.acquisition.models.environment import (
    AcquisitionEnvironment,
    NetworkEndpoint,
    ServalDeployment,
    WorkspaceLayout,
)
from hermes.acquisition.services.base import ServiceHealthStatus
from hermes.acquisition.services.environment import EnvironmentService


class DummyServalService:
    def __init__(self, status: ServiceHealthStatus) -> None:
        self._status = status

    def health_check(self) -> ServiceHealthStatus:
        return self._status


class ProbeRecordingEnvironmentService(EnvironmentService):
    def __init__(self, probe_results: List[tuple[bool, float | None, str | None]]) -> None:
        super().__init__()
        self._probe_results = probe_results
        self.calls: list[tuple[str, int | None]] = []

    def _probe_endpoint(self, host: str, port: int | None, timeout: float):  # type: ignore[override]
        self.calls.append((host, port))
        if not self._probe_results:
            raise AssertionError("No more probe results configured")
        return self._probe_results.pop(0)


@pytest.fixture
def environment(tmp_path: Path) -> AcquisitionEnvironment:
    workspace = WorkspaceLayout(name="workspace", base_dir=tmp_path)
    camera = NetworkEndpoint(name="camera", host="localhost", port=12345)
    deployment = ServalDeployment(host="localhost", port=8080, install_dir=tmp_path)
    return AcquisitionEnvironment(
        name="env",
        workspace=workspace,
        camera_endpoint=camera,
        network_checks=[
            NetworkEndpoint(name="storage", host="nas.local", port=None),
        ],
        serval=deployment,
    )


def test_ensure_run_layout_creates_directories(environment: AcquisitionEnvironment) -> None:
    service = EnvironmentService()
    layout = service.ensure_run_layout(environment, run_number=1)

    for directory in layout.required_directories:
        assert directory.exists()


def test_probe_network_updates_latency(environment: AcquisitionEnvironment) -> None:
    service = ProbeRecordingEnvironmentService(
        probe_results=[
            (True, 1.0, None),
            (False, None, "not reachable"),
        ]
    )

    endpoints = service.probe_network(environment)

    assert len(endpoints) == 2
    assert endpoints[0].reachable is True
    assert endpoints[0].latency_ms == pytest.approx(1.0)
    assert endpoints[1].reachable is False
    assert endpoints[1].latency_ms is None
    assert service.calls == [("localhost", 12345), ("nas.local", None)]


def test_collect_status_compiles_report(environment: AcquisitionEnvironment) -> None:
    service = ProbeRecordingEnvironmentService([(True, 1.0, None), (True, 2.0, None)])
    status = ServiceHealthStatus(is_connected=True, is_healthy=True)
    serval = DummyServalService(status)

    report = service.collect_status(environment, run_number=2, serval_service=serval)

    assert report.environment_name == "env"
    assert report.run_layout is not None
    assert report.run_layout.run_id == "run_002"
    assert report.serval_health == status
    assert all(endpoint.reachable for endpoint in report.endpoints)
    assert isinstance(report.serval_installations, list)


def test_collect_status_reports_serval_versions(environment: AcquisitionEnvironment) -> None:
    install_path = environment.serval.install_dir.path
    default_dir = install_path / environment.serval.default_version
    default_dir.mkdir()
    (default_dir / f"serv-{environment.serval.default_version}.jar").write_text("", encoding="utf-8")

    version_dir = install_path / "3.3.0"
    version_dir.mkdir()
    (version_dir / "serval-3.3.0.jar").write_text("", encoding="utf-8")

    service = EnvironmentService()
    report = service.collect_status(environment)

    matching = [status for status in report.serval_installations if status.path.path == install_path.resolve()]
    assert matching, "Expected installation status for configured install_dir"
    status = matching[0]
    assert status.exists
    assert status.available_versions == [environment.serval.default_version, "3.3.0"]
    assert status.default_version == environment.serval.default_version
    default_names = environment.serval.default_executable_names
    assert default_names[0] == f"serv-{environment.serval.default_version}.jar"
    default_paths = environment.serval.default_executable_paths
    assert default_paths[0].name == default_names[0]
