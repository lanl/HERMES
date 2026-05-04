from __future__ import annotations

import pytest
from pydantic import ValidationError

from hermes.state.models.acquisition.serval import (
    ServalAcquisitionResult,
    ServalEnvironment,
)
from hermes.state.models.detector import DetectorInfo, DetectorSnapshot


def test_detector_snapshot_rejects_serval_dashboard() -> None:
    with pytest.raises(ValidationError, match="dashboard"):
        DetectorSnapshot(
            info=DetectorInfo(detector_type="Tpx3"),
            dashboard={"Measurement": {"Status": "DA_IDLE"}},
        )


def test_serval_models_own_dashboard_snapshots() -> None:
    dashboard = {
        "Server": {"SoftwareVersion": "3.3.0"},
        "Measurement": {"Status": "DA_IDLE", "FrameCount": 0},
        "Detector": {"DetectorType": "Tpx3"},
    }

    environment = ServalEnvironment(
        serval_url="http://127.0.0.1:8080",
        version="3.3.0",
        dashboard=dashboard,
    )
    result = ServalAcquisitionResult(status="completed", final_dashboard=dashboard)

    assert environment.dashboard is not None
    assert environment.dashboard.server.software_version == "3.3.0"
    assert result.final_dashboard is not None
    assert result.final_dashboard.measurement is not None
    assert result.final_dashboard.measurement.status == "DA_IDLE"
