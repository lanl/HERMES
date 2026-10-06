from __future__ import annotations

import json
from pathlib import Path

import pytest
from loguru import logger

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3EventReconstruction,
    HermesTpx3EventReconstructionResult,
    HermesTpx3EventReconstructionSettings,
    HermesTpx3PhotonClustering,
    HermesTpx3PhotonClusteringSettings,
    HermesTpx3PhotonReconstruction,
    HermesTpx3PhotonReconstructionResult,
    HermesTpx3UnpackingResult,
    Tpx3Unpacking,
)
from hermes.state.models.acquisition.serval import (
    ServalAcquisitionConfig,
    ServalAcquisitionResult,
    ServalAcquisitionState,
    ServalServer,
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


def _acquisition_record(tmp_path: Path) -> HermesRecord:
    return HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id="workflow-test",
            run="test-run",
        ),
        environment=RuntimeEnvironment(
            working_directory=tmp_path,
            analysis_directory=tmp_path / "analysis",
        ),
        acquisition=ServalAcquisitionState(
            config=ServalAcquisitionConfig(
                serval=ServalServer(url="http://localhost:8080"),
            ),
        ),
    )


def test_run_acquisition_dispatches_to_the_serval_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_record = _acquisition_record(tmp_path)
    workflow = Workflow(initial_record)

    def complete_acquisition(state_manager: StateManager) -> None:
        change = state_manager.propose_change(
            "acquisition.status",
            "completed",
            origin="trusted_workflow",
            proposer="test_acquisition",
        )
        state_manager.apply_change(change.change_id)

    monkeypatch.setattr(
        "hermes.workflows.workflow.run_serval_acquisition",
        complete_acquisition,
    )

    workflow.run_acquisition()

    assert workflow.record.acquisition.status == "completed"
    assert initial_record.acquisition.status == "planned"


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


def test_run_dispatches_to_acquisition_when_only_acquisition_is_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_record = _acquisition_record(tmp_path)
    workflow = Workflow(initial_record)
    calls: list[str] = []

    def complete_acquisition(state_manager: StateManager) -> None:
        calls.append("acquisition")

    monkeypatch.setattr(
        "hermes.workflows.workflow.run_serval_acquisition",
        complete_acquisition,
    )

    returned_record = workflow.run()

    assert calls == ["acquisition"]
    assert returned_record == workflow.record
    assert (tmp_path / "HERMES_record.yaml").exists()


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


def _three_stage_record(tmp_path: Path) -> HermesRecord:
    """A record that configures unpacking, photon, and event reconstruction."""
    clustering = HermesTpx3PhotonClustering(
        settings=HermesTpx3PhotonClusteringSettings(
            max_time_spread_ticks=98304,
            min_cluster_size=2,
            max_cluster_size=64,
            min_pixel_tot_raw=1,
            min_cluster_tot_raw=2,
            max_cluster_tot_raw=500,
            max_aspect_ratio=3.0,
            min_filled_fraction=0.5,
        )
    )
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
            photon_reconstruction=HermesTpx3PhotonReconstruction(
                program=BinaryProgram(
                    name="test-photon-clusterer",
                    executable_path=tmp_path / "test-photon-clusterer",
                ),
                clustering_algorithm=clustering,
            ),
            event_reconstruction=HermesTpx3EventReconstruction(
                program=BinaryProgram(
                    name="test-event-reconstructor",
                    executable_path=tmp_path / "test-event-reconstructor",
                ),
                settings=HermesTpx3EventReconstructionSettings(
                    spatial_link_radius_pixels=2.0,
                    spatial_cells_per_axis=8,
                    max_time_difference_ticks=1000.0,
                    max_event_duration_ticks=10000.0,
                    min_photon_count=1,
                ),
            ),
        ),
    )


def test_run_logs_a_completed_line_for_every_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_record = _three_stage_record(tmp_path)
    workflow = Workflow(initial_record)

    pixel_file = FileReference(
        path=tmp_path
        / "analysis"
        / "pixel_hits"
        / "input_chip_0_pixels_00000.parquet"
    )
    photon_file = tmp_path / "analysis" / "photons" / "input_photon.parquet"
    event_file = tmp_path / "analysis" / "events" / "input_event.parquet"

    def complete_analysis(
        state_manager: StateManager,
        *,
        overwrite: bool = False,
    ) -> list[FileReference]:
        analysis = state_manager.get_state().analysis
        assert isinstance(analysis, HermesTpx3AnalysisState)
        for path, results in (
            (
                "analysis.unpacking.results",
                [
                    HermesTpx3UnpackingResult(
                        input_file=analysis.unpacking.tpx3_files[0],
                        status="completed",
                    )
                ],
            ),
            (
                "analysis.photon_reconstruction.results",
                [
                    HermesTpx3PhotonReconstructionResult(
                        input_file=pixel_file,
                        output_file=photon_file,
                        status="completed",
                    )
                ],
            ),
            (
                "analysis.event_reconstruction.results",
                [
                    HermesTpx3EventReconstructionResult(
                        raw_file_stem="input",
                        output_file=event_file,
                        status="skipped",
                    )
                ],
            ),
        ):
            change = state_manager.propose_change(
                path,
                results,
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

    assert [line["event"] for line in lines] == [
        "HERMES_record_initialized",
        "workflow_initialized",
        "stage_completed",
        "stage_completed",
        "stage_completed",
        "workflow_completed",
    ]
    assert lines[1]["stages"] == [
        "unpacking",
        "reconstruction",
        "event_reconstruction",
    ]
    completed = [line for line in lines if line["event"] == "stage_completed"]
    assert [line["stage"] for line in completed] == [
        "unpacking",
        "reconstruction",
        "event_reconstruction",
    ]
    # The skipped event-reconstruction result keeps its status; a completed
    # result maps to "success".
    assert [line["status"] for line in completed] == [
        "success",
        "success",
        "skipped",
    ]


def test_run_records_then_analyzes_when_both_are_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record(tmp_path).model_copy(
        update={
            "acquisition": ServalAcquisitionState(
                config=ServalAcquisitionConfig(
                    serval=ServalServer(url="http://localhost:8080"),
                ),
            )
        }
    )
    workflow = Workflow(record)
    calls: list[str] = []

    monkeypatch.setattr(
        "hermes.workflows.workflow.run_serval_acquisition",
        lambda _state_manager: calls.append("acquisition"),
    )

    def complete_analysis(
        state_manager: StateManager,
        *,
        overwrite: bool = False,
    ) -> list[FileReference]:
        calls.append("analysis")
        return []

    monkeypatch.setattr(
        "hermes.workflows.workflow.run_analysis",
        complete_analysis,
    )

    workflow.run()

    # Acquisition runs first (unpacking as frames land); then a final catch-up
    # analysis pass. Configuring both no longer raises.
    assert calls == ["acquisition", "analysis"]

    log_file = tmp_path / "HERMES-workflow.jsonl"
    lines = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert lines[1]["stages"] == ["acquisition", "unpacking"]


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


def test_run_saves_the_record_and_log_when_ctrl_c_stops_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = Workflow(_acquisition_record(tmp_path))

    def interrupted_acquisition(state_manager: StateManager) -> None:
        change = state_manager.propose_change(
            "acquisition.status",
            "stopped",
            origin="trusted_workflow",
            proposer="test_acquisition",
        )
        state_manager.apply_change(change.change_id)
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "hermes.workflows.workflow.run_serval_acquisition",
        interrupted_acquisition,
    )

    with pytest.raises(KeyboardInterrupt):
        workflow.run()

    record_text = (tmp_path / "HERMES_record.yaml").read_text()
    assert "status: stopped" in record_text
    log_file = tmp_path / "HERMES-workflow.jsonl"
    lines = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert [line["event"] for line in lines] == [
        "HERMES_record_initialized",
        "workflow_initialized",
        "stage_completed",
        "workflow_stopped",
    ]
    assert lines[2]["stage"] == "acquisition"
    assert lines[2]["status"] == "stopped"


def test_run_saves_the_record_and_log_when_an_error_ends_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = Workflow(_acquisition_record(tmp_path))

    def failing_acquisition(_state_manager: StateManager) -> None:
        raise RuntimeError("SERVAL went away")

    monkeypatch.setattr(
        "hermes.workflows.workflow.run_serval_acquisition",
        failing_acquisition,
    )

    with pytest.raises(RuntimeError, match="SERVAL went away"):
        workflow.run()

    assert (tmp_path / "HERMES_record.yaml").exists()
    log_file = tmp_path / "HERMES-workflow.jsonl"
    lines = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert lines[-1]["event"] == "workflow_failed"
    assert lines[-1]["error"] == "RuntimeError: SERVAL went away"
    # The acquisition ended before it recorded a status.
    assert lines[2]["stage"] == "acquisition"
    assert lines[2]["status"] == "planned"



def _set(state_manager: StateManager, path: str, value: object) -> None:
    change = state_manager.propose_change(
        path, value, origin="trusted_workflow", proposer="test"
    )
    state_manager.apply_change(change.change_id)


def _complete_unpacking(status: str):
    """A fake analysis that records every raw file with the given status."""

    def complete_analysis(
        state_manager: StateManager,
        *,
        overwrite: bool = False,
    ) -> list[FileReference]:
        analysis = state_manager.get_state().analysis
        _set(
            state_manager,
            "analysis.unpacking.results",
            [
                HermesTpx3UnpackingResult(input_file=raw_file, status=status)
                for raw_file in analysis.unpacking.tpx3_files
            ],
        )
        return analysis.unpacking.tpx3_files

    return complete_analysis


def test_run_logs_a_completed_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = Workflow(_acquisition_record(tmp_path))

    def complete_acquisition(state_manager: StateManager) -> None:
        _set(
            state_manager,
            "acquisition.result",
            ServalAcquisitionResult(
                stop_reason="completed", frames=6, dropped_frames=0
            ),
        )
        _set(state_manager, "acquisition.status", "completed")

    monkeypatch.setattr(
        "hermes.workflows.workflow.run_serval_acquisition",
        complete_acquisition,
    )

    workflow.run()

    log_file = tmp_path / "HERMES-workflow.jsonl"
    lines = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert [line["event"] for line in lines] == [
        "HERMES_record_initialized",
        "workflow_initialized",
        "stage_completed",
        "workflow_completed",
    ]
    acquisition_line = lines[2]
    assert acquisition_line["stage"] == "acquisition"
    assert acquisition_line["status"] == "success"
    assert acquisition_line["stop_reason"] == "completed"
    assert acquisition_line["frames"] == 6
    assert acquisition_line["dropped_frames"] == 0
    assert acquisition_line["errors"] == []


def test_run_logs_no_times_for_an_acquisition_that_took_no_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = Workflow(_acquisition_record(tmp_path))

    def connect_only_acquisition(state_manager: StateManager) -> None:
        _set(state_manager, "acquisition.status", "completed")

    monkeypatch.setattr(
        "hermes.workflows.workflow.run_serval_acquisition",
        connect_only_acquisition,
    )

    workflow.run()

    log_file = tmp_path / "HERMES-workflow.jsonl"
    lines = [json.loads(line) for line in log_file.read_text().splitlines()]
    acquisition_line = lines[2]
    assert acquisition_line["stage"] == "acquisition"
    assert acquisition_line["status"] == "success"
    assert acquisition_line["start"] is None
    assert acquisition_line["stop"] is None
    assert acquisition_line["stop_reason"] is None
    assert acquisition_line["frames"] is None


def test_run_analyzes_and_fails_the_log_after_a_failed_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record(tmp_path).model_copy(
        update={"acquisition": _acquisition_record(tmp_path).acquisition}
    )
    workflow = Workflow(record)

    def timed_out_acquisition(state_manager: StateManager) -> None:
        _set(
            state_manager,
            "acquisition.result",
            ServalAcquisitionResult(
                stop_reason="stopped_after_timeout",
                frames=4,
                dropped_frames=1,
                errors=["the camera did not finish"],
            ),
        )
        _set(state_manager, "acquisition.status", "failed")

    monkeypatch.setattr(
        "hermes.workflows.workflow.run_serval_acquisition",
        timed_out_acquisition,
    )
    monkeypatch.setattr(
        "hermes.workflows.workflow.run_analysis",
        _complete_unpacking("completed"),
    )

    records: list[dict] = []
    sink_id = logger.add(lambda message: records.append(message.record))
    try:
        workflow.run()
    finally:
        logger.remove(sink_id)

    # The raw files the failed acquisition wrote are still unpacked, with a
    # warning that they may be incomplete.
    assert [
        result.status for result in workflow.record.analysis.unpacking.results
    ] == ["completed"]
    warnings = [
        record
        for record in records
        if record["extra"].get("event_type")
        == "workflow.analysis_after_failed_acquisition"
    ]
    assert len(warnings) == 1
    assert warnings[0]["level"].name == "WARNING"
    assert warnings[0]["extra"]["stop_reason"] == "stopped_after_timeout"

    log_file = tmp_path / "HERMES-workflow.jsonl"
    lines = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert [line["event"] for line in lines] == [
        "HERMES_record_initialized",
        "workflow_initialized",
        "stage_completed",
        "stage_completed",
        "workflow_failed",
    ]
    acquisition_line = lines[2]
    assert acquisition_line["stage"] == "acquisition"
    assert acquisition_line["status"] == "failed"
    assert acquisition_line["stop_reason"] == "stopped_after_timeout"
    assert acquisition_line["frames"] == 4
    assert acquisition_line["dropped_frames"] == 1
    assert acquisition_line["errors"] == ["the camera did not finish"]
    assert lines[3]["stage"] == "unpacking"
    assert lines[3]["status"] == "success"
    assert lines[-1]["failed_stages"] == ["acquisition"]
    assert "error" not in lines[-1]


def test_run_fails_the_log_when_an_analysis_file_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = Workflow(_record(tmp_path))
    monkeypatch.setattr(
        "hermes.workflows.workflow.run_analysis",
        _complete_unpacking("failed"),
    )

    workflow.run()

    log_file = tmp_path / "HERMES-workflow.jsonl"
    lines = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert lines[2]["status"] == "failed"
    assert lines[-1]["event"] == "workflow_failed"
    assert lines[-1]["failed_stages"] == ["unpacking"]
