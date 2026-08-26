from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from math import floor
from pathlib import Path

import psutil
from loguru import logger

from hermes.runner.analysis.hermes.event_reconstruction import (
    HermesEventReconstructionError,
    execute_event_reconstruction,
    resolve_raw_file_stems,
)
from hermes.runner.analysis.hermes.event_reconstruction import (
    check_previous_reconstructed_file as check_previous_event_reconstructed_file,
)
from hermes.runner.analysis.hermes.event_reconstruction import (
    derive_output_path as derive_event_output_path,
)
from hermes.runner.analysis.hermes.event_reconstruction import (
    validate_program_and_algorithm as validate_event_program_and_algorithm,
)
from hermes.runner.analysis.hermes.event_reconstruction import (
    log_overall_completion as log_event_reconstruction_completion,
)
from hermes.runner.analysis.hermes.event_reconstruction import (
    log_overall_failure as log_event_reconstruction_failure,
)
from hermes.runner.analysis.hermes.event_reconstruction import (
    log_skipped_input as log_event_reconstruction_skipped,
)
from hermes.runner.analysis.hermes.photon_reconstruction import (
    HermesPhotonReconstructionError,
    check_previous_reconstructed_file,
    derive_output_path,
    execute_reconstruction,
    resolve_pixel_files,
    validate_program_and_algorithm,
)
from hermes.runner.analysis.hermes.photon_reconstruction import (
    log_overall_completion as log_reconstruction_completion,
)
from hermes.runner.analysis.hermes.photon_reconstruction import (
    log_overall_failure as log_reconstruction_failure,
)
from hermes.runner.analysis.hermes.photon_reconstruction import (
    log_skipped_input as log_reconstruction_skipped,
)
from hermes.runner.analysis.hermes.unpacker import (
    HermesTpx3Error,
    check_previous_unpacked_file,
    execute_unpacker,
    log_overall_completion,
    log_overall_failure,
    log_skipped_input,
    resolve_tpx3_files,
    validate_program_and_inputs,
)
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3EventReconstructionResult,
    HermesTpx3PhotonReconstructionResult,
    HermesTpx3UnpackingResult,
)
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import FileReference
from hermes.state_service.state_manager import StateManager

_ANALYSIS_LOGGER = logger.bind(
    domain="analysis",
    mode="hermes",
    step="tpx3_spidr_unpacking",
)


class HermesAnalysisError(Exception):
    """Raised when the saved state cannot run the HERMES analysis."""


def _largest_file_bytes(files: list[FileReference]) -> int:
    """Return the size in bytes of the largest file, or 0 for an empty list."""
    return max((f.path.stat().st_size for f in files), default=0)


def _calculate_worker_count(
    analysis: HermesTpx3AnalysisState,
    pending_count: int,
    largest_input_bytes: int,
) -> int:
    """Calculate the worker count based on resource limits and pending work.

    ``pending_count`` is how many items are queued and ``largest_input_bytes``
    is the biggest single input each worker reads, used to size a per-worker
    memory allowance.
    """
    resource_fraction = analysis.resource_limit_percent / 100.0

    physical_cpu_count = psutil.cpu_count(logical=False) or 1
    cpu_slots = max(1, floor(physical_cpu_count * resource_fraction))

    available_memory_bytes = psutil.virtual_memory().available
    estimated_worker_memory_bytes = max(
        1 * 1024 * 1024 * 1024,
        16 * largest_input_bytes,
    )
    memory_budget_bytes = floor(available_memory_bytes * resource_fraction)
    memory_slots = max(1, floor(memory_budget_bytes / estimated_worker_memory_bytes))

    worker_count = min(pending_count, cpu_slots, memory_slots)

    _ANALYSIS_LOGGER.info(
        "Using {worker_count} worker(s) for {pending_count} item(s)",
        event_type="analysis.tpx3_unpacking.resource_calculation",
        resource_limit_percent=analysis.resource_limit_percent,
        resource_fraction=resource_fraction,
        physical_cpu_count=physical_cpu_count,
        cpu_slots=cpu_slots,
        available_memory_gb=round(available_memory_bytes / (1024**3), 2),
        largest_input_mb=round(largest_input_bytes / (1024**2), 2),
        estimated_worker_memory_gb=round(
            estimated_worker_memory_bytes / (1024**3), 2
        ),
        memory_budget_gb=round(memory_budget_bytes / (1024**3), 2),
        memory_slots=memory_slots,
        pending_count=pending_count,
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
    """Run ``executor_fn`` over every item concurrently, keeping every outcome.

    Returns ``(results, errors)``: ``results`` maps each successful item's index
    to its returned value, and ``errors`` maps each failed item's index to the
    exception it raised. One item's failure never cancels the others, so a run
    records per-file success and failure instead of aborting on the first error.
    """
    results: dict[int, object] = {}
    errors: dict[int, Exception] = {}

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
                errors[index] = exc

    return results, errors


def run_hermes_analysis(
    state_manager: StateManager,
    *,
    overwrite: bool = False,
) -> list[FileReference]:
    state = state_manager.get_state()
    analysis = state.analysis
    if not isinstance(analysis, HermesTpx3AnalysisState):
        error = "no valid HERMES analysis is configured"
        _ANALYSIS_LOGGER.error(
            "Cannot run HERMES analysis: {error}",
            event_type="analysis.hermes.invalid_mode",
            error=error,
            measurement_id=state.measurement_info.measurement_id,
            run=state.measurement_info.run,
            expected_analysis_mode="hermes",
            actual_analysis_mode=getattr(analysis, "mode", None),
        )
        raise HermesAnalysisError(error)

    analysis_root = state.environment.analysis_directory.resolved_path
    if analysis_root is None:
        raise HermesAnalysisError(
            "environment.analysis_directory must be set to run HERMES analysis"
        )

    measurement_info = state.measurement_info

    unpacked_files: list[FileReference] = []
    unpacking_results: list[HermesTpx3UnpackingResult] = []
    try:
        if analysis.unpacking is not None:
            raw_data_directory = (
                state.environment.raw_data_directory.resolved_path
            )
            raw_files = resolve_tpx3_files(analysis, raw_data_directory)
            validate_program_and_inputs(analysis, analysis_root, raw_files)
            unpack_overwrite = (
                overwrite or analysis.unpacking.runtime_options.overwrite
            )
            files_to_run: list[FileReference] = []
            # For each file submitted to the pool, remember where its result
            # sits in unpacking_results so a failure can flip it to "failed".
            run_result_positions: list[int] = []
            for raw_file in raw_files:
                already_unpacked = check_previous_unpacked_file(
                    analysis_root, raw_file
                )
                if not unpack_overwrite and already_unpacked:
                    log_skipped_input(analysis_root, raw_file)
                    unpacking_results.append(
                        HermesTpx3UnpackingResult(
                            input_file=raw_file,
                            status="skipped",
                        )
                    )
                else:
                    files_to_run.append(raw_file)
                    run_result_positions.append(len(unpacking_results))
                    unpacking_results.append(
                        HermesTpx3UnpackingResult(
                            input_file=raw_file,
                            status="completed",
                        )
                    )

            failed_count = 0
            if files_to_run:
                worker_count = _calculate_worker_count(
                    analysis, len(files_to_run), _largest_file_bytes(files_to_run)
                )
                completed, errors = _run_parallel(
                    lambda raw_file: execute_unpacker(
                        analysis,
                        analysis_root,
                        raw_file,
                        measurement_info,
                        overwrite=unpack_overwrite,
                    ),
                    files_to_run,
                    worker_count,
                )
                for run_index in errors:
                    unpacking_results[run_result_positions[run_index]] = (
                        HermesTpx3UnpackingResult(
                            input_file=files_to_run[run_index],
                            status="failed",
                        )
                    )
                failed_count = len(errors)
                unpacked_files = [files_to_run[i] for i in sorted(completed)]
                if analysis.unpacking.runtime_options.delete_raw_after_unpack:
                    _delete_raw_files(unpacked_files)

            _apply_unpacking_results(
                state_manager,
                unpacking_results,
                justification=(
                    "unpacked new raw TPX3 files; revalidated existing outputs"
                ),
            )
            log_overall_completion(
                raw_file_count=len(raw_files),
                unpacked_file_count=len(unpacked_files),
                failed_file_count=failed_count,
            )

        current_analysis = _current_hermes_analysis(state_manager)
        if current_analysis.photon_reconstruction is not None:
            _run_photon_reconstruction(
                state_manager,
                current_analysis,
                analysis_root,
                measurement_info,
                overwrite=overwrite,
            )

        current_analysis = _current_hermes_analysis(state_manager)
        if current_analysis.event_reconstruction is not None:
            _run_event_reconstruction(
                state_manager, current_analysis, analysis_root, overwrite=overwrite
            )

        return unpacked_files
    except HermesTpx3Error as exc:
        # This handles a whole-stage stop, not a single file failing to unpack:
        # a per-file execution failure is now recorded "failed" and the run
        # continues. A missing executable or input, or a prior summary that is
        # invalid or has partial output, still stops the stage here. A file
        # already unpacked on a previous run stays "skipped"; the files this run
        # attempted are marked failed. If the stop came before any file was
        # examined, fall back to marking every raw file.
        if unpacking_results:
            results = [
                result
                if result.status == "skipped"
                else HermesTpx3UnpackingResult(
                    input_file=result.input_file,
                    status="failed",
                )
                for result in unpacking_results
            ]
        else:
            results = [
                HermesTpx3UnpackingResult(input_file=raw_file, status="failed")
                for raw_file in _unpacking_inputs(state_manager)
            ]
        if results:
            _apply_unpacking_results(
                state_manager,
                results,
                justification=f"TPX3 SPIDR unpacking failed: {exc}",
            )
        log_overall_failure(exc)
        raise


def _delete_raw_files(raw_files: list[FileReference]) -> None:
    """Delete each raw file after a successful unpack (best-effort, never raises).

    Only called for files this run unpacked without error, when the run opted in
    with ``delete_raw_after_unpack``. A file that cannot be deleted is logged and
    left in place.
    """
    for raw_file in raw_files:
        try:
            raw_file.path.unlink()
        except OSError as exc:
            _ANALYSIS_LOGGER.warning(
                "Could not delete raw file {raw_tpx3_file} after unpacking: {error}",
                event_type="analysis.tpx3_unpacking.raw_delete_failed",
                raw_tpx3_file=str(raw_file.path),
                error=str(exc),
            )
        else:
            _ANALYSIS_LOGGER.info(
                "Deleted raw file {raw_tpx3_file} after successful unpacking",
                event_type="analysis.tpx3_unpacking.raw_deleted",
                raw_tpx3_file=str(raw_file.path),
            )


def _unpacking_inputs(state_manager: StateManager) -> list[FileReference]:
    """Best-effort raw-file list for failure reporting (never raises)."""
    state = state_manager.get_state()
    current_analysis = state.analysis
    if (
        isinstance(current_analysis, HermesTpx3AnalysisState)
        and current_analysis.unpacking is not None
    ):
        raw_data_directory = state.environment.raw_data_directory.resolved_path
        return resolve_tpx3_files(current_analysis, raw_data_directory)
    return []


def _run_photon_reconstruction(
    state_manager: StateManager,
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
    measurement_info: MeasurementInfo,
    *,
    overwrite: bool = False,
) -> None:
    """Reconstruct photons file-by-file in parallel, recording per-file results."""
    reconstruction = analysis.photon_reconstruction
    assert reconstruction is not None
    recon_overwrite = overwrite or reconstruction.runtime_options.overwrite
    files_to_run: list[FileReference] = []
    skipped_results: list[HermesTpx3PhotonReconstructionResult] = []
    try:
        validate_program_and_algorithm(reconstruction)
        pixel_files = resolve_pixel_files(analysis, analysis_root)
        for input_file in pixel_files:
            already_reconstructed = check_previous_reconstructed_file(
                analysis_root, input_file
            )
            if not recon_overwrite and already_reconstructed:
                output_file = derive_output_path(analysis_root, input_file)
                log_reconstruction_skipped(input_file, output_file)
                skipped_results.append(
                    HermesTpx3PhotonReconstructionResult(
                        input_file=input_file,
                        output_file=output_file,
                        status="skipped",
                    )
                )
            else:
                files_to_run.append(input_file)

        run_results: list[HermesTpx3PhotonReconstructionResult] = []
        failed_results: list[HermesTpx3PhotonReconstructionResult] = []
        if files_to_run:
            worker_count = _calculate_worker_count(
                analysis, len(files_to_run), _largest_file_bytes(files_to_run)
            )
            completed, errors = _run_parallel(
                lambda input_file: execute_reconstruction(
                    analysis,
                    analysis_root,
                    input_file,
                    measurement_info,
                    overwrite=recon_overwrite,
                ),
                files_to_run,
                worker_count,
            )
            run_results = [completed[i] for i in sorted(completed)]
            failed_results = [
                HermesTpx3PhotonReconstructionResult(
                    input_file=files_to_run[i],
                    output_file=_best_effort_output_path(
                        analysis_root, files_to_run[i]
                    ),
                    status="failed",
                )
                for i in sorted(errors)
            ]

        _apply_reconstruction_results(
            state_manager,
            skipped_results + run_results + failed_results,
            justification="recorded photon reconstruction results per pixel file",
        )
        log_reconstruction_completion(
            pixel_file_count=len(pixel_files),
            reconstructed_file_count=len(run_results),
            failed_file_count=len(failed_results),
        )
    except HermesPhotonReconstructionError as exc:
        # This handles a whole-stage stop, not a single file failing to
        # reconstruct: a per-file execution failure is now recorded "failed" and
        # the run continues. An unsupported algorithm, a missing executable, or a
        # malformed pixel filename still stops the stage here. Files already
        # reconstructed on a previous run stay "skipped"; the files this run
        # attempted are marked failed. If the stop came before any file was
        # examined, fall back to every reconstruction input.
        if files_to_run or skipped_results:
            failed_inputs = files_to_run
        else:
            failed_inputs = _reconstruction_inputs(analysis, analysis_root)
        failed_results = [
            HermesTpx3PhotonReconstructionResult(
                input_file=input_file,
                output_file=_best_effort_output_path(analysis_root, input_file),
                status="failed",
            )
            for input_file in failed_inputs
        ]
        _apply_reconstruction_results(
            state_manager,
            skipped_results + failed_results,
            justification=f"photon reconstruction failed: {exc}",
        )
        log_reconstruction_failure(exc)
        raise


def _best_effort_output_path(
    analysis_root: Path,
    input_file: FileReference,
) -> Path:
    """Photon output path for failure reporting; never raises on a bad name."""
    try:
        return derive_output_path(analysis_root, input_file)
    except Exception:
        return analysis_root / "photons" / f"{input_file.path.stem}.parquet"


def _reconstruction_inputs(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
) -> list[FileReference]:
    """Best-effort pixel-file list for failure reporting (never raises)."""
    try:
        return resolve_pixel_files(analysis, analysis_root)
    except Exception:
        return []


def _run_event_reconstruction(
    state_manager: StateManager,
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
    *,
    overwrite: bool = False,
) -> None:
    """Reconstruct events per raw stem in parallel, recording per-stem results."""
    event_reconstruction = analysis.event_reconstruction
    assert event_reconstruction is not None
    event_overwrite = overwrite or event_reconstruction.runtime_options.overwrite
    stems_to_run: list[str] = []
    skipped_results: list[HermesTpx3EventReconstructionResult] = []
    try:
        validate_event_program_and_algorithm(event_reconstruction)
        raw_file_stems = resolve_raw_file_stems(analysis, analysis_root)
        for raw_file_stem in raw_file_stems:
            already_reconstructed = check_previous_event_reconstructed_file(
                analysis_root, raw_file_stem
            )
            if not event_overwrite and already_reconstructed:
                output_file = derive_event_output_path(
                    analysis_root, raw_file_stem
                )
                log_event_reconstruction_skipped(raw_file_stem, output_file)
                skipped_results.append(
                    HermesTpx3EventReconstructionResult(
                        raw_file_stem=raw_file_stem,
                        output_file=output_file,
                        status="skipped",
                    )
                )
            else:
                stems_to_run.append(raw_file_stem)

        run_results: list[HermesTpx3EventReconstructionResult] = []
        failed_results: list[HermesTpx3EventReconstructionResult] = []
        if stems_to_run:
            photon_files = [
                FileReference(path=path)
                for path in (analysis_root / "photons").glob("*.parquet")
            ]
            worker_count = _calculate_worker_count(
                analysis, len(stems_to_run), _largest_file_bytes(photon_files)
            )
            completed, errors = _run_parallel(
                lambda raw_file_stem: execute_event_reconstruction(
                    analysis,
                    analysis_root,
                    raw_file_stem,
                    overwrite=event_overwrite,
                ),
                stems_to_run,
                worker_count,
            )
            run_results = [completed[i] for i in sorted(completed)]
            failed_results = [
                HermesTpx3EventReconstructionResult(
                    raw_file_stem=stems_to_run[i],
                    output_file=derive_event_output_path(
                        analysis_root, stems_to_run[i]
                    ),
                    status="failed",
                )
                for i in sorted(errors)
            ]

        _apply_event_reconstruction_results(
            state_manager,
            skipped_results + run_results + failed_results,
            justification="recorded event reconstruction results per raw stem",
        )
        log_event_reconstruction_completion(
            raw_file_stem_count=len(raw_file_stems),
            reconstructed_stem_count=len(run_results),
            failed_stem_count=len(failed_results),
        )
    except HermesEventReconstructionError as exc:
        # This handles a whole-stage stop, not a single stem failing to
        # reconstruct: a per-stem execution failure is now recorded "failed" and
        # the run continues. An unsupported algorithm, a missing executable, or a
        # malformed photon filename still stops the stage here. Stems already
        # reconstructed on a previous run stay "skipped"; the stems this run
        # attempted are marked failed. If the stop came before any stem was
        # examined, fall back to every reconstruction input.
        if stems_to_run or skipped_results:
            failed_stems = stems_to_run
        else:
            failed_stems = _event_reconstruction_inputs(analysis, analysis_root)
        failed_results = [
            HermesTpx3EventReconstructionResult(
                raw_file_stem=raw_file_stem,
                output_file=derive_event_output_path(
                    analysis_root, raw_file_stem
                ),
                status="failed",
            )
            for raw_file_stem in failed_stems
        ]
        _apply_event_reconstruction_results(
            state_manager,
            skipped_results + failed_results,
            justification=f"event reconstruction failed: {exc}",
        )
        log_event_reconstruction_failure(exc)
        raise


def _event_reconstruction_inputs(
    analysis: HermesTpx3AnalysisState,
    analysis_root: Path,
) -> list[str]:
    """Best-effort raw-stem list for failure reporting (never raises)."""
    try:
        return resolve_raw_file_stems(analysis, analysis_root)
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
    results: list[HermesTpx3PhotonReconstructionResult],
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


def _apply_event_reconstruction_results(
    state_manager: StateManager,
    results: list[HermesTpx3EventReconstructionResult],
    *,
    justification: str,
) -> None:
    change = state_manager.propose_change(
        "analysis.event_reconstruction.results",
        results,
        origin="trusted_workflow",
        proposer="tpx3_spidr_event_reconstruction",
        justification=justification,
    )
    state_manager.apply_change(change.change_id)
