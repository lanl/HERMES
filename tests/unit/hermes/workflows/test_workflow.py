from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3UnpackingResult,
    Tpx3Unpacking,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import BinaryProgram, FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.state_manager import StateManager
from hermes.workflows.workflow import Workflow


def _record(tmp_path: Path) -> HermesRecord:
    return HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id="workflow-test",
            run="test-run",
        ),
        environment=RuntimeEnvironment(
            working_directory=tmp_path,
            analysis_directory=tmp_path / "analysis",
        ),
        analysis=HermesTpx3AnalysisState(
            unpacking=Tpx3Unpacking(
                program=BinaryProgram(
                    name="test-unpacker",
                    executable_path=tmp_path / "test-unpacker",
                ),
                tpx3_files=[FileReference(path=tmp_path / "input.tpx3")],
            ),
        ),
    )


def test_run_analysis_returns_files_and_updates_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_record = _record(tmp_path)
    workflow = Workflow(initial_record)

    def complete_analysis(
        state_manager: StateManager,
        *,
        overwrite: bool = False,
    ) -> list[FileReference]:
        assert overwrite is True
        analysis = state_manager.get_state().analysis
        assert isinstance(analysis, HermesTpx3AnalysisState)
        change = state_manager.propose_change(
            "analysis.unpacking.results",
            [
                HermesTpx3UnpackingResult(
                    input_file=raw_file,
                    status="completed",
                )
                for raw_file in analysis.unpacking.tpx3_files
            ],
            origin="trusted_workflow",
            proposer="test_analysis",
        )
        state_manager.apply_change(change.change_id)

        return analysis.unpacking.tpx3_files

    monkeypatch.setattr(
        "hermes.workflows.workflow.run_analysis",
        complete_analysis,
    )

    unpacked_files = workflow.run_analysis(overwrite=True)

    assert unpacked_files == initial_record.analysis.unpacking.tpx3_files
    updated_results = workflow.record.analysis.unpacking.results
    assert [result.status for result in updated_results] == ["completed"]
    assert initial_record.analysis.unpacking.results == []


def test_run_acquisition_is_unimplemented_and_leaves_record_unchanged(
    tmp_path: Path,
) -> None:
    initial_record = _record(tmp_path)
    workflow = Workflow(initial_record)

    with pytest.raises(NotImplementedError, match="not implemented"):
        workflow.run_acquisition()

    assert workflow.record == initial_record


def test_run_dispatches_to_analysis_when_only_analysis_is_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_record = _record(tmp_path)
    workflow = Workflow(initial_record)
    calls: list[str] = []

    def complete_analysis(
        state_manager: StateManager,
        *,
        overwrite: bool = False,
    ) -> list[FileReference]:
        calls.append("analysis")
        analysis = state_manager.get_state().analysis
        assert isinstance(analysis, HermesTpx3AnalysisState)
        return analysis.unpacking.tpx3_files

    monkeypatch.setattr(
        "hermes.workflows.workflow.run_analysis",
        complete_analysis,
    )

    returned_record = workflow.run()

    assert calls == ["analysis"]
    assert returned_record == workflow.record


def test_run_writes_the_workflow_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_record = _record(tmp_path)
    workflow = Workflow(initial_record)

    def complete_analysis(
        state_manager: StateManager,
        *,
        overwrite: bool = False,
    ) -> list[FileReference]:
        analysis = state_manager.get_state().analysis
        assert isinstance(analysis, HermesTpx3AnalysisState)
        change = state_manager.propose_change(
            "analysis.unpacking.results",
            [
                HermesTpx3UnpackingResult(input_file=raw_file, status="completed")
                for raw_file in analysis.unpacking.tpx3_files
            ],
            origin="trusted_workflow",
            proposer="test_analysis",
        )
        state_manager.apply_change(change.change_id)
        return analysis.unpacking.tpx3_files

    monkeypatch.setattr(
        "hermes.workflows.workflow.run_analysis",
        complete_analysis,
    )

    workflow.run()

    log_file = tmp_path / "HERMES-workflow.jsonl"
    lines = [json.loads(line) for line in log_file.read_text().splitlines()]

    events = [line["event"] for line in lines]
    assert events == [
        "HERMES_record_initialized",
        "workflow_initialized",
        "stage_completed",
        "workflow_completed",
    ]
    assert lines[1]["stages"] == ["unpacking"]
    assert lines[2]["stage"] == "unpacking"
    assert lines[2]["status"] == "success"


def test_run_rejects_a_record_with_nothing_to_run(tmp_path: Path) -> None:
    record = HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id="workflow-test",
            run="test-run",
        ),
        environment=RuntimeEnvironment(
            working_directory=tmp_path,
            analysis_directory=tmp_path / "analysis",
        ),
    )
    workflow = Workflow(record)

    with pytest.raises(ValueError, match="neither acquisition nor analysis"):
        workflow.run()
