from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes.state.models.acquisition.serval import ServalDashboard


def test_serval_dashboard_validates_manual_alias_payload() -> None:
    dashboard = ServalDashboard.model_validate(
        {
            "Server": {
                "SoftwareVersion": "3.3.0",
                "SoftwareTimestamp": "2023/10/23 14:04",
                "SoftwareCommit": "60be309",
                "SoftwareBuild": "311",
                "DiskSpace": [
                    {
                        "Message": "Free Space: 670.8 GB.",
                        "Path": "/data/raw",
                        "FreeSpace": 670758268928,
                        "WriteSpeed": 1.050576e9,
                        "LowerLimit": 100000000,
                        "DiskLimitReached": False,
                    }
                ],
                "Notifications": [
                    {
                        "Type": "info",
                        "Domain": "server",
                        "Message": "Destination ready.",
                        "ReferenceID": "REF_ID_GENERAL",
                        "Timestamp": 1617277710219,
                    }
                ],
            },
            "Measurement": {
                "StartDateTime": 1656070697593,
                "TimeLeft": 5992.0,
                "ElapsedTime": 189.855,
                "FrameCount": 379617,
                "DroppedFrames": 0,
                "Status": "DA_RECORDING",
                "PixelEventRate": 1455120,
                "Tdc1EventRate": 100,
                "Tdc2EventRate": 100,
            },
            "Detector": {"DetectorType": "Tpx3"},
        }
    )

    assert dashboard.server.software_version == "3.3.0"
    assert dashboard.server.disk_space[0].path == Path("/data/raw")
    assert dashboard.server.notifications[0].reference_id == "REF_ID_GENERAL"
    assert dashboard.measurement is not None
    assert dashboard.measurement.frame_count == 379617
    assert dashboard.measurement.status == "DA_RECORDING"
    assert dashboard.detector is not None
    assert dashboard.detector.detector_type == "Tpx3"

    dumped = dashboard.model_dump(mode="json", by_alias=True)
    assert dumped["Server"]["SoftwareVersion"] == "3.3.0"
    assert dumped["Measurement"]["FrameCount"] == 379617
    assert dumped["Detector"]["DetectorType"] == "Tpx3"


def test_serval_dashboard_accepts_pythonic_field_names() -> None:
    dashboard = ServalDashboard.model_validate(
        {
            "server": {
                "software_version": "3.3.0",
                "disk_space": [{"path": "/data/raw", "free_space": 1024}],
            },
            "measurement": {"status": "DA_IDLE", "frame_count": 0},
            "detector": {"detector_type": "Tpx3"},
        }
    )

    assert dashboard.server.software_version == "3.3.0"
    assert dashboard.measurement is not None
    assert dashboard.measurement.status == "DA_IDLE"


def test_serval_dashboard_rejects_invalid_measurement_status() -> None:
    with pytest.raises(ValidationError, match="Status"):
        ServalDashboard.model_validate(
            {
                "Server": {"SoftwareVersion": "3.3.0"},
                "Measurement": {"Status": "RUNNING"},
            }
        )
