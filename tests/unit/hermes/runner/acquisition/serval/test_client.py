from __future__ import annotations

import httpx
import pytest

from hermes.runner.acquisition.serval.client import ServalClient, ServalClientError


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
