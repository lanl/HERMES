from __future__ import annotations

import httpx
import pytest

import hermes.mcp.server as server
from hermes.mcp.server import CameraCheckRequest, check_camera
from hermes.runner.acquisition.serval.client import ServalClient

_URL = "http://serval.test"

# Real answers from a SERVAL 3.3.0 server with one camera connected, trimmed
# to the fields check_camera reports.
_DASHBOARD = {
    "Server": {
        "SoftwareVersion": "3.3.0",
        "DiskSpace": [
            {"Path": "/data/raw", "FreeSpace": 670758268928, "DiskLimitReached": False}
        ],
        "Notifications": [],
    },
    "Measurement": {"Status": "DA_IDLE"},
    "Detector": {"DetectorType": "Tpx3"},
}
_DETECTOR = {
    "/detector/info": {
        "NumberOfChips": 1,
        "Boards": [{"Chips": [{"Index": 0, "Id": 16018, "Name": "W0062_B09"}]}],
    },
    "/detector/health": {
        "LocalTemperature": 33.0,
        "FPGATemperature": 41.5,
        "ChipTemperatures": [56, 0, 0, 0],
        "BiasVoltage": 12.6,
        "Humidity": 21,
    },
    "/detector/layout": {
        "DetectorOrientation": "UP",
        "Original": {
            "Width": 256,
            "Height": 256,
            "Chips": [{"Chip": 0, "X": 0, "Y": 0, "Orientation": "LtRBtT"}],
        },
    },
    "/detector/config": {"BiasVoltage": 13, "TriggerMode": "CONTINUOUS"},
}


@pytest.fixture
def requests_seen(monkeypatch: pytest.MonkeyPatch):
    """Answer check_camera's requests with `handler`; returns what was asked."""
    seen: list[tuple[str, str]] = []

    def serve(handler) -> list[tuple[str, str]]:
        def record(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, request.url.path))
            return handler(request)

        def make_client(url: str) -> ServalClient:
            client = ServalClient(url)
            client._client = httpx.Client(
                base_url=url, transport=httpx.MockTransport(record)
            )
            return client

        monkeypatch.setattr(server, "ServalClient", make_client)
        return seen

    return serve


def test_nothing_answers(requests_seen) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    requests_seen(handler)
    result = check_camera(CameraCheckRequest(serval_url=_URL))

    assert result.status == "no SERVAL"
    assert result.serval_version is None
    assert result.detector is None
    assert result.problem is None
    assert result.message.startswith(f"No SERVAL reachable at {_URL}.")


def test_serval_with_no_camera(requests_seen) -> None:
    dashboard = {**_DASHBOARD, "Detector": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/dashboard":
            return httpx.Response(200, json=dashboard)
        return httpx.Response(409, text="Not connected. Please connect to a detector.")

    seen = requests_seen(handler)
    result = check_camera(CameraCheckRequest(serval_url=_URL))

    assert result.status == "no camera"
    assert result.serval_version == "3.3.0"
    assert result.measurement_status == "DA_IDLE"
    assert result.detector is None
    assert result.problem is None
    assert "no camera is connected" in result.message
    assert all(method == "GET" for method, _ in seen)


def test_serval_with_a_camera(requests_seen) -> None:
    dashboard = {
        **_DASHBOARD,
        "Server": {
            **_DASHBOARD["Server"],
            "Notifications": [
                {"Type": "severe", "Message": "Stopped writing to file channel."}
            ],
        },
        "Measurement": {"Status": "DA_RECORDING"},
    }
    bodies = {"/dashboard": dashboard, **_DETECTOR}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=bodies[request.url.path])

    seen = requests_seen(handler)
    result = check_camera(CameraCheckRequest(serval_url=_URL))

    assert result.status == "camera connected"
    assert result.serval_version == "3.3.0"
    detector = result.detector
    assert detector is not None
    assert detector.detector_type == "Tpx3"
    assert detector.chips == ["W0062_B09"]
    assert (detector.width_pixels, detector.height_pixels) == (256, 256)
    assert detector.orientation == "UP"
    assert detector.board_temperature_c == 33.0
    assert detector.fpga_temperature_c == 41.5
    assert detector.chip_temperatures_c == [56, 0, 0, 0]
    assert detector.bias_voltage_v == 12.6
    assert detector.humidity_percent == 21
    assert len(result.disk_space) == 1
    assert result.disk_space[0].path == "/data/raw"
    # The manual's dashboard example reports these bytes as "670.8 GB".
    assert result.disk_space[0].free_gb == 670.76
    assert result.notices == ["severe: Stopped writing to file channel."]
    assert result.measurement_status == "DA_RECORDING"
    assert "with a camera connected (1 chip(s), bias 12.6 V)" in result.message
    assert "A measurement is already running" in result.message
    # Only reads: nothing is sent to SERVAL or the camera.
    assert all(method == "GET" for method, _ in seen)
    assert {path for _, path in seen} == set(bodies)


@pytest.mark.parametrize(
    ("answer", "problem"),
    [
        (httpx.Response(500, text="boom"), "returned 500: boom"),
        (httpx.Response(200, text="<html>not SERVAL</html>"), "could not read"),
    ],
)
def test_serval_answers_with_an_error(
    requests_seen, answer: httpx.Response, problem: str
) -> None:
    requests_seen(lambda request: answer)

    result = check_camera(CameraCheckRequest(serval_url=_URL))

    assert result.status == "SERVAL error"
    assert result.serval_version is None
    assert result.detector is None
    assert problem in (result.problem or "")
    assert result.message.startswith(f"Something answers at {_URL}")


def test_serval_answers_but_a_camera_read_fails(requests_seen) -> None:
    bodies = {"/dashboard": _DASHBOARD, **_DETECTOR}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/detector/health":
            return httpx.Response(500, text="health read failed")
        return httpx.Response(200, json=bodies[request.url.path])

    requests_seen(handler)
    result = check_camera(CameraCheckRequest(serval_url=_URL))

    assert result.status == "SERVAL error"
    assert result.serval_version == "3.3.0"
    assert result.detector is None
    assert "returned 500: health read failed" in (result.problem or "")
    assert result.message.startswith(
        f"SERVAL 3.3.0 is running at {_URL}, but reading the camera failed"
    )
