from __future__ import annotations

from hermes.analysis.hermes.run import run_hermes_analysis
from hermes.logging import configure_logging
from hermes.state.models.shared_models import FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_manager import StateManager


class Workflow:
    """Run HERMES operations against one measurement record."""

    def __init__(self, record: HermesRecord) -> None:
        log_dir = record.environment.log_dir.resolved_path
        if log_dir is not None:
            configure_logging(log_dir)
        self._state_manager = StateManager(
            record,
            config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        )

    def run_analysis(self, *, overwrite: bool = False) -> list[FileReference]:
        return run_hermes_analysis(
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
