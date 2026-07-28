from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
)
from hermes.state.models.shared_models import FileReference
from hermes.state_service.shared_types import StateIOError
from hermes.state_service.state_io import load_hermes_record_from_yaml
from hermes.state_service.state_manager import StateManager


@pytest.fixture
def run_unpacker_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    repository_root = Path(__file__).resolve().parents[4]
    monkeypatch.syspath_prepend(str(repository_root))
    return importlib.import_module(
        "examples.analysis.unpacker_single_file.run_unpacker"
    )


def test_checked_in_partial_yaml_loads_with_expected_defaults(
    run_unpacker_module: ModuleType,
) -> None:
    initial_record = load_hermes_record_from_yaml(
        run_unpacker_module.DEFAULT_INPUT_YAML_PATH
    )

    assert (
        initial_record.measurement_info.measurement_id
        == "example-tpx3-unpacking"
    )
    assert initial_record.environment.working_dir.path == Path(
        "data/examples/analysis/unpacker"
    )
    assert initial_record.acquisition is None
    assert isinstance(initial_record.analysis, HermesTpx3AnalysisState)
    assert initial_record.analysis.unpacker_program.executable_path == Path(
        "build/backends/tpx3-spidr/hermes-tpx3-spidr"
    )
    assert initial_record.analysis.analysis_directory == Path(
        "data/examples/analysis/unpacker/analysis"
    )
    assert initial_record.analysis.tpx3_files[0].path == Path(
        "tests/data/Example_1kHz_5frames.tpx3"
    )
    assert initial_record.analysis.resource_limit_percent == 90
    assert initial_record.analysis.unpacker_program.version is None
    assert initial_record.analysis.photon_reconstruction is None
    assert initial_record.analysis.results.unpacking.status == "planned"
    assert initial_record.analysis.results.reconstruction is None

    raw_tpx3_file = initial_record.analysis.tpx3_files[0]
    assert raw_tpx3_file.media_type is None
    assert raw_tpx3_file.sha256 is None
    assert raw_tpx3_file.size_bytes is None
    assert raw_tpx3_file.created_at is None
    assert raw_tpx3_file.description is None


def test_invalid_yaml_stops_before_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_unpacker_module: ModuleType,
) -> None:
    invalid_yaml_path = tmp_path / "invalid.yaml"
    invalid_yaml_path.write_text("measurement_info: [", encoding="utf-8")

    def fail_if_called(state_manager: StateManager) -> list[FileReference]:
        raise AssertionError("analysis must not run for invalid YAML")

    monkeypatch.setattr(
        run_unpacker_module,
        "run_hermes_analysis",
        fail_if_called,
    )

    with pytest.raises(StateIOError, match="parse"):
        run_unpacker_module.main(invalid_yaml_path)


def test_main_preserves_input_and_saves_final_record_separately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run_unpacker_module: ModuleType,
) -> None:
    working_directory = tmp_path / "run"
    analysis_directory = working_directory / "analysis"
    raw_tpx3_file = tmp_path / "input.tpx3"
    unpacker_executable = tmp_path / "hermes-tpx3-spidr"
    input_yaml_path = tmp_path / "input.yaml"
    raw_tpx3_file.write_bytes(b"example")
    unpacker_executable.write_text("", encoding="utf-8")
    input_yaml_path.write_text(
        f"""
measurement_info:
  measurement_id: yaml-example
  run_number: 1
environment:
  working_dir: {working_directory}
analysis:
  mode: hermes
  unpacker_program:
    name: tpx3-spidr-cpp
    executable_path: {unpacker_executable}
  analysis_directory: {analysis_directory}
  tpx3_files:
    - path: {raw_tpx3_file}
""",
        encoding="utf-8",
    )
    original_input_yaml = input_yaml_path.read_bytes()

    def run_without_subprocess(
        state_manager: StateManager,
    ) -> list[FileReference]:
        current_record = state_manager.get_state()
        assert isinstance(current_record.analysis, HermesTpx3AnalysisState)
        return current_record.analysis.tpx3_files

    monkeypatch.setattr(
        run_unpacker_module,
        "run_hermes_analysis",
        run_without_subprocess,
    )

    run_unpacker_module.main(input_yaml_path)

    final_record_path = working_directory / "hermes-record_final.yaml"
    saved_final_record = load_hermes_record_from_yaml(final_record_path)
    console_output = capsys.readouterr().out

    assert input_yaml_path.read_bytes() == original_input_yaml
    assert final_record_path != input_yaml_path
    assert (
        saved_final_record.measurement_info.measurement_id
        == "yaml-example"
    )
    assert isinstance(saved_final_record.analysis, HermesTpx3AnalysisState)
    assert saved_final_record.analysis.resource_limit_percent == 90
    assert str(raw_tpx3_file) in console_output
    assert "Raw TPX3 files: 1" in console_output
    assert "Unpacked this run: 1" in console_output
    assert "Skipped existing valid outputs: 0" in console_output
    assert str(analysis_directory) in console_output
    assert str(final_record_path) in console_output
