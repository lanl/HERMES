"""Tests for coordinating a complete EMPIR analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from loguru import logger

from hermes.runner.analysis.empir._errors import (
    EmpirExecutionError,
    EmpirPreflightError,
)
from hermes.runner.analysis.empir.run import run_empir_analysis
from hermes.state.models.analysis.empir import (
    EmpirAnalysisState,
    EmpirEventToImageSettings,
    EmpirEventToImageState,
    EmpirPhotonToEventRun,
    EmpirPhotonToEventSettings,
    EmpirPhotonToEventState,
    EmpirPixelToPhotonRun,
    EmpirPixelToPhotonSettings,
    EmpirPixelToPhotonState,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import BinaryProgram, FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.change_requests import ChangeRequest
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_manager import StateManager
from _fake_program import write_fake_empir_program


class CapturingStateLogger:
    """Capture StateManager writes without touching the JSONL logger."""

    def __init__(self) -> None:
        self.changes: list[ChangeRequest] = []
        self.initial_records: list[HermesRecord] = []
        self.validation_failures: list[dict[str, Any]] = []

    def log_initial_state(self, record: HermesRecord) -> None:
        self.initial_records.append(record.model_copy(deep=True))

    def log_change(self, change_request: ChangeRequest) -> None:
        self.changes.append(change_request.model_copy(deep=True))

    def log_validation_failure(
        self,
        path: str,
        error: str,
        *,
        change_id: str | None = None,
        proposed_value: Any = None,
    ) -> None:
        self.validation_failures.append(
            {
                "path": path,
                "error": error,
                "change_id": change_id,
                "proposed_value": proposed_value,
            }
        )


def _record(tmp_path: Path, analysis: EmpirAnalysisState) -> HermesRecord:
    return HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id="empir-test",
            run_number=1,
        ),
        environment=RuntimeEnvironment(working_dir=tmp_path),
        analysis=analysis,
    )


def _manager(
    tmp_path: Path,
    analysis: EmpirAnalysisState,
) -> tuple[StateManager, CapturingStateLogger]:
    state_logger = CapturingStateLogger()
    manager = StateManager(
        _record(tmp_path, analysis),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=state_logger,
    )
    return manager, state_logger


def _install_fake_programs(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "pixel": tmp_path / "bin/empir_pixel2photon_tpx3spidr",
        "photon": tmp_path / "bin/empir_photon2event",
        "image": tmp_path / "bin/empir_event2image",
    }
    for executable in paths.values():
        write_fake_empir_program(executable)
    return paths


def _analysis(
    tmp_path: Path,
    executables: dict[str, Path],
    *,
    raw_modes: list[str] | None = None,
    save_photon_files: bool = False,
    save_event_files: bool = False,
) -> EmpirAnalysisState:
    modes = raw_modes or ["success"]
    photon_runs = []
    event_files = []
    pixel_runs = []
    for index, mode in enumerate(modes, start=1):
        raw_path = tmp_path / f"raw-{index}.tpx3"
        photon_path = tmp_path / f"out/raw-{index}.empirphot"
        event_path = tmp_path / f"out/raw-{index}.empirevent"
        raw_path.write_text(mode, encoding="utf-8")
        pixel_runs.append(
            EmpirPixelToPhotonRun(
                tpx3_file=FileReference(path=raw_path),
                photon_file=photon_path,
            )
        )
        photon_runs.append(
            EmpirPhotonToEventRun(
                photon_file=FileReference(path=photon_path),
                event_file=event_path,
            )
        )
        event_files.append(FileReference(path=event_path))

    return EmpirAnalysisState(
        save_photon_files=save_photon_files,
        save_event_files=save_event_files,
        pixel_to_photon=EmpirPixelToPhotonState(
            program=BinaryProgram(
                name="empir-pixel2photon",
                executable_path=executables["pixel"],
            ),
            settings=EmpirPixelToPhotonSettings(
                spatial_distance_pixels=5,
                time_distance_seconds=500e-9,
                minimum_pixel_count=3,
            ),
            runs=pixel_runs,
        ),
        photon_to_event=EmpirPhotonToEventState(
            program=BinaryProgram(
                name="empir-photon2event",
                executable_path=executables["photon"],
            ),
            settings=EmpirPhotonToEventSettings(
                spatial_distance_pixels=4,
                time_distance_seconds=100e-6,
                maximum_duration_seconds=500e-6,
            ),
            runs=photon_runs,
        ),
        event_to_image=EmpirEventToImageState(
            program=BinaryProgram(
                name="empir-event2image",
                executable_path=executables["image"],
            ),
            settings=EmpirEventToImageSettings(image_width_pixels=512),
            event_files=event_files,
            tiff_file=tmp_path / "out/final.tiff",
        ),
    )


def test_run_empir_analysis_completes_and_removes_intermediates(
    tmp_path: Path,
) -> None:
    """Run all three programs and save completed results in StateManager."""
    executables = _install_fake_programs(tmp_path)
    initial_analysis = _analysis(tmp_path, executables)
    manager, state_logger = _manager(tmp_path, initial_analysis)
    records: list[dict[str, object]] = []
    sink_id = logger.add(lambda message: records.append(message.record))

    try:
        files = run_empir_analysis(manager)
    finally:
        logger.remove(sink_id)

    assert files == [FileReference(path=tmp_path / "out/final.tiff")]
    current = manager.get_state().analysis
    assert isinstance(current, EmpirAnalysisState)
    assert current.pixel_to_photon.runs[0].result.status == "completed"
    assert current.photon_to_event.runs[0].result.status == "completed"
    assert current.event_to_image.result.status == "completed"
    assert current.pixel_to_photon.runs[0].command_args[0] == "-i"
    assert current.photon_to_event.runs[0].photon_file.path.exists() is False
    assert current.event_to_image.event_files[0].path.exists() is False
    assert initial_analysis.pixel_to_photon.runs[0].result.status == "planned"
    assert [change.status for change in state_logger.changes].count("applied") == 6
    event_types = [
        record["extra"].get("event_type")
        for record in records
        if str(record["extra"].get("event_type", "")).startswith(
            "analysis.empir.pipeline."
        )
    ]
    assert event_types == [
        "analysis.empir.pipeline.started",
        "analysis.empir.pipeline.completed",
    ]


def test_run_empir_analysis_processes_file_runs_in_order(
    tmp_path: Path,
) -> None:
    """Complete each pixel run before moving to photon-to-event runs."""
    executables = _install_fake_programs(tmp_path)
    manager, state_logger = _manager(
        tmp_path,
        _analysis(tmp_path, executables, raw_modes=["success", "success"]),
    )

    run_empir_analysis(manager)

    applied_paths = [
        change.path for change in state_logger.changes if change.status == "applied"
    ]
    assert applied_paths == [
        "analysis.pixel_to_photon.runs",
        "analysis.pixel_to_photon.runs",
        "analysis.pixel_to_photon.runs",
        "analysis.pixel_to_photon.runs",
        "analysis.photon_to_event.runs",
        "analysis.photon_to_event.runs",
        "analysis.photon_to_event.runs",
        "analysis.photon_to_event.runs",
        "analysis.event_to_image",
        "analysis.event_to_image",
    ]


def test_run_empir_analysis_stops_after_first_failed_process(
    tmp_path: Path,
) -> None:
    """Mark only the attempted run failed and leave downstream steps planned."""
    executables = _install_fake_programs(tmp_path)
    manager, _state_logger = _manager(
        tmp_path,
        _analysis(tmp_path, executables, raw_modes=["success", "nonzero"]),
    )

    with pytest.raises(EmpirExecutionError, match="exited with code 7"):
        run_empir_analysis(manager)

    current = manager.get_state().analysis
    assert isinstance(current, EmpirAnalysisState)
    assert current.pixel_to_photon.runs[0].result.status == "completed"
    assert current.pixel_to_photon.runs[1].result.status == "failed"
    assert current.pixel_to_photon.runs[1].command_args[0] == "-i"
    assert current.photon_to_event.runs[0].result.status == "planned"
    assert current.event_to_image.result.status == "planned"


def test_run_empir_analysis_rejects_preflight_without_state_changes(
    tmp_path: Path,
) -> None:
    """Reject existing outputs before any running result is saved."""
    executables = _install_fake_programs(tmp_path)
    analysis = _analysis(tmp_path, executables)
    analysis.pixel_to_photon.runs[0].photon_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    analysis.pixel_to_photon.runs[0].photon_file.write_text(
        "already here",
        encoding="utf-8",
    )
    manager, state_logger = _manager(tmp_path, analysis)

    with pytest.raises(EmpirPreflightError, match="output already exists"):
        run_empir_analysis(manager)

    assert [change.status for change in state_logger.changes] == []
    current = manager.get_state().analysis
    assert isinstance(current, EmpirAnalysisState)
    assert current.pixel_to_photon.runs[0].result.status == "planned"


def test_run_empir_analysis_wraps_missing_executable_as_preflight_error(
    tmp_path: Path,
) -> None:
    """Report missing EMPIR programs before any run status is saved."""
    executables = _install_fake_programs(tmp_path)
    executables["pixel"] = tmp_path / "bin/missing-pixel"
    manager, state_logger = _manager(tmp_path, _analysis(tmp_path, executables))

    with pytest.raises(EmpirPreflightError, match="not a file"):
        run_empir_analysis(manager)

    assert [change.status for change in state_logger.changes] == []
    current = manager.get_state().analysis
    assert isinstance(current, EmpirAnalysisState)
    assert current.pixel_to_photon.runs[0].result.status == "planned"


def test_run_empir_analysis_retains_photon_after_downstream_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep photon inputs when photon-to-event fails."""
    executables = _install_fake_programs(tmp_path)
    manager, _state_logger = _manager(tmp_path, _analysis(tmp_path, executables))

    def fail_photon_to_event(*_args: object, **_kwargs: object) -> None:
        raise EmpirPreflightError("forced photon failure")

    monkeypatch.setattr(
        "hermes.runner.analysis.empir.run.execute_photon_to_event",
        fail_photon_to_event,
    )

    with pytest.raises(EmpirPreflightError, match="forced photon failure"):
        run_empir_analysis(manager)

    current = manager.get_state().analysis
    assert isinstance(current, EmpirAnalysisState)
    assert current.photon_to_event.runs[0].photon_file.path.is_file()
    assert current.photon_to_event.runs[0].result.status == "failed"
    assert current.event_to_image.result.status == "planned"


def test_run_empir_analysis_keeps_intermediates_when_configured(
    tmp_path: Path,
) -> None:
    """Honor save settings after downstream steps succeed."""
    executables = _install_fake_programs(tmp_path)
    manager, _state_logger = _manager(
        tmp_path,
        _analysis(
            tmp_path,
            executables,
            save_photon_files=True,
            save_event_files=True,
        ),
    )

    run_empir_analysis(manager)

    current = manager.get_state().analysis
    assert isinstance(current, EmpirAnalysisState)
    assert current.photon_to_event.runs[0].photon_file.path.is_file()
    assert current.event_to_image.event_files[0].path.is_file()
