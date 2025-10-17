# src/hermes/acquisition/models/dashboard.py
"""
Dashboard models for HERMES (Serval integration).

Manual references
─────────────────
- Serval v3.3 (2023): §4.8 "/dashboard requests" and §4.8.1 "dashboard JSON structure" (tables 4.11 – 4.12). 
  * Adds nested Server.DiskSpace, extended Measurement fields, Detector health/temperature rates.
- Serval v1.22 (2021; Serval 2.1.5): §4.8 "/dashboard requests" and §4.8.1 "dashboard JSON structure" (Table 4.11). 
  * Contains Server.SoftwareVersion, Measurement.TimeLeft/ElapsedTime/FrameCount/PixelEventRate/Status, Detector.DetectorType.

Versioning notes
────────────────
- Structure unchanged; v3.3 only adds optional fields.
- Keep new fields optional for backward-compatibility.
- Use `model_dump(by_alias=True)` when sending or logging JSON.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import Field

# explicit imports (no implicit __init__.py usage)
from .common import HermesBaseModel, HermesRuntimeModel, AcquisitionStatus


# =============================================================================
# Server sub-object — present in both 2.1.5 & 3.3
# =============================================================================
class ServerInfo(HermesBaseModel):
    """
    Server-level metadata.
    v1.22 Table 4.11: "SoftwareVersion", "SoftwareTimestamp".
    v3.3 adds optional "DiskSpace" array for free/total storage. 
    """
    software_version: str = Field(..., alias="SoftwareVersion")
    software_timestamp: Optional[str] = Field(None, alias="SoftwareTimestamp")
    notifications: Optional[List[str]] = Field(default_factory=list, alias="Notifications")
    # [v3.3+] DiskSpace list (added for monitoring available storage) 
    disk_space: Optional[List["DiskSpace"]] = Field(default=None, alias="DiskSpace")


# =============================================================================
# Measurement sub-object — runtime acquisition telemetry
# =============================================================================
class MeasurementStatus(HermesRuntimeModel):
    """
    Measurement telemetry.
    v1.22 Table 4.11: StartDateTime, TimeLeft, ElapsedTime, FrameCount, PixelEventRate, Status.
    v3.3 adds extended rate metrics and disk usage integration. 
    """
    start_datetime: Optional[int] = Field(None, alias="StartDateTime", description="UNIX timestamp of measurement start [v1.22 §4.8.1]")
    time_left_s: Optional[float] = Field(None, alias="TimeLeft", ge=0.0)
    elapsed_time_s: Optional[float] = Field(None, alias="ElapsedTime", ge=0.0)
    frame_count: Optional[int] = Field(None, alias="FrameCount", ge=0)
    pixel_event_rate: Optional[int] = Field(None, alias="PixelEventRate", ge=0)
    status: Optional[AcquisitionStatus] = Field(None, alias="Status")
    # [v3.3+] Additional optional telemetry fields (e.g., DiskUsage, DroppedFrames)
    disk_usage_gb: Optional[float] = Field(None, alias="DiskUsageGB")
    dropped_frames: Optional[int] = Field(None, alias="DroppedFrames")


# =============================================================================
# Detector sub-object — type & summary state
# =============================================================================
class DetectorSummary(HermesBaseModel):
    """
    Detector summary from /dashboard.
    v1.22 Table 4.11: "DetectorType".
    v3.3 adds optional Temperature and Health fields. 
    """
    detector_type: str = Field(..., alias="DetectorType")
    # [v3.3+] additional fields seen in extended dashboard
    temperature_c: Optional[float] = Field(None, alias="TemperatureC")
    health: Optional[str] = Field(None, alias="Health")


# =============================================================================
# DiskSpace sub-object (v3.3 only)
# =============================================================================
class DiskSpace(HermesBaseModel):
    """
    Server disk space report.
    Introduced in Serval v3.3 dashboard (Table 4.12 approx.). 
    """
    mount: str = Field(..., alias="Mount")
    free_gb: float = Field(..., alias="FreeGB")
    total_gb: float = Field(..., alias="TotalGB")


# =============================================================================
# Root Dashboard object (/dashboard response)
# =============================================================================
class Dashboard(HermesBaseModel):
    """
    Complete /dashboard snapshot.

    v1.22 §4.8.1 structure:
      {
        "Server": { SoftwareVersion, SoftwareTimestamp },
        "Measurement": { … },
        "Detector": { DetectorType }
      }
    v3.3 adds:
      - Server.DiskSpace[]
      - Measurement extra metrics
      - Detector temperature & health fields. 
    """
    server: ServerInfo = Field(..., alias="Server")
    measurement: MeasurementStatus = Field(..., alias="Measurement")
    detector: DetectorSummary = Field(..., alias="Detector")

    # [v3.3+] optional global server health aggregates (not in 2.1.5)
    server_load_percent: Optional[float] = Field(None, alias="ServerLoadPercent")
    server_uptime_s: Optional[float] = Field(None, alias="ServerUptimeSeconds")
