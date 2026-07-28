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
    record = load_hermes_record_from_yaml(
        run_unpacker_module.DEFAULT_CONFIG_PATH
    )

    assert record.measurement_info.measurement_id == "example-tpx3-unpacking"
    assert record.environment.working_dir.path == Path(
        "data/examples/analysis/unpacker"
    )
    assert record.acquisition is None
    assert isinstance(record.analysis, HermesTpx3AnalysisState)
    assert record.analysis.unpacker_program.executable_path == Path(
        "build/backends/tpx3-spidr/hermes-tpx3-spidr"
    )
    assert record.analysis.analysis_directory == Path(
        "data/examples/analysis/unpacker/analysis"
    )
    assert record.analysis.tpx3_files[0].path == Path(
        "tests/data/Example_1kHz_5frames.tpx3"
    )
    assert record.analysis.resource_limit_percent == 90
    assert record.analysis.unpacker_program.version is None
    assert record.analysis.photon_reconstruction is None
    assert record.analysis.results.unpacking.status == "planned"
    assert record.analysis.results.reconstruction is None

    raw_file = record.analysis.tpx3_files[0]
    assert raw_file.media_type is None
    assert raw_file.sha256 is None
    assert raw_file.size_bytes is None
    assert raw_file.created_at is None
    assert raw_file.description is None


def test_invalid_yaml_stops_before_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_unpacker_module: ModuleType,
) -> None:
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text("measurement_info: [", encoding="utf-8")

    def fail_if_called(state_manager: StateManager) -> list[FileReference]:
        raise AssertionError("analysis must not run for invalid YAML")

    monkeypatch.setattr(
        run_unpacker_module,
        "run_hermes_analysis",
        fail_if_called,
    )

    with pytest.raises(StateIOError, match="parse"):
        run_unpacker_module.main(config_path)


def test_main_preserves_input_and_saves_final_record_separately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run_unpacker_module: ModuleType,
) -> None:
    working_dir = tmp_path / "run"
    analysis_directory = working_dir / "analysis"
    raw_file = tmp_path / "input.tpx3"
    executable = tmp_path / "hermes-tpx3-spidr"
    config_path = tmp_path / "input.yaml"
    raw_file.write_bytes(b"example")
    executable.write_text("", encoding="utf-8")
    config_path.write_text(
        f"""
measurement_info:
  measurement_id: yaml-example
  run_number: 1
environment:
  working_dir: {working_dir}
analysis:
  mode: hermes
  unpacker_program:
    name: tpx3-spidr-cpp
    executable_path: {executable}
  analysis_directory: {analysis_directory}
  tpx3_files:
    - path: {raw_file}
""",
        encoding="utf-8",
    )
    original_input = config_path.read_bytes()

    def run_without_subprocess(
        state_manager: StateManager,
    ) -> list[FileReference]:
        state = state_manager.get_state()
        assert isinstance(state.analysis, HermesTpx3AnalysisState)
        return state.analysis.tpx3_files

    monkeypatch.setattr(
        run_unpacker_module,
        "run_hermes_analysis",
        run_without_subprocess,
    )

    run_unpacker_module.main(config_path)

    state_path = working_dir / "hermes-record.yaml"
    saved_record = load_hermes_record_from_yaml(state_path)
    output = capsys.readouterr().out

    assert config_path.read_bytes() == original_input
    assert state_path != config_path
    assert saved_record.measurement_info.measurement_id == "yaml-example"
    assert isinstance(saved_record.analysis, HermesTpx3AnalysisState)
    assert saved_record.analysis.resource_limit_percent == 90
    assert str(raw_file) in output
    assert str(analysis_directory) in output
    assert str(state_path) in output
