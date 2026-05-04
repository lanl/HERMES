from __future__ import annotations

from pathlib import Path

from hermes.state.models.acquisition.serval import (
    ServalAcquisitionResult,
    ServalAcquisitionState,
)
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3SpidrAnalysisState,
    HermesTpx3SpidrResult,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import ArtifactRef
from hermes.state.state import HermesRecord


HASH = "a" * 64


def test_hermes_record_serializes_paths_datetimes_and_mode_tags(tmp_path: Path) -> None:
    raw_artifact = ArtifactRef(
        path=tmp_path / "run-001/data/tpx3/raw.tpx3",
        kind="raw_tpx3",
        media_type="application/octet-stream",
        sha256=HASH,
        size_bytes=1024,
    )
    decoded_artifact = ArtifactRef(
        path=tmp_path / "run-001/data/analyzed/events.parquet",
        kind="decoded_events",
        media_type="application/parquet",
    )
    record = HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id=" LC-20231023 ",
            run_number=1,
            beamline="DCS",
        ),
        environment=RuntimeEnvironment(working_dir=tmp_path / "run-001"),
        acquisition=ServalAcquisitionState(
            result=ServalAcquisitionResult(status="completed", artifacts=[raw_artifact])
        ),
        analysis=HermesTpx3SpidrAnalysisState(
            result=HermesTpx3SpidrResult(
                status="completed",
                input_artifacts=[raw_artifact],
                output_artifacts=[decoded_artifact],
                summary_metrics={"events": 42, "duration_s": 1.5},
            )
        ),
    )

    dumped = record.model_dump(mode="json")

    assert dumped["measurement_info"]["measurement_id"] == "LC-20231023"
    assert dumped["environment"]["working_dir"]["resolved_path"] == str(
        (tmp_path / "run-001").resolve()
    )
    assert dumped["environment"]["raw_data_dir"]["resolved_path"] is None
    assert dumped["acquisition"]["mode"] == "serval"
    assert dumped["acquisition"]["result"]["artifacts"][0]["path"].endswith("raw.tpx3")
    assert dumped["analysis"]["mode"] == "hermes_tpx3_spidr"
    assert dumped["analysis"]["result"]["summary_metrics"]["events"] == 42
