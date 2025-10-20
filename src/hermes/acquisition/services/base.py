from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import requests
from pydantic import BaseModel, ConfigDict, Field



class ServiceError(RuntimeError):
    """Base class for service-layer exceptions."""


class ServiceConnectionError(ServiceError):
    """Raised when a service cannot be reached."""


class ServiceTimeoutError(ServiceError):
    """Raised when a service request times out."""


class ServiceResponseError(ServiceError):
    """Raised when a service returns an unexpected response."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, body: Optional[str] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ServiceHealthStatus(BaseModel):
    """Health snapshot reported by service implementations."""

    is_connected: bool = Field(..., description="True when the last operation reached the service endpoint.")
    is_healthy: bool = Field(..., description="True when the service reports nominal status.")
    last_check: datetime = Field(default_factory=_utcnow, description="UTC timestamp of the health check.")
    response_time_ms: Optional[float] = Field(
        default=None, ge=0.0, description="Latency of the last probe in milliseconds if available."
    )
    detail: Optional[str] = Field(default=None, description="Optional human-readable context for operators.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional structured details from probes.")

    model_config = ConfigDict(extra="forbid")


class BaseHTTPService:
    """Convenience wrapper for HTTP-based services with shared error handling."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url must be provided")

        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = session or requests.Session()
        self._owns_session = session is None

    @property
    def base_url(self) -> str:
        """Base URL used for all outgoing requests."""

        return self._base_url

    @property
    def timeout(self) -> float:
        """Default request timeout in seconds."""

        return self._timeout

    def close(self) -> None:
        """Release any resources held by the underlying HTTP session."""

        if self._owns_session:
            self._session.close()

    # Allow usage as a context manager so callers can rely on deterministic cleanup.
    def __enter__(self) -> "BaseHTTPService":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
        expected_status: Iterable[int] | int = 200,
        timeout: Optional[float] = None,
    ) -> requests.Response:
        """Perform an HTTP request with consistent error handling."""

        url = f"{self._base_url}{endpoint}"
        try:
            response = self._session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json,
                timeout=timeout or self._timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise ServiceTimeoutError(f"Request to {url} timed out") from exc
        except requests.exceptions.RequestException as exc:
            raise ServiceConnectionError(f"Request to {url} failed: {exc}") from exc

        if isinstance(expected_status, int):
            expected_codes = {expected_status}
        else:
            expected_codes = set(expected_status)

        if response.status_code not in expected_codes:
            body_preview = response.text[:2048] if response.text else "<empty>"
            raise ServiceResponseError(
                f"Unexpected response {response.status_code} from {url}",
                status_code=response.status_code,
                body=body_preview,
            )

        return response

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
        expected_status: Iterable[int] | int = 200,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """Perform an HTTP request expecting a JSON response."""

        response = self._request(
            method,
            endpoint,
            params=params,
            json=json,
            expected_status=expected_status,
            timeout=timeout,
        )

        if not response.content:
            return {}

        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - defensive guard
            body_preview = response.text[:2048] if response.text else "<empty>"
            raise ServiceResponseError(
                f"Failed to decode JSON response from {response.url}",
                status_code=response.status_code,
                body=body_preview,
            ) from exc


__all__ = [
    "BaseHTTPService",
    "ServiceError",
    "ServiceConnectionError",
    "ServiceTimeoutError",
    "ServiceResponseError",
    "ServiceHealthStatus",
]
