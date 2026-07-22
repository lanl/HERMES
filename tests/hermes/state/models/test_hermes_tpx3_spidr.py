from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesPhotonReconstructionState,
    HermesTpx3AnalysisState,
    Tpx3SpidrUnpackerProgram,
    Tpx3SpidrUnpackerResult,
    Tpx3SpidrUnpackerSettings,
    Tpx3SpidrUnpackingRun,
)
from hermes.state.models.shared_models import FileReference


def _unpacking_run(tmp_path: Path) -> Tpx3SpidrUnpackingRun:
    raw_file = FileReference(path=tmp_path / "raw.tpx3")
    return Tpx3SpidrUnpackingRun(
        program=Tpx3SpidrUnpackerProgram(
            name="tpx3-spidr-cpp",
            executable_path=tmp_path / "bin/hermes-tpx3-spidr",
            version="0.1.0",
        ),
        settings=Tpx3SpidrUnpackerSettings(
            input_tpx3_file=raw_file,
            tpx3_parquet_directory=tmp_path / "tpx3_parquet",
            command_args=[str(raw_file.path), str(tmp_path / "tpx3_parquet")],
        ),
        result=Tpx3SpidrUnpackerResult(
            status="completed",
            exit_code=0,
            summary_json_file=FileReference(
                path=tmp_path / "tpx3_parquet/summary.json"
            ),
            pixel_hit_count=10,
            tdc_hit_count=2,
            global_timestamp_count=1,
            spidr_control_count=3,
            tpx3_control_count=4,
            unknown_packet_count=0,
        ),
    )


def test_hermes_analysis_state_serializes_unpacking_runs(tmp_path: Path) -> None:
    state = HermesTpx3AnalysisState(unpacking_runs=[_unpacking_run(tmp_path)])

    dumped = state.model_dump(mode="json")

    assert dumped["mode"] == "hermes"
    assert dumped["unpacking_runs"][0]["program"]["name"] == "tpx3-spidr-cpp"
    assert dumped["unpacking_runs"][0]["settings"][
        "tpx3_parquet_directory"
    ].endswith("tpx3_parquet")
    assert dumped["unpacking_runs"][0]["result"]["pixel_hit_count"] == 10
    assert dumped["photon_reconstruction"] is None
    assert dumped["event_reconstruction"] is None


def test_hermes_analysis_state_requires_an_unpacking_run() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        HermesTpx3AnalysisState(unpacking_runs=[])


def test_unpacker_result_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError, match="pixel_hit_count"):
        Tpx3SpidrUnpackerResult(pixel_hit_count=-1)


def test_empty_reconstruction_models_reject_undefined_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        HermesPhotonReconstructionState(settings={})
