from __future__ import annotations

from typing import Annotated, Any, TypeAlias

from pydantic import Field, model_validator

from hermes.state.models.acquisition.serval import ServalAcquisitionState
from hermes.state.models.analysis.empir import EmpirAnalysisState
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import StrictBaseModel

AcquisitionState: TypeAlias = ServalAcquisitionState
AnalysisState: TypeAlias = Annotated[
    HermesTpx3AnalysisState | EmpirAnalysisState,
    Field(discriminator="mode"),
]


class HermesRecord(StrictBaseModel):
    """Top-level durable state record for one HERMES run."""

    measurement_info: MeasurementInfo
    environment: RuntimeEnvironment
    acquisition: AcquisitionState | None = Field(default=None)
    analysis: AnalysisState | None = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def default_run_directory_to_run_name(cls, data: Any) -> Any:
        """Use the run name as the run directory when one is not given.

        A config that names ``measurement_info.run`` but leaves
        ``environment.run_directory`` out then lays its outputs out under
        ``<working_directory>/<run>/...`` instead of straight in the working
        directory, so the run name lives in one place. An explicit
        ``run_directory`` always wins. This runs before the environment resolves
        its directories, so they nest under the run name. The run name is used
        exactly as written; set ``run_directory`` yourself when the run name
        would make an awkward directory name.
        """
        if not isinstance(data, dict):
            return data
        environment = data.get("environment")
        if not isinstance(environment, dict):
            return data
        if environment.get("run_directory") is not None:
            return data
        measurement_info = data.get("measurement_info")
        if not isinstance(measurement_info, dict):
            return data
        run = measurement_info.get("run")
        if not isinstance(run, str) or not run.strip():
            return data
        return {
            **data,
            "environment": {**environment, "run_directory": run.strip()},
        }
