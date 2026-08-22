"""Coordinate the three EMPIR programs for one analysis run."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from hermes.runner.analysis.empir._errors import (
    EmpirError,
    EmpirExecutionError,
    EmpirNotInstalledError,
    EmpirPreflightError,
)
from hermes.runner.analysis.executables import resolve_executable
from hermes.runner.analysis.empir.event_to_image import (
    build_event_to_image_command,
    execute_event_to_image,
)
from hermes.runner.analysis.empir.photon_to_event import (
    build_photon_to_event_command,
    execute_photon_to_event,
)
from hermes.runner.analysis.empir.pixel_to_photon import (
    build_pixel_to_photon_command,
    execute_pixel_to_photon,
)
from hermes.state.models.analysis.empir import (
    EmpirAnalysisState,
    EmpirEventToImageResult,
    EmpirEventToImageState,
    EmpirPhotonToEventResult,
    EmpirPhotonToEventRun,
    EmpirPixelToPhotonResult,
    EmpirPixelToPhotonRun,
)
from hermes.state.models.shared_models import FileReference
from hermes.state_service.state_manager import StateManager

_ANALYSIS_LOGGER = logger.bind(
    domain="analysis",
    mode="empir",
    step="pipeline",
)


def run_empir_analysis(state_manager: StateManager) -> list[FileReference]:
    """Run pixel-to-photon, photon-to-event, and event-to-image in order."""
    try:
        analysis = _current_empir_analysis(state_manager)
        resolved = _preflight(analysis)

        _ANALYSIS_LOGGER.info(
            "EMPIR analysis started",
            event_type="analysis.empir.pipeline.started",
            pixel_to_photon_run_count=len(analysis.pixel_to_photon.runs),
            photon_to_event_run_count=len(analysis.photon_to_event.runs),
            event_to_image_input_count=len(analysis.event_to_image.event_files),
            pixel_to_photon_executable=str(resolved.pixel_to_photon),
            photon_to_event_executable=str(resolved.photon_to_event),
            event_to_image_executable=str(resolved.event_to_image),
        )

        for index in range(len(analysis.pixel_to_photon.runs)):
            current = _current_empir_analysis(state_manager)
            stage = current.pixel_to_photon
            current_run = stage.runs[index]
            command = build_pixel_to_photon_command(
                stage, current_run, resolved.pixel_to_photon
            )
            if current_run.photon_file.exists():
                _log_skipped("pixel_to_photon", current_run.photon_file)
                result = EmpirPixelToPhotonResult(
                    status="skipped",
                    photon_file=FileReference(path=current_run.photon_file),
                )
            else:
                try:
                    result = execute_pixel_to_photon(
                        stage, current_run, resolved.pixel_to_photon
                    )
                except EmpirError as exc:
                    _apply_pixel_failure(
                        state_manager, index, current_run, command[1:], exc
                    )
                    raise
            _apply_pixel_to_photon_run(
                state_manager,
                index,
                current_run.model_copy(
                    update={"command_args": command[1:], "result": result}
                ),
                justification="EMPIR pixel-to-photon done",
            )

        for index in range(len(analysis.photon_to_event.runs)):
            current = _current_empir_analysis(state_manager)
            stage = current.photon_to_event
            current_run = stage.runs[index]
            command = build_photon_to_event_command(
                stage, current_run, resolved.photon_to_event
            )
            if current_run.event_file.exists():
                _log_skipped("photon_to_event", current_run.event_file)
                result = EmpirPhotonToEventResult(
                    status="skipped",
                    event_file=FileReference(path=current_run.event_file),
                )
            else:
                try:
                    result = execute_photon_to_event(
                        stage, current_run, resolved.photon_to_event
                    )
                except EmpirError as exc:
                    _apply_photon_failure(
                        state_manager, index, current_run, command[1:], exc
                    )
                    raise
            _apply_photon_to_event_run(
                state_manager,
                index,
                current_run.model_copy(
                    update={"command_args": command[1:], "result": result}
                ),
                justification="EMPIR photon-to-event done",
            )
            _remove_intermediate(
                current_run.photon_file.path,
                keep=analysis.save_photon_files,
                step_name="photon_to_event",
            )

        current = _current_empir_analysis(state_manager)
        stage = current.event_to_image
        command = build_event_to_image_command(stage, resolved.event_to_image)
        if stage.tiff_file.exists():
            _log_skipped("event_to_image", stage.tiff_file)
            result = EmpirEventToImageResult(
                status="skipped",
                tiff_file=FileReference(path=stage.tiff_file),
            )
        else:
            try:
                result = execute_event_to_image(stage, resolved.event_to_image)
            except EmpirError as exc:
                _apply_event_failure(state_manager, stage, command[1:], exc)
                raise
        completed_stage = stage.model_copy(
            update={"command_args": command[1:], "result": result}
        )
        _apply_event_to_image_state(
            state_manager,
            completed_stage,
            justification="EMPIR event-to-image done",
        )
        for event_file in stage.event_files:
            _remove_intermediate(
                event_file.path,
                keep=analysis.save_event_files,
                step_name="event_to_image",
            )

    except EmpirNotInstalledError as exc:
        _ANALYSIS_LOGGER.warning(
            "EMPIR is not installed: {error}",
            event_type="analysis.empir.not_installed",
            error=str(exc),
        )
        raise
    except EmpirError as exc:
        _ANALYSIS_LOGGER.error(
            "EMPIR analysis failed: {error}",
            event_type="analysis.empir.pipeline.failed",
            error=str(exc),
        )
        raise

    final_file = result.tiff_file
    assert final_file is not None
    _ANALYSIS_LOGGER.info(
        "EMPIR analysis completed",
        event_type="analysis.empir.pipeline.completed",
        output_file=str(final_file.path),
    )
    return [final_file]


class _ResolvedExecutables:
    def __init__(
        self,
        *,
        pixel_to_photon: Path,
        photon_to_event: Path,
        event_to_image: Path,
    ) -> None:
        self.pixel_to_photon = pixel_to_photon
        self.photon_to_event = photon_to_event
        self.event_to_image = event_to_image


def _preflight(analysis: EmpirAnalysisState) -> _ResolvedExecutables:
    """Check the whole EMPIR run before the first state update."""
    try:
        validated = EmpirAnalysisState.model_validate(
            analysis.model_dump(mode="python")
        )
    except ValueError as exc:
        raise EmpirPreflightError(
            f"EMPIR analysis settings are invalid: {exc}"
        ) from exc

    resolved = _ResolvedExecutables(
        pixel_to_photon=_resolve_step_executable(
            validated.pixel_to_photon.program.executable_path
        ),
        photon_to_event=_resolve_step_executable(
            validated.photon_to_event.program.executable_path
        ),
        event_to_image=_resolve_step_executable(
            validated.event_to_image.program.executable_path
        ),
    )
    _validate_initial_inputs(validated)
    _validate_path_collisions(validated)
    _prepare_output_parents(validated)
    return resolved


def _resolve_step_executable(configured_path: Path) -> Path:
    try:
        return resolve_executable(configured_path)
    except (FileNotFoundError, PermissionError) as exc:
        expanded = configured_path.expanduser()
        names_a_program = not expanded.is_absolute() and expanded.parent == Path(".")
        if names_a_program and isinstance(exc, FileNotFoundError):
            # A bare program name that is not on PATH means EMPIR is not
            # installed. An explicit path that is broken is a misconfiguration,
            # so that keeps the ordinary preflight error.
            raise EmpirNotInstalledError(
                f"EMPIR is not installed or not on PATH: {configured_path}. "
                "HERMES can control EMPIR but does not install it. Install "
                "EMPIR and make its programs available on PATH, then re-run."
            ) from exc
        raise EmpirPreflightError(str(exc)) from exc


def _validate_initial_inputs(analysis: EmpirAnalysisState) -> None:
    for run in analysis.pixel_to_photon.runs:
        path = run.tpx3_file.path
        if not path.is_file():
            raise EmpirPreflightError(
                f"pixel_to_photon input is not a regular file: {path}"
            )


def _validate_path_collisions(analysis: EmpirAnalysisState) -> None:
    input_paths = [run.tpx3_file.path for run in analysis.pixel_to_photon.runs]
    output_paths = [
        *(run.photon_file for run in analysis.pixel_to_photon.runs),
        *(run.event_file for run in analysis.photon_to_event.runs),
        analysis.event_to_image.tiff_file,
    ]
    all_paths = input_paths + output_paths
    normalized = [_normalized_path(path) for path in all_paths]
    if len(set(normalized)) != len(normalized):
        raise EmpirPreflightError("EMPIR input and output paths must be unique")


def _prepare_output_parents(analysis: EmpirAnalysisState) -> None:
    output_paths = [
        *(run.photon_file for run in analysis.pixel_to_photon.runs),
        *(run.event_file for run in analysis.photon_to_event.runs),
        analysis.event_to_image.tiff_file,
    ]
    for output_path in output_paths:
        parent = output_path.parent
        if parent.exists() and not parent.is_dir():
            raise EmpirPreflightError(
                f"EMPIR output parent is not a directory: {parent}"
            )
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise EmpirPreflightError(
                f"EMPIR output parent cannot be created: {parent}"
            ) from exc


def _normalized_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _current_empir_analysis(state_manager: StateManager) -> EmpirAnalysisState:
    analysis = state_manager.get_state().analysis
    if not isinstance(analysis, EmpirAnalysisState):
        actual_mode = getattr(analysis, "mode", None)
        raise EmpirPreflightError(
            f"no valid EMPIR analysis is configured: {actual_mode}"
        )
    return analysis


def _apply_pixel_to_photon_run(
    state_manager: StateManager,
    index: int,
    updated_run: EmpirPixelToPhotonRun,
    *,
    justification: str,
) -> None:
    analysis = _current_empir_analysis(state_manager)
    runs = list(analysis.pixel_to_photon.runs)
    runs[index] = updated_run
    _apply_change(
        state_manager,
        "analysis.pixel_to_photon.runs",
        runs,
        proposer="empir_pixel_to_photon",
        justification=justification,
    )


def _apply_photon_to_event_run(
    state_manager: StateManager,
    index: int,
    updated_run: EmpirPhotonToEventRun,
    *,
    justification: str,
) -> None:
    analysis = _current_empir_analysis(state_manager)
    runs = list(analysis.photon_to_event.runs)
    runs[index] = updated_run
    _apply_change(
        state_manager,
        "analysis.photon_to_event.runs",
        runs,
        proposer="empir_photon_to_event",
        justification=justification,
    )


def _apply_event_to_image_state(
    state_manager: StateManager,
    updated_state: EmpirEventToImageState,
    *,
    justification: str,
) -> None:
    _apply_change(
        state_manager,
        "analysis.event_to_image",
        updated_state,
        proposer="empir_event_to_image",
        justification=justification,
    )


def _apply_pixel_failure(
    state_manager: StateManager,
    index: int,
    run: EmpirPixelToPhotonRun,
    command_args: list[str],
    error: EmpirError,
) -> None:
    result = EmpirPixelToPhotonResult(status="failed", errors=[str(error)])
    if isinstance(error, EmpirExecutionError):
        result = EmpirPixelToPhotonResult(
            status="failed",
            elapsed_seconds=error.outcome.elapsed_seconds,
            exit_code=error.outcome.exit_code,
            errors=[str(error)],
        )
    _apply_pixel_to_photon_run(
        state_manager,
        index,
        run.model_copy(update={"command_args": command_args, "result": result}),
        justification=f"EMPIR pixel-to-photon failed: {error}",
    )


def _apply_photon_failure(
    state_manager: StateManager,
    index: int,
    run: EmpirPhotonToEventRun,
    command_args: list[str],
    error: EmpirError,
) -> None:
    result = EmpirPhotonToEventResult(status="failed", errors=[str(error)])
    if isinstance(error, EmpirExecutionError):
        result = EmpirPhotonToEventResult(
            status="failed",
            elapsed_seconds=error.outcome.elapsed_seconds,
            exit_code=error.outcome.exit_code,
            errors=[str(error)],
        )
    _apply_photon_to_event_run(
        state_manager,
        index,
        run.model_copy(update={"command_args": command_args, "result": result}),
        justification=f"EMPIR photon-to-event failed: {error}",
    )


def _apply_event_failure(
    state_manager: StateManager,
    stage: EmpirEventToImageState,
    command_args: list[str],
    error: EmpirError,
) -> None:
    result = EmpirEventToImageResult(status="failed", errors=[str(error)])
    if isinstance(error, EmpirExecutionError):
        result = EmpirEventToImageResult(
            status="failed",
            elapsed_seconds=error.outcome.elapsed_seconds,
            exit_code=error.outcome.exit_code,
            errors=[str(error)],
        )
    _apply_event_to_image_state(
        state_manager,
        stage.model_copy(update={"command_args": command_args, "result": result}),
        justification=f"EMPIR event-to-image failed: {error}",
    )


def _log_skipped(step_name: str, output_path: Path) -> None:
    _ANALYSIS_LOGGER.info(
        "EMPIR {step} skipped: output already exists at {path}",
        event_type=f"analysis.empir.{step_name}.skipped",
        step=step_name,
        path=str(output_path),
    )


def _remove_intermediate(path: Path, *, keep: bool, step_name: str) -> None:
    if keep:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        _ANALYSIS_LOGGER.warning(
            "EMPIR intermediate cleanup failed: {error}",
            event_type="analysis.empir.cleanup.failed",
            step=step_name,
            path=str(path),
            error=str(exc),
        )


def _apply_change(
    state_manager: StateManager,
    path: str,
    value: object,
    *,
    proposer: str,
    justification: str,
) -> None:
    change = state_manager.propose_change(
        path,
        value,
        origin="trusted_workflow",
        proposer=proposer,
        justification=justification,
    )
    state_manager.apply_change(change.change_id)
