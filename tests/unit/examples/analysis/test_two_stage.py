from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3PhotonReconstructionResult,
    HermesTpx3UnpackingResult,
    HermesTpx3PhotonQualityFlagCountsSummary,
    HermesTpx3PhotonRejectionCountsSummary,
    HermesTpx3PhotonReconstructionCountsSummary,
)
from hermes.state.models.shared_models import FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateIOError
from hermes.state_service.state_io import load_hermes_record_from_yaml


@pytest.fixture
def run_two_stage_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    repository_root = Path(__file__).resolve().parents[4]
    monkeypatch.syspath_prepend(str(repository_root))
    return importlib.import_module("examples.analysis.two_stage.run_two_stage")


def test_checked_in_yaml_configures_both_analysis_stages(
    run_two_stage_module: ModuleType,
) -> None:
    initial_record = load_hermes_record_from_yaml(
        run_two_stage_module.DEFAULT_INPUT_YAML_PATH
    )

    assert (
        initial_record.measurement_info.measurement_id
        == "example-tpx3-two-stage-analysis"
    )
    assert initial_record.environment.working_directory.path == Path(
        "data/examples/analysis/two_stage"
    )
    assert isinstance(initial_record.analysis, HermesTpx3AnalysisState)

    analysis = initial_record.analysis
    assert analysis.unpacking.program.name == "tpx3-spidr-cpp"
    assert analysis.unpacking.program.executable_path == Path(
        "build/backends/tpx3-spidr/hermes-tpx3-spidr"
    )
    assert initial_record.environment.analysis_directory.path == Path("analysis")
    assert analysis.unpacking.tpx3_files == [
        FileReference(path=Path("tests/data/Example_1kHz_5frames.tpx3"))
    ]

    reconstruction = analysis.photon_reconstruction
    assert reconstruction is not None
    assert reconstruction.program.name == "photon-clusterer-cpp"
    assert reconstruction.program.executable_path == Path(
        "build/backends/photon-clusterer/hermes-photon-clusterer"
    )
    assert reconstruction.clustering_algorithm.name == "connected_components"
    assert reconstruction.pixel_files == "auto"
    assert (
        reconstruction.clustering_algorithm.settings.timewalk_calibration_file
        == Path("calibrations/tpx3/time-walk_example.json")
    )
    assert reconstruction.clustering_algorithm.save_photon_pixels is True


def test_main_runs_two_files_and_saves_final_record_separately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run_two_stage_module: ModuleType,
) -> None:
    working_directory = tmp_path / "run"
    analysis_directory = working_directory / "analysis"
    photon_directory = analysis_directory / "photons"
    first_raw_file = tmp_path / "first.tpx3"
    second_raw_file = tmp_path / "second.tpx3"
    input_yaml_path = tmp_path / "input.yaml"
    first_raw_file.write_bytes(b"first")
    second_raw_file.write_bytes(b"second")
    input_yaml_path.write_text(
        f"""
measurement_info:
  measurement_id: two-stage-test
  run: test-run
environment:
  working_directory: {working_directory}
  analysis_directory: {analysis_directory}
analysis:
  mode: hermes
  unpacking:
    program:
      name: test-unpacker
      executable_path: {tmp_path / "test-unpacker"}
    tpx3_files:
      - path: {first_raw_file}
      - path: {second_raw_file}
  photon_reconstruction:
    program:
      name: test-clusterer
      executable_path: {tmp_path / "test-clusterer"}
    pixel_files: auto
    clustering_algorithm:
      name: connected_components
      settings:
        max_time_spread_ticks: 100
        min_cluster_size: 2
        max_cluster_size: 10
        min_pixel_tot_raw: 1
        min_cluster_tot_raw: 2
        max_cluster_tot_raw: 100
        max_aspect_ratio: 2.0
        min_filled_fraction: 0.5
""",
        encoding="utf-8",
    )
    original_input_yaml = input_yaml_path.read_bytes()
    received_records: list[HermesRecord] = []

    class CompletedWorkflow:
        def __init__(self, record: HermesRecord) -> None:
            received_records.append(record.model_copy(deep=True))
            analysis = record.analysis
            assert isinstance(analysis, HermesTpx3AnalysisState)
            tpx3_files = analysis.unpacking.tpx3_files
            counts = HermesTpx3PhotonReconstructionCountsSummary(
                pixel_rows_read=10,
                pixel_rows_below_min_tot=0,
                components_formed=5,
                photon_count=3,
                rejected_component_count=2,
                rejection_counts=HermesTpx3PhotonRejectionCountsSummary(
                    below_min_cluster_size=0,
                    above_max_cluster_size=0,
                    below_min_cluster_tot=0,
                    above_max_cluster_tot=0,
                    above_max_aspect_ratio=0,
                    below_min_filled_fraction=0,
                ),
                quality_flag_counts=HermesTpx3PhotonQualityFlagCountsSummary(
                    saturated_pixel=0,
                    bridged_components=0,
                ),
                warnings=[],
                errors=[],
            )
            completed_unpacking = analysis.unpacking.model_copy(
                update={
                    "results": [
                        HermesTpx3UnpackingResult(
                            input_file=raw_file,
                            status="completed",
                        )
                        for raw_file in tpx3_files
                    ]
                }
            )
            assert analysis.photon_reconstruction is not None
            completed_reconstruction = analysis.photon_reconstruction.model_copy(
                update={
                    "results": [
                        HermesTpx3PhotonReconstructionResult(
                            input_file=tpx3_files[0],
                            output_file=photon_directory / "photons.parquet",
                            status="completed",
                            counts=counts,
                        )
                    ]
                }
            )
            completed_analysis = analysis.model_copy(
                update={
                    "unpacking": completed_unpacking,
                    "photon_reconstruction": completed_reconstruction,
                }
            )
            self.record = record.model_copy(
                update={"analysis": completed_analysis}
            )

        def run_analysis(self) -> list[FileReference]:
            analysis = self.record.analysis
            assert isinstance(analysis, HermesTpx3AnalysisState)
            return analysis.unpacking.tpx3_files

    monkeypatch.setattr(run_two_stage_module, "Workflow", CompletedWorkflow)

    run_two_stage_module.main(input_yaml_path)

    final_record_path = working_directory / "hermes-record_final.yaml"
    saved_final_record = load_hermes_record_from_yaml(final_record_path)
    console_output = capsys.readouterr().out

    assert input_yaml_path.read_bytes() == original_input_yaml
    assert final_record_path != input_yaml_path
    assert len(received_records) == 1
    received_analysis = received_records[0].analysis
    assert isinstance(received_analysis, HermesTpx3AnalysisState)
    assert [
        raw_file.path for raw_file in received_analysis.unpacking.tpx3_files
    ] == [
        first_raw_file,
        second_raw_file,
    ]
    assert received_analysis.photon_reconstruction is not None

    assert isinstance(saved_final_record.analysis, HermesTpx3AnalysisState)
    unpacking_results = saved_final_record.analysis.unpacking.results
    assert [result.status for result in unpacking_results] == [
        "completed",
        "completed",
    ]
    reconstruction = saved_final_record.analysis.photon_reconstruction
    assert reconstruction is not None
    assert reconstruction.results[0].status == "completed"

    assert str(first_raw_file) in console_output
    assert str(second_raw_file) in console_output
    assert "Raw TPX3 files: 2" in console_output
    assert "Unpacked this run: 2" in console_output
    assert "Skipped existing valid unpacking output: 0" in console_output
    assert "Reconstructed photon files this run: 1" in console_output
    assert "Photons: 3" in console_output
    assert "Rejected clusters: 2" in console_output
    assert str(analysis_directory) in console_output
    assert str(photon_directory) in console_output
    assert str(final_record_path) in console_output


def test_invalid_yaml_stops_before_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_two_stage_module: ModuleType,
) -> None:
    invalid_yaml_path = tmp_path / "invalid.yaml"
    invalid_yaml_path.write_text("measurement_info: [", encoding="utf-8")

    class UnexpectedWorkflow:
        def __init__(self, record: HermesRecord) -> None:
            raise AssertionError("workflow must not run for invalid YAML")

    monkeypatch.setattr(run_two_stage_module, "Workflow", UnexpectedWorkflow)

    with pytest.raises(StateIOError, match="parse"):
        run_two_stage_module.main(invalid_yaml_path)
