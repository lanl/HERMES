from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from hermes.analysis.hermes.run import run_hermes_analysis
from hermes.analysis.hermes.unpacker import derive_summary_path
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3SpidrSummary,
    Tpx3SpidrUnpackerProgram,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_manager import StateManager

_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_TPX3_FIXTURE = _REPOSITORY_ROOT / "tests/data/Example_1kHz_5frames.tpx3"
_UNPACKER_EXECUTABLE = (
    _REPOSITORY_ROOT
    / "build/backends/tpx3-spidr/hermes-tpx3-spidr"
)


def test_real_cpp_unpacker_handles_two_inputs_and_skips_completed_files(
    tmp_path: Path,
) -> None:
    import pytest

    if not _TPX3_FIXTURE.is_file():
        pytest.skip(f"required TPX3 test file is missing: {_TPX3_FIXTURE}")
    if not _UNPACKER_EXECUTABLE.is_file():
        pytest.skip(
            "build the required C++ unpacker before running this test: "
            f"{_UNPACKER_EXECUTABLE}"
        )

    raw_directory = tmp_path / "rawTpx3"
    raw_directory.mkdir()
    raw_paths = [
        raw_directory / "example-first.tpx3",
        raw_directory / "example-second.tpx3",
    ]
    for raw_path in raw_paths:
        shutil.copyfile(_TPX3_FIXTURE, raw_path)

    analysis = HermesTpx3AnalysisState(
        unpacker_program=Tpx3SpidrUnpackerProgram(
            name="tpx3-spidr-cpp",
            executable_path=_UNPACKER_EXECUTABLE,
            version="0.1.0",
        ),
        analysis_directory=tmp_path / "analysis",
        tpx3_files=[FileReference(path=raw_path) for raw_path in raw_paths],
    )
    manager = StateManager(
        HermesRecord(
            measurement_info=MeasurementInfo(
                measurement_id="real-tpx3-unpacker",
                run_number=1,
            ),
            environment=RuntimeEnvironment(working_dir=tmp_path),
            acquisition=None,
            analysis=analysis,
        ),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )

    log_records: list[dict[str, Any]] = []
    sink_id = logger.add(
        lambda message: log_records.append(message.record),
        filter=lambda record: record["extra"].get("domain") == "analysis",
    )
    try:
        first_run = run_hermes_analysis(manager)
    finally:
        logger.remove(sink_id)

    assert [raw_file.path for raw_file in first_run] == raw_paths
    completed_state = manager.get_state()
    assert completed_state.acquisition is None
    assert completed_state.analysis.results.unpacking.status == "completed"
    assert completed_state.analysis.results.unpacking.started_at is not None
    assert completed_state.analysis.results.unpacking.finished_at is not None

    summaries: list[Tpx3SpidrSummary] = []
    generated_paths: set[Path] = set()
    for raw_file in analysis.tpx3_files:
        summary_path = derive_summary_path(analysis, raw_file)
        assert summary_path.is_file()
        summary = Tpx3SpidrSummary.model_validate_json(summary_path.read_bytes())
        summaries.append(summary)

        listed_paths = {
            relative_path
            for category in (
                summary.parquet.pixel_data,
                summary.parquet.tdc_timestamps,
                summary.parquet.heartbeat_packets,
                summary.parquet.control_packets,
                summary.parquet.unrecognized_packets,
            )
            for relative_path in category.files
        }
        assert listed_paths
        assert all(
            relative_path.name.startswith(f"{raw_file.path.stem}-")
            for relative_path in listed_paths
        )
        assert generated_paths.isdisjoint(listed_paths)
        generated_paths.update(listed_paths)
        assert all(
            (analysis.analysis_directory / relative_path).is_file()
            for relative_path in listed_paths
        )

    assert all(not summary.unpacking.errors for summary in summaries)
    assert all(not summary.parquet.errors for summary in summaries)
    assert sum(
        summary.parquet.pixel_data.row_count for summary in summaries
    ) > 0

    saved_analysis = completed_state.analysis.model_dump(mode="json")
    assert set(saved_analysis) == {
        "mode",
        "unpacker_program",
        "analysis_directory",
        "tpx3_files",
        "results",
    }
    assert set(saved_analysis["results"]["unpacking"]) == {
        "status",
        "started_at",
        "finished_at",
    }
    assert not _contains_key(
        saved_analysis,
        {
            "summary_json_file",
            "parquet",
            "warnings",
            "errors",
            "exit_code",
            "command_args",
        },
    )

    first_event_inputs = [
        Path(record["extra"]["raw_tpx3_file"]).name
        for record in log_records
        if record["extra"].get("event_type")
        == "analysis.tpx3_unpacking.started"
    ]
    assert first_event_inputs == ["example-first.tpx3", "example-second.tpx3"]

    saved_files = [
        derive_summary_path(analysis, raw_file)
        for raw_file in analysis.tpx3_files
    ] + [
        analysis.analysis_directory / relative_path
        for relative_path in generated_paths
    ]
    modification_times = {
        path: path.stat().st_mtime_ns
        for path in saved_files
    }

    skip_records: list[dict[str, Any]] = []
    sink_id = logger.add(
        lambda message: skip_records.append(message.record),
        filter=lambda record: record["extra"].get("domain") == "analysis",
    )
    try:
        second_run = run_hermes_analysis(manager)
    finally:
        logger.remove(sink_id)

    assert second_run == []
    assert {
        path: path.stat().st_mtime_ns
        for path in saved_files
    } == modification_times
    skipped_inputs = [
        Path(record["extra"]["raw_tpx3_file"]).name
        for record in skip_records
        if record["extra"].get("event_type")
        == "analysis.tpx3_unpacking.skipped"
    ]
    assert skipped_inputs == ["example-first.tpx3", "example-second.tpx3"]
    assert manager.get_state().analysis.results.unpacking.status == "completed"


def _contains_key(value: object, keys: set[str]) -> bool:
    if isinstance(value, dict):
        return any(key in keys for key in value) or any(
            _contains_key(child, keys) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(child, keys) for child in value)
    return False
