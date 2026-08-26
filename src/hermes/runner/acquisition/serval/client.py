from __future__ import annotations

import time
from typing import Any

import httpx
from loguru import logger

from hermes.state.models.acquisition.serval import (
    DestinationConfiguration,
    ServalDashboard,
)
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

    def _send(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        start = time.monotonic()
        try:
            response = self._client.request(method, path, json=json, params=params)
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

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
        return self._send("GET", path, params=params)

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

    def put_detector_config(self, config: DetectorConfiguration) -> None:
        """Send the detector configuration to SERVAL as SERVAL JSON."""
        self.put(
            "/detector/config",
            config.model_dump(by_alias=True, exclude_none=True),
        )

    def measurement_start(self) -> httpx.Response:
        """Start a measurement (`GET /measurement/start`)."""
        return self.get("/measurement/start")

    def measurement_stop(self) -> httpx.Response:
        """Stop the running measurement (`GET /measurement/stop`)."""
        return self.get("/measurement/stop")

    def get_destination(self) -> DestinationConfiguration:
        return DestinationConfiguration.model_validate(
            self.get_json("/server/destination")
        )

    def put_destination(self, destination: DestinationConfiguration) -> None:
        """Tell SERVAL where to write, sending the destination as SERVAL JSON."""
        self.put(
            "/server/destination",
            destination.model_dump(by_alias=True, exclude_none=True),
        )

    def load_pixel_config(self, server_file_path: str) -> httpx.Response:
        """Ask SERVAL to load a `.bpc` pixel-configuration file it can reach."""
        return self._load_config("pixelconfig", server_file_path)

    def load_dacs(self, server_file_path: str) -> httpx.Response:
        """Ask SERVAL to load a `.dacs` DAC-settings file it can reach."""
        return self._load_config("dacs", server_file_path)

    def _load_config(self, config_format: str, server_file_path: str) -> httpx.Response:
        # Load is a GET, and the file path is resolved by the SERVAL host (here,
        # the local machine). The response body is short free text, so callers
        # read the raw response rather than parsed JSON.
        return self.get(
            "/config/load",
            params={"format": config_format, "file": server_file_path},
        )

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
