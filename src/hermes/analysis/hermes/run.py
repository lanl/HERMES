from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from math import floor

import psutil
from loguru import logger

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

_ANALYSIS_LOGGER = logger.bind(
    domain="analysis",
    mode="hermes",
    step="tpx3_spidr_unpacking",
)


class HermesAnalysisError(Exception):
    """Raised when the saved state cannot run the HERMES analysis."""


def _calculate_worker_count(
    analysis: HermesTpx3AnalysisState,
    files_to_run: list[FileReference],
) -> int:
    """Calculate the worker count based on resource limits and pending files."""
    resource_fraction = analysis.resource_limit_percent / 100.0
    pending_file_count = len(files_to_run)

    physical_cpu_count = psutil.cpu_count(logical=False) or 1
    cpu_slots = max(1, floor(physical_cpu_count * resource_fraction))

    available_memory_bytes = psutil.virtual_memory().available
    largest_pending_file_size = max(
        (f.path.stat().st_size for f in files_to_run),
        default=0,
    )
    estimated_worker_memory_bytes = max(
        1 * 1024 * 1024 * 1024,
        16 * largest_pending_file_size,
    )
    memory_budget_bytes = floor(available_memory_bytes * resource_fraction)
    memory_slots = max(1, floor(memory_budget_bytes / estimated_worker_memory_bytes))

    worker_count = min(pending_file_count, cpu_slots, memory_slots)

    _ANALYSIS_LOGGER.info(
        "analysis.tpx3_unpacking.resource_calculation",
        event_type="analysis.tpx3_unpacking.resource_calculation",
        resource_limit_percent=analysis.resource_limit_percent,
        resource_fraction=resource_fraction,
        physical_cpu_count=physical_cpu_count,
        cpu_slots=cpu_slots,
        available_memory_gb=round(available_memory_bytes / (1024**3), 2),
        largest_pending_file_mb=round(largest_pending_file_size / (1024**2), 2),
        estimated_worker_memory_gb=round(
            estimated_worker_memory_bytes / (1024**3), 2
        ),
        memory_budget_gb=round(memory_budget_bytes / (1024**3), 2),
        memory_slots=memory_slots,
        pending_file_count=pending_file_count,
        worker_count=worker_count,
    )

    if estimated_worker_memory_bytes > memory_budget_bytes:
        _ANALYSIS_LOGGER.warning(
            "analysis.tpx3_unpacking.memory_warning",
            event_type="analysis.tpx3_unpacking.memory_warning",
            estimated_worker_memory_gb=round(
                estimated_worker_memory_bytes / (1024**3), 2
            ),
            memory_budget_gb=round(memory_budget_bytes / (1024**3), 2),
            message=(
                "estimated worker memory exceeds selected memory allowance; "
                "allowing at least one worker for forward progress"
            ),
        )

    return worker_count


def _run_parallel_unpacking(
    analysis: HermesTpx3AnalysisState,
    files_to_run: list[FileReference],
    worker_count: int,
) -> list[FileReference]:
    """Run unpacker processes concurrently and return successfully unpacked files."""
    first_error: Exception | None = None
    completed_files: set[int] = set()

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_index = {
            executor.submit(execute_unpacker, analysis, raw_file): i
            for i, raw_file in enumerate(files_to_run)
        }

        for future in as_completed(future_to_index):
            file_index = future_to_index[future]
            try:
                future.result()
                completed_files.add(file_index)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                    for remaining_future in future_to_index:
                        if not remaining_future.done():
                            remaining_future.cancel()

    if first_error is not None:
        raise first_error

    return [files_to_run[i] for i in sorted(completed_files)]


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

        if files_to_run:
            worker_count = _calculate_worker_count(analysis, files_to_run)
            unpacked_files = _run_parallel_unpacking(
                analysis,
                files_to_run,
                worker_count,
            )
        else:
            unpacked_files = []

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
        return unpacked_files
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
