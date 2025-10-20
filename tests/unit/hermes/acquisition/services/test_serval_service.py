from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from hermes.acquisition.models.environment import ServalDeployment
from hermes.acquisition.models.tpx_serval.dashboard import Dashboard
from hermes.acquisition.models.tpx_serval.destinations import Destination
from hermes.acquisition.models.tpx_serval.measurement import MeasurementConfig
from hermes.acquisition.services.base import ServiceError, ServiceHealthStatus
from hermes.acquisition.services.serval import ServalHTTPService


class FakeResponse:
    def __init__(self, *, status_code: int = 200, json_payload: Optional[Dict[str, Any]] = None) -> None:
        self.status_code = status_code
        self._json_payload = json_payload
        if json_payload is None:
            self._text = ""
            self.content = b""
        else:
            self._text = json.dumps(json_payload)
            self.content = self._text.encode("utf-8")
        self.url = "http://localhost/mock"

    @property
    def text(self) -> str:
        return self._text

    def json(self) -> Dict[str, Any]:
        if self._json_payload is None:
            raise ValueError("No JSON payload")
        return self._json_payload


class FakeSession:
    def __init__(self, responses: List[FakeResponse]) -> None:
        self._responses = responses
        self.calls: List[Dict[str, Any]] = []

    def request(self, *, method: str, url: str, params=None, json=None, timeout=None):  # type: ignore[override]
        if not self._responses:
            raise AssertionError("No fake responses left")
        response = self._responses.pop(0)
        self.calls.append({
            "method": method.upper(),
            "url": url,
            "params": params,
            "json": json,
            "timeout": timeout,
        })
        return response


@pytest.fixture
def deployment(tmp_path) -> ServalDeployment:
    return ServalDeployment(host="localhost", port=8080, install_dir=tmp_path)


def test_serval_deployment_defaults_install_dir() -> None:
    deployment = ServalDeployment()
    assert deployment.install_dir.path == Path("/opt/serval")
    assert deployment.config_dir is not None
    assert deployment.config_dir.path == Path("/opt/serval/initFiles")


def make_dashboard_payload() -> Dict[str, Any]:
    return {
        "Server": {
            "SoftwareVersion": "3.3.0",
        },
        "Measurement": {
            "Status": "DA_RUNNING",
            "FrameCount": 42,
        },
        "Detector": {
            "DetectorType": "TPX3",
        },
    }


def test_get_dashboard_returns_model(deployment: ServalDeployment) -> None:
    session = FakeSession([FakeResponse(json_payload=make_dashboard_payload())])
    service = ServalHTTPService(deployment, session=session)

    dashboard = service.get_dashboard()

    assert isinstance(dashboard, Dashboard)
    assert dashboard.server.software_version == "3.3.0"
    assert dashboard.measurement.frame_count == 42
    assert session.calls[0]["method"] == "GET"
    assert session.calls[0]["url"].endswith("/dashboard")


def test_health_check_failure_marks_unhealthy(deployment: ServalDeployment) -> None:
    session = FakeSession([])
    service = ServalHTTPService(deployment, session=session)
    service.get_dashboard = MagicMock(side_effect=ServiceError("boom"))  # type: ignore[assignment]

    status = service.health_check()

    assert isinstance(status, ServiceHealthStatus)
    assert not status.is_connected
    assert not status.is_healthy
    assert status.detail == "boom"


def test_set_destination_sends_payload(deployment: ServalDeployment) -> None:
    session = FakeSession([FakeResponse()])
    service = ServalHTTPService(deployment, session=session)

    destination = Destination()

    service.set_destination(destination)

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["method"] == "PUT"
    assert call["url"].endswith("/server/destination")
    assert call["json"] == destination.model_dump(by_alias=True, exclude_none=True)


def test_measurement_config_round_trip(deployment: ServalDeployment) -> None:
    config_payload = {
        "Mode": "count",
        "StartDelay": 0.0,
        "StopDelay": 0.0,
    }
    session = FakeSession([
        FakeResponse(json_payload=config_payload),  # GET /measurement/config
        FakeResponse(json_payload=config_payload),  # PUT /measurement/config
    ])
    service = ServalHTTPService(deployment, session=session)

    config = service.get_measurement_config()
    assert isinstance(config, MeasurementConfig)
    assert config.mode.value == "count"

    service.set_measurement_config(config)
    assert session.calls[-1]["method"] == "PUT"
    assert session.calls[-1]["url"].endswith("/measurement/config")
