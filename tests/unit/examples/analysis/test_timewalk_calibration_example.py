from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3PhotonClusteringSettings,
)
from hermes.state.models.shared_models import FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateIOError
from hermes.state_service.state_io import load_hermes_record_from_yaml


@pytest.fixture
def run_timewalk_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    repository_root = Path(__file__).resolve().parents[4]
    monkeypatch.syspath_prepend(str(repository_root))
    return importlib.import_module(
        "examples.analysis.timewalk_calibration.run_timewalk_calibration"
    )


def test_checked_in_yaml_configures_unpacking_and_clustering(
    run_timewalk_module: ModuleType,
) -> None:
    initial_record = load_hermes_record_from_yaml(
        run_timewalk_module.DEFAULT_INPUT_YAML_PATH
    )

    assert (
        initial_record.measurement_info.measurement_id
        == "example-tpx3-timewalk-calibration"
    )
    assert initial_record.environment.working_directory.path == Path(
        "data/examples/analysis/timewalk_calibration"
    )
    assert isinstance(initial_record.analysis, HermesTpx3AnalysisState)
    assert initial_record.environment.analysis_directory.path == Path("analysis")
    assert initial_record.analysis.unpacking.tpx3_files == [
        FileReference(path=Path("tests/data/tpx3/Example_1kHz_5frames.tpx3"))
    ]
    assert initial_record.analysis.photon_reconstruction is None

    import yaml

    clustering_settings = HermesTpx3PhotonClusteringSettings.model_validate(
        yaml.safe_load(
            run_timewalk_module.CLUSTERING_SETTINGS_YAML_PATH.read_text(
                encoding="utf-8"
            )
        )
    )
    assert clustering_settings.adjacency == 8
    assert clustering_settings.max_time_spread_ticks == 491_520
    assert clustering_settings.min_cluster_size == 2
    assert clustering_settings.max_cluster_size == 64


def test_main_runs_workflow_and_calibrates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run_timewalk_module: ModuleType,
) -> None:
    working_directory = tmp_path / "run"
    analysis_directory = working_directory / "analysis"
    pixel_directory = analysis_directory / "pixel_hits"
    pixel_directory.mkdir(parents=True)
    pixel_file = pixel_directory / "input-chip-0-part-00000.parquet"
    pixel_file.write_bytes(b"pixels")
    raw_tpx3_file = tmp_path / "input.tpx3"
    unpacker_executable = tmp_path / "hermes-tpx3-spidr"
    input_yaml_path = tmp_path / "input.yaml"
    raw_tpx3_file.write_bytes(b"example")
    unpacker_executable.write_text("", encoding="utf-8")
    input_yaml_path.write_text(
        f"""
measurement_info:
  measurement_id: timewalk-test
  run: test-run
environment:
  working_directory: {working_directory}
  analysis_directory: {analysis_directory}
analysis:
  mode: hermes
  unpacking:
    program:
      name: tpx3-spidr-cpp
      executable_path: {unpacker_executable}
    tpx3_files:
      - path: {raw_tpx3_file}
""",
        encoding="utf-8",
    )
    original_input_yaml = input_yaml_path.read_bytes()
    received_records: list[HermesRecord] = []

    class CompletedWorkflow:
        def __init__(self, record: HermesRecord) -> None:
            received_records.append(record.model_copy(deep=True))
            self.record = record

        def run_analysis(self) -> list[FileReference]:
            analysis = self.record.analysis
            assert isinstance(analysis, HermesTpx3AnalysisState)
            return analysis.unpacking.tpx3_files

    calibration_calls: list[dict[str, object]] = []

    def fake_calibrate_timewalk(
        pixel_data_files: list[Path],
        settings: HermesTpx3PhotonClusteringSettings,
        output_file: Path,
        correction_file: Path,
    ) -> SimpleNamespace:
        calibration_calls.append(
            {
                "pixel_data_files": pixel_data_files,
                "settings": settings,
                "output_file": output_file,
                "correction_file": correction_file,
            }
        )
        return SimpleNamespace(
            components_considered=10,
            components_used=6,
            pixel_pairs=42,
            high_tot_anchor=23.0,
            selected_model="inverse",
            selected_parameters={"a": 1.0, "b": 2.0},
            selection_reason="inverse improved held-out RMSE",
            comparison_plot=output_file.with_name(
                f"{output_file.stem}-comparison.png"
            ),
        )

    monkeypatch.setattr(run_timewalk_module, "Workflow", CompletedWorkflow)
    monkeypatch.setattr(
        run_timewalk_module, "calibrate_timewalk", fake_calibrate_timewalk
    )

    run_timewalk_module.main(input_yaml_path)

    final_record_path = working_directory / "hermes-record_final.yaml"
    saved_final_record = load_hermes_record_from_yaml(final_record_path)
    console_output = capsys.readouterr().out

    assert input_yaml_path.read_bytes() == original_input_yaml
    assert final_record_path != input_yaml_path
    assert len(received_records) == 1
    assert saved_final_record.measurement_info.measurement_id == "timewalk-test"

    assert len(calibration_calls) == 1
    call = calibration_calls[0]
    assert call["pixel_data_files"] == [pixel_file]
    assert isinstance(call["settings"], HermesTpx3PhotonClusteringSettings)
    assert call["settings"].adjacency == 8
    assert call["output_file"] == (
        analysis_directory / "logs/timewalk-calibration.json"
    )
    assert call["correction_file"] == (
        analysis_directory / "logs/timewalk-calibration-correction.json"
    )

    assert "Components considered: 10" in console_output
    assert "Components used:       6" in console_output
    assert "Pixel pairs:           42" in console_output
    assert "Selected model:        inverse" in console_output
    assert str(analysis_directory / "logs/timewalk-calibration.json") in (
        console_output
    )
    assert str(final_record_path) in console_output


def test_invalid_yaml_stops_before_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_timewalk_module: ModuleType,
) -> None:
    invalid_yaml_path = tmp_path / "invalid.yaml"
    invalid_yaml_path.write_text("measurement_info: [", encoding="utf-8")

    class UnexpectedWorkflow:
        def __init__(self, record: HermesRecord) -> None:
            raise AssertionError("workflow must not run for invalid YAML")

    def unexpected_calibrate(*args: object, **kwargs: object) -> object:
        raise AssertionError("calibration must not run for invalid YAML")

    monkeypatch.setattr(run_timewalk_module, "Workflow", UnexpectedWorkflow)
    monkeypatch.setattr(
        run_timewalk_module, "calibrate_timewalk", unexpected_calibrate
    )

    with pytest.raises(StateIOError, match="parse"):
        run_timewalk_module.main(invalid_yaml_path)
