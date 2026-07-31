from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from math import floor

import psutil
from loguru import logger

from hermes.analysis.hermes.reconstruction import (
    HermesReconstructionError,
    derive_output_path,
    execute_reconstruction,
    plan_reconstruction,
)
from hermes.analysis.hermes.reconstruction import (
    log_overall_completion as log_reconstruction_completion,
)
from hermes.analysis.hermes.reconstruction import (
    log_overall_failure as log_reconstruction_failure,
)
from hermes.analysis.hermes.reconstruction import (
    log_skipped_input as log_reconstruction_skipped,
)
from hermes.analysis.hermes.unpacker import (
    HermesTpx3Error,
    execute_unpacker,
    log_overall_completion,
    log_overall_failure,
    log_skipped_input,
    plan_unpacking,
)
from hermes.state.models.analysis.empir import EmpirAnalysisState
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3ReconstructionResult,
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


def _run_parallel(executor_fn, items, worker_count):
    """Run ``executor_fn`` over ``items`` concurrently, stopping on first error.

    Returns ``{index: result}`` for the items that completed successfully. On
    the first failure the remaining not-started futures are cancelled and the
    error is re-raised once in-flight work drains.
    """
    first_error: Exception | None = None
    results: dict[int, object] = {}

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_index = {
            executor.submit(executor_fn, item): i
            for i, item in enumerate(items)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                results[index] = future.result()
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                    for remaining_future in future_to_index:
                        if not remaining_future.done():
                            remaining_future.cancel()

    if first_error is not None:
        raise first_error

    return results


def run_hermes_analysis(
    state_manager: StateManager,
    *,
    overwrite: bool = False,
) -> list[FileReference]:
    state = state_manager.get_state()
    analysis = state.analysis
    if isinstance(analysis, EmpirAnalysisState):
        error = "EMPIR analysis is not implemented yet"
        _ANALYSIS_LOGGER.error(
            "Cannot run HERMES analysis: {error}",
            event_type="analysis.hermes.invalid_mode",
            error=error,
            measurement_id=state.measurement_info.measurement_id,
            run_number=state.measurement_info.run_number,
            expected_analysis_mode="hermes",
            actual_analysis_mode=getattr(analysis, "mode", None),
        )
        raise HermesAnalysisError(error)
    if not isinstance(analysis, HermesTpx3AnalysisState):
        error = "no valid HERMES analysis is configured"
        _ANALYSIS_LOGGER.error(
            "Cannot run HERMES analysis: {error}",
            event_type="analysis.hermes.invalid_mode",
            error=error,
            measurement_id=state.measurement_info.measurement_id,
            run_number=state.measurement_info.run_number,
            expected_analysis_mode="hermes",
            actual_analysis_mode=getattr(analysis, "mode", None),
        )
        raise HermesAnalysisError(error)

    unpack_overwrite = overwrite or analysis.unpacking.runtime_options.overwrite
    try:
        unpacking_plan = plan_unpacking(analysis, overwrite=unpack_overwrite)
        files_to_run = [
            raw_file
            for raw_file, action in unpacking_plan
            if action == "run"
        ]

        for raw_file, action in unpacking_plan:
            if action == "skip":
                log_skipped_input(analysis, raw_file)

        started_at = utc_now()
        if files_to_run:
            worker_count = _calculate_worker_count(analysis, files_to_run)
            completed = _run_parallel(
                lambda raw_file: execute_unpacker(
                    analysis, raw_file, overwrite=unpack_overwrite
                ),
                files_to_run,
                worker_count,
            )
            unpacked_files = [files_to_run[i] for i in sorted(completed)]
        else:
            unpacked_files = []

        completed_at = utc_now()
        unpacking_results = [
            HermesTpx3UnpackingResult(
                input_file=raw_file,
                status="completed" if action == "run" else "skipped",
                started_at=started_at if action == "run" else None,
                completed_at=completed_at if action == "run" else None,
            )
            for raw_file, action in unpacking_plan
        ]
        _apply_unpacking_results(
            state_manager,
            unpacking_results,
            justification="unpacked new raw TPX3 files; revalidated existing outputs",
        )
        log_overall_completion(
            raw_file_count=len(unpacking_plan),
            unpacked_file_count=len(files_to_run),
        )

        current_analysis = _current_hermes_analysis(state_manager)
        if current_analysis.photon_reconstruction is not None:
            _run_photon_reconstruction(
                state_manager, current_analysis, overwrite=overwrite
            )

        return unpacked_files
    except HermesTpx3Error as exc:
        current_analysis = state_manager.get_state().analysis
        if isinstance(current_analysis, HermesTpx3AnalysisState):
            _apply_unpacking_results(
                state_manager,
                [
                    HermesTpx3UnpackingResult(
                        input_file=raw_file,
                        status="failed",
                        completed_at=utc_now(),
                    )
                    for raw_file in current_analysis.unpacking.tpx3_files
                ],
                justification=f"TPX3 SPIDR unpacking failed: {exc}",
            )
        log_overall_failure(exc)
        raise


def _run_photon_reconstruction(
    state_manager: StateManager,
    analysis: HermesTpx3AnalysisState,
    *,
    overwrite: bool = False,
) -> None:
    """Reconstruct photons file-by-file in parallel, recording per-file results."""
    reconstruction = analysis.photon_reconstruction
    assert reconstruction is not None
    recon_overwrite = overwrite or reconstruction.runtime_options.overwrite
    try:
        reconstruction_plan = plan_reconstruction(
            analysis, overwrite=recon_overwrite
        )
        files_to_run = [
            input_file
            for input_file, action in reconstruction_plan
            if action == "run"
        ]

        skipped_results: list[HermesTpx3ReconstructionResult] = []
        for input_file, action in reconstruction_plan:
            if action == "skip":
                output_file = derive_output_path(reconstruction, input_file)
                log_reconstruction_skipped(input_file, output_file)
                skipped_results.append(
                    HermesTpx3ReconstructionResult(
                        input_file=input_file,
                        output_file=output_file,
                        status="completed",
                    )
                )

        if files_to_run:
            worker_count = _calculate_worker_count(analysis, files_to_run)
            completed = _run_parallel(
                lambda input_file: execute_reconstruction(
                    analysis, input_file, overwrite=recon_overwrite
                ),
                files_to_run,
                worker_count,
            )
            run_results = [completed[i] for i in sorted(completed)]
        else:
            run_results = []

        _apply_reconstruction_results(
            state_manager,
            skipped_results + run_results,
            justification="every pixel file passed photon reconstruction",
        )
        log_reconstruction_completion(
            pixel_file_count=len(reconstruction_plan),
            reconstructed_file_count=len(files_to_run),
        )
    except HermesReconstructionError as exc:
        _apply_reconstruction_results(
            state_manager,
            [
                HermesTpx3ReconstructionResult(
                    input_file=input_file,
                    output_file=derive_output_path(reconstruction, input_file),
                    status="failed",
                    completed_at=utc_now(),
                )
                for input_file in _reconstruction_inputs(analysis)
            ],
            justification=f"photon reconstruction failed: {exc}",
        )
        log_reconstruction_failure(exc)
        raise


def _reconstruction_inputs(
    analysis: HermesTpx3AnalysisState,
) -> list[FileReference]:
    """Best-effort pixel-file list for failure reporting (never raises)."""
    from hermes.analysis.hermes.reconstruction import resolve_pixel_files

    try:
        return resolve_pixel_files(analysis)
    except Exception:
        return []


def _current_hermes_analysis(
    state_manager: StateManager,
) -> HermesTpx3AnalysisState:
    current_analysis = state_manager.get_state().analysis
    if not isinstance(current_analysis, HermesTpx3AnalysisState):
        raise HermesAnalysisError(
            "the saved analysis mode changed during analysis"
        )
    return current_analysis


def _apply_unpacking_results(
    state_manager: StateManager,
    results: list[HermesTpx3UnpackingResult],
    *,
    justification: str,
) -> None:
    change = state_manager.propose_change(
        "analysis.unpacking.results",
        results,
        origin="trusted_workflow",
        proposer="tpx3_spidr_unpacking",
        justification=justification,
    )
    state_manager.apply_change(change.change_id)


def _apply_reconstruction_results(
    state_manager: StateManager,
    results: list[HermesTpx3ReconstructionResult],
    *,
    justification: str,
) -> None:
    change = state_manager.propose_change(
        "analysis.photon_reconstruction.results",
        results,
        origin="trusted_workflow",
        proposer="tpx3_spidr_reconstruction",
        justification=justification,
    )
    state_manager.apply_change(change.change_id)
