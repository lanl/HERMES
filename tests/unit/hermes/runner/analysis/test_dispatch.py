"""Tests for selecting the EMPIR or HERMES analysis runner by mode."""

from __future__ import annotations

from pathlib import Path

import pytest

import hermes.runner.analysis.run as dispatcher
from hermes.runner.analysis.run import AnalysisModeError, run_analysis
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
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3Unpacking,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import BinaryProgram, FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_manager import StateManager


def _manager(tmp_path: Path, analysis: object | None) -> StateManager:
    record = HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id="dispatch-test",
            run_number=1,
        ),
        environment=RuntimeEnvironment(working_dir=tmp_path),
        analysis=analysis,
    )
    return StateManager(
        record,
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )


def _empir_analysis(tmp_path: Path) -> EmpirAnalysisState:
    photon_path = tmp_path / "out/raw.empirphot"
    event_path = tmp_path / "out/raw.empirevent"
    return EmpirAnalysisState(
        pixel_to_photon=EmpirPixelToPhotonState(
            program=BinaryProgram(
                name="empir_pixel2photon_tpx3spidr",
                executable_path=Path("empir_pixel2photon_tpx3spidr"),
            ),
            settings=EmpirPixelToPhotonSettings(
                spatial_distance_pixels=5,
                time_distance_seconds=500e-9,
                minimum_pixel_count=3,
            ),
            runs=[
                EmpirPixelToPhotonRun(
                    input_tpx3_file=FileReference(path=tmp_path / "raw.tpx3"),
                    photon_file=photon_path,
                )
            ],
        ),
        photon_to_event=EmpirPhotonToEventState(
            program=BinaryProgram(
                name="empir_photon2event",
                executable_path=Path("empir_photon2event"),
            ),
            settings=EmpirPhotonToEventSettings(
                spatial_distance_pixels=4,
                time_distance_seconds=100e-6,
                maximum_duration_seconds=500e-6,
            ),
            runs=[
                EmpirPhotonToEventRun(
                    input_photon_file=FileReference(path=photon_path),
                    event_file=event_path,
                )
            ],
        ),
        event_to_image=EmpirEventToImageState(
            program=BinaryProgram(
                name="empir_event2image",
                executable_path=Path("empir_event2image"),
            ),
            settings=EmpirEventToImageSettings(image_width_pixels=512),
            input_event_files=[FileReference(path=event_path)],
            tiff_file=tmp_path / "out/final.tiff",
        ),
    )


def _hermes_analysis(tmp_path: Path) -> HermesTpx3AnalysisState:
    return HermesTpx3AnalysisState(
        analysis_directory=tmp_path / "analysis",
        unpacking=Tpx3Unpacking(
            program=BinaryProgram(
                name="test-unpacker",
                executable_path=tmp_path / "test-unpacker",
            ),
            tpx3_files=[FileReference(path=tmp_path / "input.tpx3")],
        ),
    )


def test_run_analysis_routes_empir_mode_to_empir_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(tmp_path, _empir_analysis(tmp_path))
    calls: list[str] = []

    def fake_empir(state_manager: StateManager) -> list[FileReference]:
        calls.append("empir")
        return [FileReference(path=tmp_path / "out/final.tiff")]

    def fake_hermes(*args: object, **kwargs: object) -> list[FileReference]:
        calls.append("hermes")
        return []

    monkeypatch.setattr(dispatcher, "run_empir_analysis", fake_empir)
    monkeypatch.setattr(dispatcher, "run_hermes_analysis", fake_hermes)

    result = run_analysis(manager, overwrite=True)

    assert calls == ["empir"]
    assert result == [FileReference(path=tmp_path / "out/final.tiff")]


def test_run_analysis_routes_hermes_mode_and_passes_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(tmp_path, _hermes_analysis(tmp_path))
    seen_overwrite: list[bool] = []

    def fake_empir(state_manager: StateManager) -> list[FileReference]:
        raise AssertionError("EMPIR runner must not run for HERMES mode")

    def fake_hermes(
        state_manager: StateManager,
        *,
        overwrite: bool = False,
    ) -> list[FileReference]:
        seen_overwrite.append(overwrite)
        return []

    monkeypatch.setattr(dispatcher, "run_empir_analysis", fake_empir)
    monkeypatch.setattr(dispatcher, "run_hermes_analysis", fake_hermes)

    run_analysis(manager, overwrite=True)

    assert seen_overwrite == [True]


def test_run_analysis_rejects_missing_analysis(tmp_path: Path) -> None:
    manager = _manager(tmp_path, None)

    with pytest.raises(AnalysisModeError, match="no valid analysis mode"):
        run_analysis(manager)
