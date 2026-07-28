from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisResults,
    HermesTpx3AnalysisState,
    HermesTpx3ReconstructionResult,
    HermesTpx3UnpackingResult,
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
    assert initial_record.environment.working_dir.path == Path(
        "data/examples/analysis/two_stage"
    )
    assert isinstance(initial_record.analysis, HermesTpx3AnalysisState)

    analysis = initial_record.analysis
    assert analysis.unpacker_program.name == "tpx3-spidr-cpp"
    assert analysis.unpacker_program.executable_path == Path(
        "build/backends/tpx3-spidr/hermes-tpx3-spidr"
    )
    assert analysis.analysis_directory == Path(
        "data/examples/analysis/two_stage/analysis"
    )
    assert analysis.tpx3_files == [
        FileReference(path=Path("tests/data/Example_1kHz_5frames.tpx3"))
    ]

    reconstruction = analysis.photon_reconstruction
    assert reconstruction is not None
    assert reconstruction.program.name == "photon-clusterer-cpp"
    assert reconstruction.program.executable_path == Path(
        "build/backends/photon-clusterer/hermes-photon-clusterer"
    )
    assert reconstruction.clustering_algorithm == "connected_components"
    assert reconstruction.pixel_data_directory == (
        analysis.analysis_directory / "pixelHits"
    )
    assert reconstruction.photon_output_directory == (
        analysis.analysis_directory / "photons"
    )
    assert reconstruction.settings.timewalk_calibration_file == Path(
        "calibrations/tpx3/time-walk_example.json"
    )
    assert reconstruction.settings.save_photon_pixels is True


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
  run_number: 1
environment:
  working_dir: {working_directory}
analysis:
  mode: hermes
  unpacker_program:
    name: test-unpacker
    executable_path: {tmp_path / "test-unpacker"}
  analysis_directory: {analysis_directory}
  tpx3_files:
    - path: {first_raw_file}
    - path: {second_raw_file}
  photon_reconstruction:
    program:
      name: test-clusterer
      executable_path: {tmp_path / "test-clusterer"}
    pixel_data_directory: {analysis_directory / "pixelHits"}
    photon_output_directory: {photon_directory}
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
            completed_analysis = analysis.model_copy(
                update={
                    "results": HermesTpx3AnalysisResults(
                        unpacking=HermesTpx3UnpackingResult(status="completed"),
                        reconstruction=HermesTpx3ReconstructionResult(
                            status="completed",
                            photon_count=3,
                            rejected_count=2,
                        ),
                    )
                }
            )
            self.record = record.model_copy(
                update={"analysis": completed_analysis}
            )

        def run_analysis(self) -> list[FileReference]:
            analysis = self.record.analysis
            assert isinstance(analysis, HermesTpx3AnalysisState)
            return analysis.tpx3_files

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
    assert [raw_file.path for raw_file in received_analysis.tpx3_files] == [
        first_raw_file,
        second_raw_file,
    ]
    assert received_analysis.photon_reconstruction is not None

    assert isinstance(saved_final_record.analysis, HermesTpx3AnalysisState)
    assert saved_final_record.analysis.results.unpacking.status == "completed"
    assert (
        saved_final_record.analysis.results.reconstruction is not None
    )
    assert (
        saved_final_record.analysis.results.reconstruction.status
        == "completed"
    )

    assert str(first_raw_file) in console_output
    assert str(second_raw_file) in console_output
    assert "Raw TPX3 files: 2" in console_output
    assert "Unpacked this run: 2" in console_output
    assert "Skipped existing valid unpacking output: 0" in console_output
    assert "Photon reconstruction status: completed" in console_output
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
