from __future__ import annotations

from hermes.analysis.hermes.unpacker import plan_unpacking
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisResults,
    HermesTpx3AnalysisState,
    HermesTpx3UnpackingResult,
)
from hermes.state.models.shared_models import FileReference, utc_now
from hermes.state_service.state_manager import StateManager


class HermesAnalysisError(Exception):
    """Raised when the saved state cannot run the HERMES analysis."""


def run_hermes_analysis(state_manager: StateManager) -> list[FileReference]:
    state = state_manager.get_state()
    analysis = state.analysis
    if not isinstance(analysis, HermesTpx3AnalysisState):
        raise HermesAnalysisError("the saved analysis mode is not HERMES")

    unpacking_plan = plan_unpacking(analysis)
    files_to_run = [
        raw_file
        for raw_file, action in unpacking_plan
        if action == "run"
    ]
    if not files_to_run:
        return []

    running_results = HermesTpx3AnalysisResults(
        unpacking=HermesTpx3UnpackingResult(
            status="running",
            started_at=utc_now(),
        ),
        reconstruction=analysis.results.reconstruction,
    )
    change = state_manager.propose_change(
        "analysis.results",
        running_results,
        origin="trusted_workflow",
        proposer="tpx3_spidr_unpacking",
        justification="TPX3 SPIDR unpacking is ready to start",
    )
    state_manager.apply_change(change.change_id)

    return files_to_run
