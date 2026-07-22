from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from hermes.state.models.shared_models import FileReference, StrictBaseModel

AnalysisRunStatus = Literal[
    "planned",
    "running",
    "completed",
    "failed",
    "skipped",
    "unknown",
]


class Tpx3SpidrUnpackerProgram(StrictBaseModel):
    name: str = Field(min_length=1)
    executable_path: Path
    version: str | None = None


class Tpx3SpidrUnpackerSettings(StrictBaseModel):
    input_tpx3_file: FileReference
    tpx3_parquet_directory: Path
    command_args: list[str] = Field(default_factory=list)


class Tpx3SpidrUnpackerResult(StrictBaseModel):
    status: AnalysisRunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exit_code: int | None = None
    summary_json_file: FileReference | None = None
    pixel_hit_count: int | None = Field(default=None, ge=0)
    tdc_hit_count: int | None = Field(default=None, ge=0)
    global_timestamp_count: int | None = Field(default=None, ge=0)
    spidr_control_count: int | None = Field(default=None, ge=0)
    tpx3_control_count: int | None = Field(default=None, ge=0)
    unknown_packet_count: int | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class Tpx3SpidrUnpackingRun(StrictBaseModel):
    program: Tpx3SpidrUnpackerProgram
    settings: Tpx3SpidrUnpackerSettings
    result: Tpx3SpidrUnpackerResult = Field(default_factory=Tpx3SpidrUnpackerResult)


class HermesPhotonReconstructionState(StrictBaseModel):
    pass


class HermesEventReconstructionState(StrictBaseModel):
    pass


class HermesTpx3AnalysisState(StrictBaseModel):
    mode: Literal["hermes"] = "hermes"
    unpacking_runs: list[Tpx3SpidrUnpackingRun] = Field(min_length=1)
    photon_reconstruction: HermesPhotonReconstructionState | None = None
    event_reconstruction: HermesEventReconstructionState | None = None
