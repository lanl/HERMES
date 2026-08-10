from __future__ import annotations

from loguru import logger

from hermes.runner.analysis.run import run_analysis
from hermes.logging import configure_logging
from hermes.state.models.shared_models import FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_manager import StateManager

_WORKFLOW_LOGGER = logger.bind(domain="workflow")


class Workflow:
    """Run HERMES operations against one measurement record."""

    def __init__(self, record: HermesRecord) -> None:
        log_dir = record.environment.log_directory.resolved_path
        configure_logging(log_dir, level=record.environment.log_level)
        self._state_manager = StateManager(
            record,
            config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        )
        _WORKFLOW_LOGGER.info(
            "Initialized HERMES workflow for measurement {measurement_id}, "
            "run {run}",
            event_type="workflow.initialized",
            measurement_id=record.measurement_info.measurement_id,
            run=record.measurement_info.run,
        )

    def run_analysis(self, *, overwrite: bool = False) -> list[FileReference]:
        return run_analysis(
            self._state_manager,
            overwrite=overwrite,
        )

    def run_acquisition(self) -> None:
        """Reserve the acquisition entry point until acquisition is implemented."""
        raise NotImplementedError("HERMES acquisition is not implemented")

    def run(self) -> None:
        """Reserve the combined acquisition-to-analysis entry point."""
        raise NotImplementedError(
            "combined HERMES acquisition and analysis is not implemented"
        )

    @property
    def record(self) -> HermesRecord:
        return self._state_manager.get_state()
