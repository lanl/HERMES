"""Select the EMPIR or HERMES analysis runner from the saved analysis mode."""

from __future__ import annotations

from loguru import logger

from hermes.runner.analysis.empir.run import run_empir_analysis
from hermes.runner.analysis.hermes.run import run_hermes_analysis
from hermes.state.models.analysis.empir import EmpirAnalysisState
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
)
from hermes.state.models.shared_models import FileReference
from hermes.state_service.state_manager import StateManager

_ANALYSIS_LOGGER = logger.bind(domain="analysis", step="dispatch")


class AnalysisModeError(Exception):
    """Raised when the saved state has no runnable analysis mode."""


def run_analysis(
    state_manager: StateManager,
    *,
    overwrite: bool = False,
) -> list[FileReference]:
    """Run the analysis selected by ``analysis.mode`` in the current record.

    HERMES analysis honors ``overwrite``. EMPIR analysis has no overwrite
    behavior; its preflight rejects an output that already exists.
    """
    analysis = state_manager.get_state().analysis

    if isinstance(analysis, EmpirAnalysisState):
        return run_empir_analysis(state_manager)
    if isinstance(analysis, HermesTpx3AnalysisState):
        return run_hermes_analysis(state_manager, overwrite=overwrite)

    error = "no valid analysis mode is configured"
    _ANALYSIS_LOGGER.error(
        "Cannot run analysis: {error}",
        event_type="analysis.dispatch.invalid_mode",
        error=error,
        actual_analysis_mode=getattr(analysis, "mode", None),
    )
    raise AnalysisModeError(error)
