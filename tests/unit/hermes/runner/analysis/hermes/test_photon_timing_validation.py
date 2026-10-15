"""Calibration checks in Python and in the compiled photon program.

Build the native program with ``pixi run build-cpp-photon-clusterer`` to run
the agreement checks; Python-only validation needs no compiled program.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hermes.runner.analysis.hermes.photon_reconstruction import (
    HermesPhotonReconstructionPreflightError,
    load_photon_timing,
)
from hermes.state.models.analysis.hermes_tpx3_spidr import HermesTpx3AnalysisState

_ROOT = Path(__file__).resolve().parents[6]
_BINARY = _ROOT / "build/backends/photon-clusterer/hermes-photon-clusterer"


def _curve(**updates: object) -> str:
    return json.dumps({
        "model": "linear", "parameters": {"m": 1.0},
        "time_unit": "canonical_ticks", "high_tot_anchor": 30,
    } | updates)


_CASES = [
    pytest.param(_curve(), True, id="linear"),
    pytest.param(_curve(model="inverse", parameters={"a": 10, "b": 5}),
                 True, id="inverse"),
    pytest.param(_curve(model="inverse", parameters={"a": 10, "b": -1024}),
                 True, id="pole-outside-native-range"),
    pytest.param(_curve(high_tot_anchor=0), True, id="zero-anchor"),
    pytest.param(_curve(high_tot_anchor=1023), True, id="saturation-anchor"),
    pytest.param(_curve(parameters={"m": True}), False, id="boolean-slope"),
    pytest.param(_curve(parameters={"m": "1"}), False, id="string-slope"),
    pytest.param(_curve(parameters={}), False, id="missing-slope"),
    pytest.param(_curve(parameters=[]), False, id="parameters-not-object"),
    pytest.param(_curve(parameters={"m": float("nan")}), False, id="nan-slope"),
    pytest.param(_curve(parameters={"m": float("inf")}), False, id="infinite-slope"),
    pytest.param(_curve(parameters={"m": 1e308}), False, id="correction-overflow"),
    pytest.param(_curve(high_tot_anchor=True), False, id="boolean-anchor"),
    pytest.param(_curve(high_tot_anchor=None), False, id="null-anchor"),
    pytest.param(_curve(high_tot_anchor=float("nan")), False, id="nan-anchor"),
    pytest.param(_curve(high_tot_anchor=-1), False, id="anchor-below-range"),
    pytest.param(_curve(high_tot_anchor=1024), False, id="anchor-above-range"),
    pytest.param(_curve(time_unit="ns"), False, id="wrong-units"),
    pytest.param(_curve(model="quadratic"), False, id="unknown-model"),
    pytest.param(_curve(model="inverse", parameters={"a": 10, "b": 0}),
                 False, id="pole-at-zero"),
    pytest.param(_curve(model="inverse", parameters={"a": 10, "b": -1023}),
                 False, id="pole-at-saturation"),
    pytest.param(_curve(model="inverse", parameters={"a": 10, "b": -0.5}),
                 False, id="pole-between-integer-counts"),
    pytest.param("[]", False, id="not-object"),
    pytest.param("{", False, id="malformed-json"),
]


def _analysis(calibration: Path) -> HermesTpx3AnalysisState:
    return HermesTpx3AnalysisState.model_validate({
        "photon_reconstruction": {
            "program": {"name": "photon-clusterer-cpp", "executable_path": _BINARY},
            "clustering_algorithm": {
                "name": "connected_components",
                "settings": {
                    "max_time_spread_ticks": 491520,
                    "min_cluster_size": 2, "max_cluster_size": 64,
                    "min_pixel_tot_raw": 1, "min_cluster_tot_raw": 2,
                    "max_cluster_tot_raw": 65472,
                    "max_aspect_ratio": 3, "min_filled_fraction": 0.5,
                    "timewalk": {"method": "calibration", "calibration_file": calibration},
                },
            },
        },
    })


@pytest.mark.parametrize(("document", "accepted"), _CASES)
def test_python_validates_calibration(
    tmp_path: Path, document: str, accepted: bool,
) -> None:
    calibration = tmp_path / "curve.json"
    calibration.write_text(document, encoding="utf-8")
    analysis = _analysis(calibration)
    if accepted:
        timing = load_photon_timing(analysis)
        assert timing.calibration_file == calibration.resolve()
        assert timing.correction_model == json.loads(document)["model"]
    else:
        with pytest.raises(HermesPhotonReconstructionPreflightError, match="calibration"):
            load_photon_timing(analysis)


@pytest.mark.parametrize(("document", "accepted"), _CASES)
def test_cpp_agrees_on_calibration_files(
    tmp_path: Path, document: str, accepted: bool,
) -> None:
    if not _BINARY.is_file():
        pytest.skip("run pixi run build-cpp-photon-clusterer for native agreement checks")
    calibration = tmp_path / "curve.json"
    calibration.write_text(document, encoding="utf-8")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "timewalk": {"method": "calibration", "calibration_file": str(calibration)},
    }), encoding="utf-8")
    pixel_file = tmp_path / "sample_chip_0_pixels_00000.parquet"
    pq.write_table(pa.table({
        "local_x": pa.array([0, 1], type=pa.uint16()),
        "local_y": pa.array([0, 0], type=pa.uint16()),
        "tot_raw": pa.array([1, 1023], type=pa.uint16()),
        "timestamp_canonical": pa.array([100, 102], type=pa.uint64()),
    }), pixel_file)
    result = subprocess.run(
        [str(_BINARY), "--input", str(pixel_file), "--settings", str(settings_file)],
        cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == (0 if accepted else 2), result.stdout + result.stderr


def test_missing_calibration_is_a_preflight_error(tmp_path: Path) -> None:
    with pytest.raises(HermesPhotonReconstructionPreflightError, match="calibration"):
        load_photon_timing(_analysis(tmp_path / "missing.json"))
