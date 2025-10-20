from __future__ import annotations

import time
from typing import Any, Dict, Optional

from hermes.acquisition.logger import logger
from hermes.acquisition.models.environment import ServalDeployment
from hermes.acquisition.models.tpx_serval.dashboard import Dashboard
from hermes.acquisition.models.tpx_serval.destinations import Destination
from hermes.acquisition.models.tpx_serval.measurement import MeasurementConfig
from hermes.acquisition.services.base import (
    BaseHTTPService,
    ServiceError,
    ServiceHealthStatus,
)


class ServalHTTPService(BaseHTTPService):
    """HTTP client for interacting with a Serval acquisition server."""

    def __init__(
        self,
        deployment: ServalDeployment,
        *,
        timeout: float = 5.0,
        session=None,
    ) -> None:
        base_url = f"http://{deployment.host}:{deployment.port}"
        super().__init__(base_url, timeout=timeout, session=session)
        self._deployment = deployment

    # ---------------------------------------------------------------------
    # Core API helpers
    # ---------------------------------------------------------------------
    def _dump_payload(self, model: Any) -> Dict[str, Any]:
        return model.model_dump(by_alias=True, exclude_none=True)

    # ---------------------------------------------------------------------
    # Dashboard & health monitoring
    # ---------------------------------------------------------------------
    def get_dashboard(self) -> Dashboard:
        """Fetch the Serval dashboard snapshot."""

        payload = self._request_json("GET", "/dashboard")
        dashboard = Dashboard.model_validate(payload)
        logger.debug(
            "Serval dashboard: version=%s status=%s detector=%s",
            dashboard.server.software_version,
            dashboard.measurement.status,
            dashboard.detector.detector_type,
        )
        return dashboard

    def health_check(self) -> ServiceHealthStatus:
        """Probe Serval and return a structured health snapshot."""

        start = time.perf_counter()
        try:
            dashboard = self.get_dashboard()
        except ServiceError as exc:
            logger.warning("Serval health probe failed: %s", exc)
            duration_ms = (time.perf_counter() - start) * 1000.0
            return ServiceHealthStatus(
                is_connected=False,
                is_healthy=False,
                response_time_ms=duration_ms,
                detail=str(exc),
            )

        duration_ms = (time.perf_counter() - start) * 1000.0
        metadata: Dict[str, Any] = {
            "software_version": dashboard.server.software_version,
            "status": dashboard.measurement.status.value if dashboard.measurement.status else None,
            "frame_count": dashboard.measurement.frame_count,
            "detector_type": dashboard.detector.detector_type,
        }
        return ServiceHealthStatus(
            is_connected=True,
            is_healthy=True,
            response_time_ms=duration_ms,
            metadata={k: v for k, v in metadata.items() if v is not None},
        )

    # ---------------------------------------------------------------------
    # Measurement control
    # ---------------------------------------------------------------------
    def start_measurement(self) -> None:
        """Trigger Serval to start acquiring data."""

        logger.info("Requesting Serval measurement start")
        self._request("GET", "/measurement/start", expected_status=(200, 204))

    def stop_measurement(self) -> None:
        """Request Serval to stop the current acquisition."""

        logger.info("Requesting Serval measurement stop")
        self._request("GET", "/measurement/stop", expected_status=(200, 204))

    def get_measurement_config(self) -> Optional[MeasurementConfig]:
        """Retrieve the current measurement configuration."""

        response = self._request("GET", "/measurement/config", expected_status=(200, 204))
        if response.status_code == 204 or not response.content:
            return None
        payload = response.json()
        return MeasurementConfig.model_validate(payload)

    def set_measurement_config(self, config: MeasurementConfig) -> None:
        """Upload a measurement configuration to Serval."""

        logger.info("Uploading Serval measurement configuration")
        self._request(
            "PUT",
            "/measurement/config",
            json=self._dump_payload(config),
            expected_status=(200, 204),
        )

    # ---------------------------------------------------------------------
    # Destination management
    # ---------------------------------------------------------------------
    def get_destination(self) -> Optional[Destination]:
        """Return the current Serval destination configuration."""

        response = self._request("GET", "/server/destination", expected_status=(200, 204))
        if response.status_code == 204 or not response.content:
            return None
        payload = response.json()
        return Destination.model_validate(payload)

    def set_destination(self, destination: Destination) -> None:
        """Upload a destination configuration."""

        logger.info("Uploading Serval destination configuration")
        self._request(
            "PUT",
            "/server/destination",
            json=self._dump_payload(destination),
            expected_status=(200, 204),
        )

    # ---------------------------------------------------------------------
    # Convenience accessors
    # ---------------------------------------------------------------------
    @property
    def deployment(self) -> ServalDeployment:
        """Return the deployment descriptor used by this service."""

        return self._deployment


__all__ = ["ServalHTTPService"]
