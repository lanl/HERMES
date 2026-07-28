from __future__ import annotations

from hermes.analysis.hermes.run import run_hermes_analysis
from hermes.state.models.shared_models import FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_manager import StateManager


class Workflow:
    """Run HERMES operations against one measurement record."""

    def __init__(self, record: HermesRecord) -> None:
        self._state_manager = StateManager(
            record,
            config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        )

    def run_analysis(self, *, overwrite: bool = False) -> list[FileReference]:
        return run_hermes_analysis(
            self._state_manager,
            overwrite=overwrite,
        )

    @property
    def record(self) -> HermesRecord:
        return self._state_manager.get_state()
