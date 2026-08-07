from __future__ import annotations

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
            run_number=1,
        ),
        environment=RuntimeEnvironment(working_dir=tmp_path),
        analysis=HermesTpx3AnalysisState(
            analysis_directory=tmp_path / "analysis",
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


@pytest.mark.parametrize("method_name", ["run_acquisition", "run"])
def test_unimplemented_workflow_operations_leave_record_unchanged(
    tmp_path: Path,
    method_name: str,
) -> None:
    initial_record = _record(tmp_path)
    workflow = Workflow(initial_record)

    with pytest.raises(NotImplementedError, match="not implemented"):
        getattr(workflow, method_name)()

    assert workflow.record == initial_record
