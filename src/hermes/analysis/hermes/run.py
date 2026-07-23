from __future__ import annotations

from hermes.analysis.hermes.unpacker import (
    HermesTpx3Error,
    execute_unpacker,
    log_overall_completion,
    log_overall_failure,
    log_skipped_input,
    plan_unpacking,
)
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

    try:
        unpacking_plan = plan_unpacking(analysis)
        files_to_run = [
            raw_file
            for raw_file, action in unpacking_plan
            if action == "run"
        ]

        if files_to_run:
            _apply_unpacking_result(
                state_manager,
                analysis,
                HermesTpx3UnpackingResult(
                    status="running",
                    started_at=utc_now(),
                ),
                justification="TPX3 SPIDR unpacking is ready to start",
            )

        for raw_file, action in unpacking_plan:
            if action == "skip":
                log_skipped_input(analysis, raw_file)
            else:
                execute_unpacker(analysis, raw_file)

        current_analysis = state_manager.get_state().analysis
        if not isinstance(current_analysis, HermesTpx3AnalysisState):
            raise HermesAnalysisError("the saved analysis mode changed during unpacking")
        _apply_unpacking_result(
            state_manager,
            current_analysis,
            HermesTpx3UnpackingResult(
                status="completed",
                started_at=current_analysis.results.unpacking.started_at,
                finished_at=utc_now(),
            ),
            justification="every raw TPX3 file passed unpacking validation",
        )
        log_overall_completion(
            raw_file_count=len(unpacking_plan),
            unpacked_file_count=len(files_to_run),
        )
        return files_to_run
    except HermesTpx3Error as exc:
        current_analysis = state_manager.get_state().analysis
        if isinstance(current_analysis, HermesTpx3AnalysisState):
            _apply_unpacking_result(
                state_manager,
                current_analysis,
                HermesTpx3UnpackingResult(
                    status="failed",
                    started_at=current_analysis.results.unpacking.started_at,
                    finished_at=utc_now(),
                ),
                justification=f"TPX3 SPIDR unpacking failed: {exc}",
            )
        log_overall_failure(exc)
        raise


def _apply_unpacking_result(
    state_manager: StateManager,
    analysis: HermesTpx3AnalysisState,
    unpacking_result: HermesTpx3UnpackingResult,
    *,
    justification: str,
) -> None:
    results = HermesTpx3AnalysisResults(
        unpacking=unpacking_result,
        reconstruction=analysis.results.reconstruction,
    )
    change = state_manager.propose_change(
        "analysis.results",
        results,
        origin="trusted_workflow",
        proposer="tpx3_spidr_unpacking",
        justification=justification,
    )
    state_manager.apply_change(change.change_id)
