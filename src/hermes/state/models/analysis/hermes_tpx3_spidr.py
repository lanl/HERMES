from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from hermes.state.models.payloads import ExternalPayloadRef
from hermes.state.models.shared_models import ArtifactRef, JsonObject, StrictBaseModel

AnalysisRunStatus = Literal[
    "planned",
    "running",
    "completed",
    "failed",
    "skipped",
    "unknown",
]


class HermesTpx3SpidrEnvironment(StrictBaseModel):
    binary_path: Path | None = None
    version: str | None = None


class ClusterConfig(StrictBaseModel):
    max_spatial_distance_px: float | None = Field(default=None, ge=0)
    max_time_distance_ns: float | None = Field(default=None, ge=0)
    min_cluster_size: int | None = Field(default=None, ge=0)
    options: JsonObject = Field(default_factory=dict)


class HermesTpx3SpidrConfig(StrictBaseModel):
    command_args: list[str] = Field(default_factory=list)
    cluster_config: ClusterConfig | ExternalPayloadRef | None = None
    options: JsonObject = Field(default_factory=dict)


class HermesTpx3SpidrResult(StrictBaseModel):
    status: AnalysisRunStatus = "unknown"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exit_code: int | None = None
    input_artifacts: list[ArtifactRef] = Field(default_factory=list)
    output_artifacts: list[ArtifactRef] = Field(default_factory=list)
    summary_artifact: ArtifactRef | None = None
    summary_metrics: JsonObject = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class HermesTpx3SpidrAnalysisState(StrictBaseModel):
    mode: Literal["hermes_tpx3_spidr"] = "hermes_tpx3_spidr"
    environment: HermesTpx3SpidrEnvironment | None = None
    config: HermesTpx3SpidrConfig | None = None
    result: HermesTpx3SpidrResult | None = None
