from __future__ import annotations

from typing import TypeAlias

from pydantic import Field

from hermes.state.models.acquisition.serval import ServalAcquisitionState
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3SpidrAnalysisState,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import StrictBaseModel

AcquisitionState: TypeAlias = ServalAcquisitionState
AnalysisState: TypeAlias = HermesTpx3SpidrAnalysisState


class HermesRecord(StrictBaseModel):
    """Top-level durable state record for one HERMES run."""

    measurement_info: MeasurementInfo
    environment: RuntimeEnvironment
    acquisition: AcquisitionState | None = Field(default=None)
    analysis: AnalysisState | None = Field(default=None)
