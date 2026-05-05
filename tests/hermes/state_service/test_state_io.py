from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from hermes.state.models.acquisition.serval import (
    ServalAcquisitionResult,
    ServalAcquisitionState,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import ArtifactRef
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateIOError
from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)


HASH = "a" * 64


def _example_record(tmp_path: Path) -> HermesRecord:
    raw_artifact = ArtifactRef(
        path=tmp_path / "run-001/data/raw.tpx3",
        kind="raw_tpx3",
        media_type="application/octet-stream",
        sha256=HASH,
        size_bytes=2048,
    )
    return HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id="LC-20260505",
            run_number=1,
            beamline="DCS",
        ),
        environment=RuntimeEnvironment(
            working_dir=tmp_path / "run-001",
            raw_data_dir="data",
            log_dir="logs",
        ),
        acquisition=ServalAcquisitionState(
            result=ServalAcquisitionResult(
                status="completed",
                artifacts=[raw_artifact],
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
    assert loaded.analysis is None


def test_save_hermes_record_yaml_is_readable_and_uses_pythonic_names(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / "nested/logs/hermes-record.initial.yaml"

    save_hermes_record_to_yaml(_example_record(tmp_path), record_path)

    content = record_path.read_text(encoding="utf-8")
    loaded_yaml = yaml.safe_load(content)
    assert loaded_yaml["measurement_info"]["measurement_id"] == "LC-20260505"
    assert loaded_yaml["environment"]["working_dir"]["resolved_path"].endswith(
        "run-001"
    )
    assert loaded_yaml["acquisition"]["mode"] == "serval"
    assert loaded_yaml["analysis"] is None
    assert "measurement_info:" in content
    assert "acquisition:" in content
    assert "&id" not in content
    assert "*id" not in content


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
  working_dir: run-001
""",
        encoding="utf-8",
    )

    with pytest.raises(StateIOError, match="validate") as exc_info:
        load_hermes_record_from_yaml(record_path)

    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_load_hermes_record_from_yaml_wraps_read_errors(tmp_path: Path) -> None:
    record_path = tmp_path / "missing.yaml"

    with pytest.raises(StateIOError, match="read") as exc_info:
        load_hermes_record_from_yaml(record_path)

    assert isinstance(exc_info.value.__cause__, OSError)
