"""Numerical timing through YAML -> Workflow -> the real C++ program -> Parquet.

Run ``pixi run build-cpp-photon-clusterer`` before these tests. All inputs and
outputs are tiny synthetic files created under pytest's temporary directory.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3PhotonReconstructionSummary,
)
from hermes.state_service.state_io import load_hermes_record_from_yaml
from hermes.workflows.workflow import Workflow

_ROOT = Path(__file__).resolve().parents[6]
_BINARY = _ROOT / "build/backends/photon-clusterer/hermes-photon-clusterer"

# These are hand-calculated canonical-tick times, independent of the decoder
# and timing helpers. Raw times are 100,106,110 at ToTs 10,30,20. Linear delays
# are -20,0,-10; inverse delays are 6,0,2. Every source hit counts in the mean.
_CASES = [
    pytest.param(None, None, False, 316 / 3, id="omitted-timing-defaults"),
    pytest.param("average", None, False, 316 / 3, id="raw-average"),
    pytest.param("leading_edge", None, False, 100, id="raw-leading-edge"),
    pytest.param("brightest", None, False, 106, id="raw-brightest"),
    pytest.param("average", "linear", False, 346 / 3, id="linear-average"),
    pytest.param("leading_edge", "linear", False, 106, id="linear-leading-edge"),
    pytest.param("brightest", "linear", False, 106, id="linear-brightest"),
    pytest.param("average", "inverse", False, 308 / 3, id="inverse-average"),
    pytest.param("leading_edge", "inverse", False, 94, id="inverse-leading-edge"),
    pytest.param("brightest", "inverse", False, 106, id="inverse-brightest"),
    pytest.param("leading_edge", "inverse", True, 94, id="legacy-calibrated-leading-edge"),
]


def _assert_workflow_timing(
    tmp_path: Path,
    estimator: str | None,
    model: str | None,
    legacy: bool,
    expected: float,
    source_times: tuple[int, int, int] = (100, 106, 110),
    exact_time: bool = False,
) -> None:
    if not _BINARY.is_file():
        pytest.skip("run pixi run build-cpp-photon-clusterer for timing integration tests")

    run_directory = tmp_path / "run"
    analysis_directory = run_directory / "analysis"
    pixel_file = analysis_directory / "pixel_hits/sample_chip_0_pixels_00000.parquet"
    pixel_file.parent.mkdir(parents=True)
    source = pa.table({
        "local_x": pa.array([0, 1, 1], type=pa.uint16()),
        "local_y": pa.array([0, 0, 0], type=pa.uint16()),
        "tot_raw": pa.array([10, 30, 20], type=pa.uint16()),
        "timestamp_canonical": pa.array(source_times, type=pa.uint64()),
    })
    pq.write_table(source, pixel_file)
    source_bytes = pixel_file.read_bytes()
    settings: dict[str, object] = {
        "max_time_spread_ticks": 20,
        "min_cluster_size": 2, "max_cluster_size": 64,
        "min_pixel_tot_raw": 1, "min_cluster_tot_raw": 2,
        "max_cluster_tot_raw": 65472,
        "max_aspect_ratio": 3, "min_filled_fraction": 0.5,
    }
    if estimator is not None:
        settings["photon_time_estimator"] = estimator
        settings["timewalk"] = {"method": "none"}
    calibration_file = tmp_path / "curve.json"
    parameters = {"m": 1} if model == "linear" else {"a": 240, "b": 10}
    if model is not None:
        calibration_file.write_text(json.dumps({
            "model": model, "parameters": parameters,
            "time_unit": "canonical_ticks", "high_tot_anchor": 30,
        }), encoding="utf-8")
        if legacy:
            settings.pop("timewalk")
            settings["timewalk_calibration_file"] = str(calibration_file)
        else:
            settings["timewalk"] = {
                "method": "calibration", "calibration_file": str(calibration_file),
            }
    config_file = tmp_path / "input.yaml"
    config_file.write_text(yaml.safe_dump({
        "measurement_info": {"measurement_id": "numerical-photon-timing", "run": "run"},
        "environment": {
            "working_directory": str(tmp_path), "run_directory": "run",
            "analysis_directory": "analysis", "log_level": "ERROR",
        },
        "analysis": {
            "mode": "hermes",
            "detector_layout": {"kind": "single_chip"},
            "photon_reconstruction": {
                "program": {
                    "name": "photon-clusterer-cpp", "executable_path": str(_BINARY),
                },
                "pixel_files": "auto",
                "clustering_algorithm": {
                    "name": "connected_components", "save_photon_pixels": True,
                    "settings": settings,
                },
            },
        },
    }), encoding="utf-8")
    config_bytes = config_file.read_bytes()

    record = Workflow(load_hermes_record_from_yaml(config_file)).run()
    reconstruction = record.analysis.photon_reconstruction
    assert len(reconstruction.results) == 1
    assert reconstruction.results[0].status == "completed"
    photons = pq.read_table(reconstruction.results[0].output_file)
    assert photons.schema.field("timestamp_canonical").type == pa.float64()
    assert photons.num_rows == 1
    photon = photons.to_pylist()[0]
    # Small rational means allow two final float64 rounding steps. Large-time
    # regressions require exact values: two float64 steps there hide lost ticks.
    assert photon.pop("timestamp_canonical") == pytest.approx(
        expected, rel=0, abs=0 if exact_time else 2 * math.ulp(float(expected)),
    )
    assert photon == {"photon_id": 0, "x": 2 / 3, "y": 0, "tot": 60, "quality_flags": 0}

    metadata = {key.decode(): value.decode() for key, value in photons.schema.metadata.items()}
    chosen_estimator = estimator or "average"
    method = "calibration" if model is not None else "none"
    expected_file = str(calibration_file) if model is not None else ""
    assert metadata["photon_time_estimator"] == chosen_estimator
    assert metadata["timewalk_method"] == method
    assert metadata["correction_model"] == (model or "none")
    assert metadata["calibration_file"] == expected_file
    assert float(metadata["canonical_tick_seconds"]) == 25e-9 / 12288
    echoed = json.loads(metadata["clustering_settings"])
    assert echoed["photon_time_estimator"] == chosen_estimator
    assert echoed["timewalk"] == {
        "method": method, "calibration_file": expected_file or None,
    }
    if model is not None:
        assert json.loads(metadata["correction_parameters"]) == parameters
        assert float(metadata["high_tot_anchor"]) == 30
    else:
        assert "correction_parameters" not in metadata
        assert "high_tot_anchor" not in metadata

    summary_file = (
        analysis_directory / "logs/photon_reconstruction"
        / "sample_chip_0_photon_reconstruction_summary_00000.json"
    )
    summary = HermesTpx3PhotonReconstructionSummary.model_validate_json(summary_file.read_bytes())
    assert summary.reconstruction.pixels_read == 3
    assert summary.reconstruction.clusters_formed == 1
    assert summary.reconstruction.total_photons == 1
    assert summary.reconstruction.rejected_clusters == 0
    assert summary.photon_timing.estimator == chosen_estimator
    assert summary.photon_timing.correction_model == (model or "none")
    assert summary.photon_timing.calibration_file == (calibration_file if model else None)
    assert summary.photon_timing.parameters == (parameters if model else {})
    assert summary.photon_timing.high_tot_anchor == (30 if model else None)
    assert summary.clustering.settings == echoed

    pixel_clusters = pq.read_table(summary.parquet_files.pixel_clusters.files[0])
    assert pixel_clusters.schema.field("timestamp_canonical").type == pa.uint64()
    assert pixel_clusters.to_pylist() == [
        {"photon_id": 0, "pixel_event_id": index,
         "x": hit["local_x"], "y": hit["local_y"],
         "tot_raw": hit["tot_raw"], "timestamp_canonical": hit["timestamp_canonical"]}
        for index, hit in enumerate(source.to_pylist())
    ]
    assert pixel_file.read_bytes() == source_bytes
    assert config_file.read_bytes() == config_bytes

    saved = load_hermes_record_from_yaml(run_directory / "HERMES_record.yaml")
    saved_settings = saved.analysis.photon_reconstruction.clustering_algorithm.settings
    assert saved_settings.photon_time_estimator == chosen_estimator
    assert saved_settings.timewalk.method == method
    assert saved_settings.timewalk.calibration_file == (calibration_file if model else None)
    assert "timewalk_calibration_file" not in saved_settings.model_dump()
    workflow_log = run_directory / "HERMES-workflow.jsonl"
    log_lines = [json.loads(line) for line in workflow_log.read_text().splitlines()]
    assert log_lines[-1]["event"] == "workflow_completed"


@pytest.mark.parametrize(("estimator", "model", "legacy", "expected"), _CASES)
def test_workflow_writes_expected_photon_time_and_timing_details(
    tmp_path: Path,
    estimator: str | None,
    model: str | None,
    legacy: bool,
    expected: float,
) -> None:
    _assert_workflow_timing(tmp_path, estimator, model, legacy, expected)


@pytest.mark.parametrize(("model", "expected"), [
    pytest.param(None, float(2**53 + 2), id="raw"),
    pytest.param("linear", float(2**53 + 12), id="linear"),
    pytest.param("inverse", float(2**53 - 1), id="inverse"),
])
def test_workflow_retains_large_timestamp_average(
    tmp_path: Path, model: str | None, expected: float,
) -> None:
    # The raw mean is 2^53+5/3. Linear correction adds a mean of 10 ticks;
    # inverse correction subtracts a mean of 8/3, giving exactly 2^53-1.
    # All expected values above are the nearest representable float64 values.
    _assert_workflow_timing(
        tmp_path, None if model is None else "average", model, False, expected,
        source_times=(2**53 + 1, 2**53 + 2, 2**53 + 2),
        exact_time=True,
    )
