from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from hermes.state.models.acquisition.serval import (
    ServalAcquisitionResult,
    ServalAcquisitionState,
    ServalEnvironment,
)
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateIOError
from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)


NOW = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)
PARTIAL_HERMES_ANALYSIS_YAML = """
measurement_info:
  measurement_id: example-tpx3-unpacking
  run: test-run
environment:
  working_directory: data/examples/analysis/unpacker
  analysis_directory: analysis
analysis:
  mode: hermes
  unpacking:
    program:
      name: tpx3-spidr-cpp
      executable_path: build/backends/tpx3-spidr/hermes-tpx3-spidr
    tpx3_files:
      - path: tests/data/tpx3/Example_1kHz_5frames.tpx3
"""


def _example_record(tmp_path: Path) -> HermesRecord:
    raw_file = FileReference(
        path=tmp_path / "run-001/data/raw.tpx3",
        media_type="application/octet-stream",
        created_at=NOW,
    )
    return HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id="LC-20260505",
            run="test-run",
            beamline="DCS",
        ),
        environment=RuntimeEnvironment(
            working_directory=tmp_path / "run-001",
            raw_data_directory="data",
            log_directory="logs",
        ),
        acquisition=ServalAcquisitionState(
            serval_environment=ServalEnvironment(serval_url="http://localhost:8080"),
            result=ServalAcquisitionResult(
                status="completed",
                started_at=NOW,
                completed_at=NOW,
                output_files=[raw_file],
            )
        ),
    )


def test_save_and_load_hermes_record_yaml_round_trip(tmp_path: Path) -> None:
    record = _example_record(tmp_path)
    record_path = tmp_path / "run-001/logs/hermes-record.final.yaml"

    written_path = save_hermes_record_to_yaml(record, record_path)
    loaded = load_hermes_record_from_yaml(written_path)

    assert written_path == record_path
    assert loaded == record
    assert loaded.measurement_info.measurement_id == "LC-20260505"
    assert loaded.acquisition is not None
    assert loaded.acquisition.result is not None
    assert loaded.acquisition.result.status == "completed"
    assert loaded.acquisition.result.started_at == NOW
    assert loaded.acquisition.result.output_files[0].created_at == NOW
    assert loaded.analysis is None


def test_save_hermes_record_yaml_is_readable_and_uses_pythonic_names(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / "nested/logs/hermes-record.initial.yaml"

    save_hermes_record_to_yaml(_example_record(tmp_path), record_path)

    content = record_path.read_text(encoding="utf-8")
    loaded_yaml = yaml.safe_load(content)
    assert loaded_yaml["measurement_info"]["measurement_id"] == "LC-20260505"
    assert loaded_yaml["environment"]["working_directory"][
        "resolved_path"
    ].endswith("run-001")
    assert loaded_yaml["acquisition"]["mode"] == "serval"
    assert loaded_yaml["analysis"] is None
    assert "measurement_info:" in content
    assert "acquisition:" in content
    assert "&id" not in content
    assert "*id" not in content


def test_load_partial_yaml_applies_record_and_environment_defaults(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / "minimal-record.yaml"
    record_path.write_text(
        """
measurement_info:
  measurement_id: example-run
  run: test-run
environment: {}
""",
        encoding="utf-8",
    )

    loaded = load_hermes_record_from_yaml(record_path)

    assert isinstance(loaded, HermesRecord)
    assert loaded.acquisition is None
    assert loaded.analysis is None
    assert loaded.environment.working_directory.path == Path.cwd()
    assert loaded.environment.working_directory.required is True
    assert (
        loaded.environment.working_directory.resolved_path == Path.cwd().resolve()
    )
    assert loaded.environment.run_directory.path is None
    assert loaded.environment.run_directory.required is False
    assert loaded.environment.run_directory.resolved_path is None
    assert loaded.environment.allow_overlapping_output_dirs is False


def test_load_partial_hermes_analysis_yaml_applies_nested_defaults(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / "partial-analysis.yaml"
    record_path.write_text(PARTIAL_HERMES_ANALYSIS_YAML, encoding="utf-8")

    loaded = load_hermes_record_from_yaml(record_path)

    assert loaded.acquisition is None
    assert isinstance(loaded.analysis, HermesTpx3AnalysisState)
    assert loaded.analysis.resource_limit_percent == 90
    assert loaded.analysis.unpacking.program.version is None
    assert loaded.analysis.photon_reconstruction is None
    assert loaded.analysis.unpacking.results == []

    raw_file = loaded.analysis.unpacking.tpx3_files[0]
    assert raw_file.media_type is None
    assert raw_file.created_at is None
    assert raw_file.description is None


def test_save_partial_loaded_record_writes_defaults_and_round_trips(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "partial-analysis.yaml"
    saved_path = tmp_path / "final-record.yaml"
    input_path.write_text(PARTIAL_HERMES_ANALYSIS_YAML, encoding="utf-8")

    loaded = load_hermes_record_from_yaml(input_path)
    save_hermes_record_to_yaml(loaded, saved_path)
    saved_yaml = yaml.safe_load(saved_path.read_text(encoding="utf-8"))
    reloaded = load_hermes_record_from_yaml(saved_path)

    assert saved_yaml["acquisition"] is None
    assert saved_yaml["analysis"]["resource_limit_percent"] == 90
    assert saved_yaml["analysis"]["unpacking"]["program"]["version"] is None
    assert saved_yaml["analysis"]["unpacking"]["results"] == []
    assert (
        saved_yaml["analysis"]["unpacking"]["tpx3_files"][0]["media_type"]
        is None
    )
    assert reloaded == loaded


def test_load_file_list_and_save_expanded_raw_tpx3_files(
    tmp_path: Path,
) -> None:
    file_list_path = tmp_path / "inputs/raw_tpx3_files.txt"
    file_list_path.parent.mkdir()
    file_list_path.write_text(
        "first.tpx3\n# ignored comment\n\nsecond.tpx3\n",
        encoding="utf-8",
    )
    input_yaml_path = tmp_path / "file-list-record.yaml"
    final_record_path = tmp_path / "final-record.yaml"
    input_yaml_path.write_text(
        f"""
measurement_info:
  measurement_id: file-list-run
  run: test-run
environment:
  working_directory: {tmp_path}
  analysis_directory: analysis
analysis:
  mode: hermes
  unpacking:
    program:
      name: tpx3-spidr-cpp
      executable_path: hermes-tpx3-spidr
    tpx3_files:
      file_list: {file_list_path}
""",
        encoding="utf-8",
    )

    loaded = load_hermes_record_from_yaml(input_yaml_path)
    save_hermes_record_to_yaml(loaded, final_record_path)
    saved_yaml = yaml.safe_load(final_record_path.read_text(encoding="utf-8"))
    reloaded = load_hermes_record_from_yaml(final_record_path)

    assert isinstance(loaded.analysis, HermesTpx3AnalysisState)
    assert [
        raw_file.path for raw_file in loaded.analysis.unpacking.tpx3_files
    ] == [
        (file_list_path.parent / "first.tpx3").resolve(),
        (file_list_path.parent / "second.tpx3").resolve(),
    ]
    saved_raw_tpx3_files = saved_yaml["analysis"]["unpacking"]["tpx3_files"]
    assert isinstance(saved_raw_tpx3_files, list)
    assert [Path(raw_file["path"]) for raw_file in saved_raw_tpx3_files] == [
        (file_list_path.parent / "first.tpx3").resolve(),
        (file_list_path.parent / "second.tpx3").resolve(),
    ]
    assert reloaded == loaded


def test_load_hermes_record_from_yaml_rejects_invalid_yaml(tmp_path: Path) -> None:
    record_path = tmp_path / "bad.yaml"
    record_path.write_text("measurement_info: [", encoding="utf-8")

    with pytest.raises(StateIOError, match="parse") as exc_info:
        load_hermes_record_from_yaml(record_path)

    assert isinstance(exc_info.value.__cause__, yaml.YAMLError)


def test_load_hermes_record_from_yaml_requires_top_level_mapping(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / "bad.yaml"
    record_path.write_text("- not\n- a\n- record\n", encoding="utf-8")

    with pytest.raises(StateIOError, match="top-level mapping"):
        load_hermes_record_from_yaml(record_path)


def test_load_hermes_record_from_yaml_wraps_validation_errors(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / "invalid-record.yaml"
    record_path.write_text(
        """
measurement_info:
  measurement_id: LC-20260505
environment:
  working_directory: run-001
""",
        encoding="utf-8",
    )

    with pytest.raises(StateIOError, match="validate") as exc_info:
        load_hermes_record_from_yaml(record_path)

    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_load_hermes_record_from_yaml_requires_environment(tmp_path: Path) -> None:
    record_path = tmp_path / "missing-environment.yaml"
    record_path.write_text(
        """
measurement_info:
  measurement_id: LC-20260505
  run: test-run
""",
        encoding="utf-8",
    )

    with pytest.raises(StateIOError, match="validate") as exc_info:
        load_hermes_record_from_yaml(record_path)

    cause = exc_info.value.__cause__
    assert isinstance(cause, ValidationError)
    assert cause.errors()[0]["loc"] == ("environment",)
    assert cause.errors()[0]["type"] == "missing"


@pytest.mark.parametrize(
    ("field", "value", "expected_location", "expected_type"),
    [
        ("unexpected_field", "true", ("unexpected_field",), "extra_forbidden"),
        (
            "run_number",
            "-1",
            ("measurement_info", "run_number"),
            "greater_than_equal",
        ),
    ],
)
def test_load_hermes_record_from_yaml_rejects_unknown_or_invalid_fields(
    tmp_path: Path,
    field: str,
    value: str,
    expected_location: tuple[str, ...],
    expected_type: str,
) -> None:
    record_path = tmp_path / f"{field}.yaml"
    if field == "unexpected_field":
        yaml_content = f"""
measurement_info:
  measurement_id: LC-20260505
  run: test-run
environment: {{}}
{field}: {value}
"""
    else:
        yaml_content = f"""
measurement_info:
  measurement_id: LC-20260505
  run: test-run
  {field}: {value}
environment: {{}}
"""
    record_path.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(StateIOError, match="validate") as exc_info:
        load_hermes_record_from_yaml(record_path)

    cause = exc_info.value.__cause__
    assert isinstance(cause, ValidationError)
    assert cause.errors()[0]["loc"] == expected_location
    assert cause.errors()[0]["type"] == expected_type


def test_load_hermes_record_from_yaml_requires_analysis_mode(tmp_path: Path) -> None:
    record_path = tmp_path / "missing-analysis-mode.yaml"
    record_path.write_text(
        PARTIAL_HERMES_ANALYSIS_YAML.replace("  mode: hermes\n", ""),
        encoding="utf-8",
    )

    with pytest.raises(StateIOError, match="validate") as exc_info:
        load_hermes_record_from_yaml(record_path)

    cause = exc_info.value.__cause__
    assert isinstance(cause, ValidationError)
    assert cause.errors()[0]["loc"] == ("analysis",)
    assert cause.errors()[0]["type"] == "union_tag_not_found"


def test_load_hermes_record_from_yaml_wraps_read_errors(tmp_path: Path) -> None:
    record_path = tmp_path / "missing.yaml"

    with pytest.raises(StateIOError, match="read") as exc_info:
        load_hermes_record_from_yaml(record_path)

    assert isinstance(exc_info.value.__cause__, OSError)
