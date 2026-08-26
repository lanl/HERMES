from __future__ import annotations

import httpx
import pytest

from hermes.runner.acquisition.serval.client import ServalClient, ServalClientError
from hermes.state.models.acquisition.serval import (
    DestinationConfiguration,
    ServalRawDestination,
)
from hermes.state.models.detector import DetectorConfiguration


def _client_with_handler(handler) -> ServalClient:
    client = ServalClient("http://serval.test")
    client._client = httpx.Client(
        base_url="http://serval.test",
        transport=httpx.MockTransport(handler),
    )
    return client


def test_get_dashboard_parses_server_answer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/dashboard"
        return httpx.Response(
            200,
            json={
                "Server": {"SoftwareVersion": "3.3.0"},
                "Measurement": {"Status": "DA_IDLE"},
                "Detector": {"DetectorType": "Tpx3"},
            },
        )

    with _client_with_handler(handler) as client:
        dashboard = client.get_dashboard()

    assert dashboard.server.software_version == "3.3.0"
    assert dashboard.measurement is not None
    assert dashboard.measurement.status == "DA_IDLE"


# Real /detector/* answers from a connected SERVAL 3.3.0 server, trimmed to
# the fields the models read. Kept together so the snapshot test can serve all
# four endpoints from one place.
_DETECTOR_INFO = {
    "IfaceName": "Spidr",
    "NumberOfChips": 1,
    "Boards": [
        {
            "ChipboardId": "2000164",
            "IpAddress": "192.168.100.10",
            "Chips": [{"Index": 0, "Id": 16018, "Name": "W0062_B09"}],
        }
    ],
}
_DETECTOR_HEALTH = {
    "LocalTemperature": 33.0,
    "FPGATemperature": 41.5,
    "ChipTemperatures": [56, 0, 0, 0],
    "BiasVoltage": 12.6,
    "Humidity": 21,
}
_DETECTOR_LAYOUT = {
    "DetectorOrientation": "UP",
    "Original": {
        "Width": 256,
        "Height": 256,
        "Chips": [{"Chip": 0, "X": 0, "Y": 0, "Orientation": "LtRBtT"}],
    },
}
_DETECTOR_CONFIG = {"BiasVoltage": 13, "BiasEnabled": True, "TriggerMode": "CONTINUOUS"}


def test_get_detector_info_parses_boards_and_chips() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/detector/info"
        return httpx.Response(200, json=_DETECTOR_INFO)

    with _client_with_handler(handler) as client:
        info = client.get_detector_info()

    assert info.iface_name == "Spidr"
    assert info.boards[0].chipboard_id == "2000164"
    assert info.boards[0].chips[0].name == "W0062_B09"


def test_get_detector_snapshot_reads_all_four_endpoints() -> None:
    bodies = {
        "/detector/info": _DETECTOR_INFO,
        "/detector/health": _DETECTOR_HEALTH,
        "/detector/layout": _DETECTOR_LAYOUT,
        "/detector/config": _DETECTOR_CONFIG,
    }
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json=bodies[request.url.path])

    with _client_with_handler(handler) as client:
        snapshot = client.get_detector_snapshot()

    assert sorted(seen) == sorted(bodies)
    assert snapshot.info is not None
    assert snapshot.health is not None
    assert snapshot.health.bias_voltage_v == 12.6
    assert snapshot.layout is not None
    assert snapshot.layout.original is not None
    assert snapshot.layout.original.width == 256
    assert snapshot.configuration is not None
    assert snapshot.configuration.trigger_mode == "CONTINUOUS"


def test_get_destination_parses_server_answer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/server/destination"
        return httpx.Response(
            200,
            json={
                "Raw": [{"Base": "file:///data", "FilePattern": "run_%d"}],
                "Image": [],
            },
        )

    with _client_with_handler(handler) as client:
        destination = client.get_destination()

    assert destination.raw[0].base == "file:///data"
    assert destination.raw[0].file_pattern == "run_%d"
    assert destination.image == []


def test_put_destination_sends_serval_json() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["content"] = request.content
        return httpx.Response(200, text="OK")

    destination = DestinationConfiguration(
        raw=[
            ServalRawDestination(
                base="file:///data/raw",
                file_pattern="run_",
                split_strategy="FRAME",
            )
        ]
    )
    with _client_with_handler(handler) as client:
        client.put_destination(destination)

    assert seen["method"] == "PUT"
    assert seen["path"] == "/server/destination"
    body = seen["content"]
    assert b'"Raw"' in body  # type: ignore[operator]
    assert b'"Base"' in body  # type: ignore[operator]
    assert b'"SplitStrategy"' in body  # type: ignore[operator]


def test_load_pixel_config_and_dacs_hit_config_load() -> None:
    seen: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.url.path,
                request.url.params["format"],
                request.url.params["file"],
            )
        )
        return httpx.Response(200, text="Config loaded")

    with _client_with_handler(handler) as client:
        pixel = client.load_pixel_config("/abs/settings.bpc")
        dacs = client.load_dacs("/abs/settings.bpc.dacs")

    assert pixel.status_code == 200
    assert dacs.text == "Config loaded"
    assert seen == [
        ("/config/load", "pixelconfig", "/abs/settings.bpc"),
        ("/config/load", "dacs", "/abs/settings.bpc.dacs"),
    ]


def test_put_detector_config_sends_serval_json() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["content"] = request.content
        return httpx.Response(200, text="OK")

    config = DetectorConfiguration(
        bias_voltage_v=12.0,
        trigger_mode="AUTOTRIGSTART_TIMERSTOP",
        n_triggers=5,
    )
    with _client_with_handler(handler) as client:
        client.put_detector_config(config)

    assert seen["method"] == "PUT"
    assert seen["path"] == "/detector/config"
    body = seen["content"]
    assert b'"BiasVoltage"' in body  # type: ignore[operator]
    assert b'"TriggerMode"' in body  # type: ignore[operator]
    assert b'"nTriggers"' in body  # type: ignore[operator]


def test_measurement_start_and_stop_hit_their_endpoints() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, text="OK")

    with _client_with_handler(handler) as client:
        client.measurement_start()
        client.measurement_stop()

    assert seen == ["/measurement/start", "/measurement/stop"]


def test_get_detector_snapshot_raises_when_not_connected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, text="Not connected. Please connect to a detector.")

    with _client_with_handler(handler) as client:  # noqa: SIM117
        with pytest.raises(ServalClientError, match="409"):
            client.get_detector_snapshot()


def test_get_json_returns_decoded_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    with _client_with_handler(handler) as client:
        assert client.get_json("/anything") == {"ok": True}


def test_put_json_sends_body_and_returns_answer() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["content"] = request.content
        return httpx.Response(200, json={"applied": True})

    with _client_with_handler(handler) as client:
        assert client.put_json("/detector/config", {"nTriggers": 10}) == {
            "applied": True
        }

    assert seen["method"] == "PUT"
    assert b"nTriggers" in seen["content"]  # type: ignore[operator]


def test_non_200_raises_with_status_and_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with _client_with_handler(handler) as client:  # noqa: SIM117
        with pytest.raises(ServalClientError, match="500"):
            client.get_json("/dashboard")


def test_transport_failure_raises_serval_client_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no server", request=request)

    with _client_with_handler(handler) as client:  # noqa: SIM117
        with pytest.raises(ServalClientError, match="could not be sent"):
            client.get("/dashboard")
