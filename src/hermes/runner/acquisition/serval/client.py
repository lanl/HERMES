from __future__ import annotations

import time
from typing import Any

import httpx
from loguru import logger

from hermes.state.models.acquisition.serval import ServalDashboard
from hermes.state.models.detector import (
    DetectorConfiguration,
    DetectorHealth,
    DetectorInfo,
    DetectorLayout,
    DetectorSnapshot,
)

_CLIENT_LOGGER = logger.bind(domain="acquisition", backend="serval", step="serval_client")

# SERVAL answers every successful call with 200; anything else is an error.
_SUCCESS_STATUS = 200


class ServalClientError(Exception):
    """Raised when a SERVAL HTTP call fails to send or answers with non-200."""


class ServalClient:
    """Thin HTTP client for the SERVAL server.

    HERMES talks only to SERVAL over HTTP; SERVAL talks to the camera. Every
    call raises `ServalClientError` on a transport failure or any non-200
    answer, and logs the method, path, status, and elapsed time in the
    acquisition/serval domain so the run's `acquisition.serval.jsonl` records
    every request.
    """

    def __init__(self, base_url: str, *, timeout_s: float = 10.0) -> None:
        self.base_url = base_url
        self._client = httpx.Client(base_url=base_url, timeout=timeout_s)

    def __enter__(self) -> ServalClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _send(self, method: str, path: str, *, json: Any | None = None) -> httpx.Response:
        start = time.monotonic()
        try:
            response = self._client.request(method, path, json=json)
        except httpx.HTTPError as error:
            elapsed_ms = round((time.monotonic() - start) * 1000, 1)
            # Logged at debug, not error: a caller that expects the server to be
            # up (readiness polling) treats a refused connection as normal and
            # decides on its own how loudly to report a genuine failure.
            _CLIENT_LOGGER.debug(
                "SERVAL {method} {path} could not be sent: {error}",
                event_type="acquisition.serval.http_send_failed",
                method=method,
                path=path,
                elapsed_ms=elapsed_ms,
                error=str(error),
            )
            raise ServalClientError(
                f"SERVAL {method} {path} could not be sent: {error}"
            ) from error

        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        _CLIENT_LOGGER.debug(
            "SERVAL {method} {path} -> {status_code} in {elapsed_ms} ms",
            event_type="acquisition.serval.http_request",
            method=method,
            path=path,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
        )
        if response.status_code != _SUCCESS_STATUS:
            raise ServalClientError(
                f"SERVAL {method} {path} returned "
                f"{response.status_code}: {response.text}"
            )
        return response

    def get(self, path: str) -> httpx.Response:
        return self._send("GET", path)

    def put(self, path: str, body: Any) -> httpx.Response:
        return self._send("PUT", path, json=body)

    def get_json(self, path: str) -> Any:
        return self.get(path).json()

    def put_json(self, path: str, body: Any) -> Any:
        return self.put(path, body).json()

    def get_dashboard(self) -> ServalDashboard:
        return ServalDashboard.model_validate(self.get_json("/dashboard"))

    def get_detector_info(self) -> DetectorInfo:
        return DetectorInfo.model_validate(self.get_json("/detector/info"))

    def get_detector_health(self) -> DetectorHealth:
        return DetectorHealth.model_validate(self.get_json("/detector/health"))

    def get_detector_layout(self) -> DetectorLayout:
        return DetectorLayout.model_validate(self.get_json("/detector/layout"))

    def get_detector_config(self) -> DetectorConfiguration:
        return DetectorConfiguration.model_validate(self.get_json("/detector/config"))

    def get_detector_snapshot(self) -> DetectorSnapshot:
        """Read all four `/detector/*` endpoints into one snapshot.

        Only valid once SERVAL reports a connected detector; before then each
        read returns 409 and raises `ServalClientError`.
        """
        return DetectorSnapshot(
            info=self.get_detector_info(),
            health=self.get_detector_health(),
            layout=self.get_detector_layout(),
            configuration=self.get_detector_config(),
        )
