from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hermes.runner.analysis.hermes.timewalk_calibration import (
    PixelCluster,
    PixelHit,
    RelativeDelayAccumulator,
    Tpx3TimewalkCalibration,
    Tpx3TimewalkCorrection,
    calibrate_timewalk,
    cluster_pixel_hits,
    fit_timewalk_models,
)
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    Tpx3PhotonClusteringSettings,
)


def _settings(**updates: object) -> Tpx3PhotonClusteringSettings:
    values: dict[str, object] = {
        "max_time_spread_ticks": 2_000,
        "min_cluster_size": 2,
        "max_cluster_size": 64,
        "min_pixel_tot_raw": 1,
        "min_cluster_tot_raw": 2,
        "max_cluster_tot_raw": 65_472,
        "max_aspect_ratio": 3.0,
        "min_filled_fraction": 0.5,
    }
    values.update(updates)
    return Tpx3PhotonClusteringSettings.model_validate(values)


def test_eight_connected_clustering_grows_transitively_without_jumping() -> None:
    hits = [
        PixelHit(x=0, y=0, tot_raw=10, timestamp_canonical=100),
        PixelHit(x=1, y=1, tot_raw=10, timestamp_canonical=101),
        PixelHit(x=2, y=2, tot_raw=10, timestamp_canonical=102),
        PixelHit(x=4, y=4, tot_raw=10, timestamp_canonical=103),
    ]

    clusters = cluster_pixel_hits(hits, _settings())

    assert [[(hit.x, hit.y) for hit in cluster.hits] for cluster in clusters] == [
        [(0, 0), (1, 1), (2, 2)],
        [(4, 4)],
    ]


def test_four_connected_clustering_does_not_join_diagonal_pixels() -> None:
    hits = [
        PixelHit(x=0, y=0, tot_raw=10, timestamp_canonical=100),
        PixelHit(x=1, y=1, tot_raw=10, timestamp_canonical=101),
    ]

    clusters = cluster_pixel_hits(hits, _settings(adjacency=4))

    assert [len(cluster.hits) for cluster in clusters] == [1, 1]


def test_relative_delay_uses_earliest_pixel_and_keeps_reference_tot() -> None:
    accumulator = RelativeDelayAccumulator()
    accumulator.add_cluster(
        PixelCluster(
            hits=[
                PixelHit(x=1, y=0, tot_raw=50, timestamp_canonical=1_020),
                PixelHit(x=0, y=0, tot_raw=100, timestamp_canonical=1_000),
                PixelHit(x=0, y=1, tot_raw=75, timestamp_canonical=1_010),
            ]
        ),
        time_block=2,
    )

    arrays = accumulator.arrays()

    assert accumulator.pair_count == 2
    assert arrays.time_block.tolist() == [2, 2]
    assert arrays.pixel_tot.tolist() == [50.0, 75.0]
    assert arrays.reference_tot.tolist() == [100.0, 100.0]
    assert arrays.delay_sum.tolist() == [20.0, 10.0]


def test_fit_recovers_known_linear_relation() -> None:
    accumulator = _synthetic_accumulator("linear")

    linear_fit, inverse_fit, _ = fit_timewalk_models(accumulator)

    assert linear_fit.parameters["m"] == pytest.approx(-2.0)
    assert linear_fit.rmse_ticks == pytest.approx(0.0)
    assert linear_fit.held_out_rmse_ticks == pytest.approx(0.0)
    assert inverse_fit.held_out_rmse_ticks > linear_fit.held_out_rmse_ticks


def test_fit_recovers_known_inverse_relation() -> None:
    accumulator = _synthetic_accumulator("inverse")

    linear_fit, inverse_fit, _ = fit_timewalk_models(accumulator)

    assert inverse_fit.parameters["a"] == pytest.approx(100_000, rel=0.03)
    assert inverse_fit.parameters["b"] == pytest.approx(50, rel=0.08)
    assert inverse_fit.held_out_rmse_ticks < linear_fit.held_out_rmse_ticks


def test_calibration_writes_valid_json_and_comparison_plot(
    tmp_path: Path,
) -> None:
    pixel_file = tmp_path / "pixel_hits/raw-chip-0-part-00000.parquet"
    pixel_file.parent.mkdir()
    rows = _synthetic_parquet_rows()
    pq.write_table(pa.table(rows), pixel_file)
    output_file = tmp_path / "logs/timewalk-calibration.json"
    correction_file = tmp_path / "calibrations/timewalk-calibration-correction.json"

    calibration = calibrate_timewalk(
        [pixel_file],
        _settings(max_time_spread_ticks=2_000),
        output_file,
        correction_file,
    )
    loaded = Tpx3TimewalkCalibration.model_validate_json(
        output_file.read_bytes()
    )

    assert calibration.pixel_pairs > 0
    assert loaded == calibration
    assert output_file.is_file()
    assert calibration.comparison_plot.is_file()
    assert calibration.selected_parameters

    correction = Tpx3TimewalkCorrection.model_validate_json(
        correction_file.read_bytes()
    )
    assert correction.model == calibration.selected_model
    assert correction.parameters == calibration.selected_parameters
    assert correction.high_tot_anchor == calibration.high_tot_anchor


def test_calibration_writes_correction_to_requested_path(
    tmp_path: Path,
) -> None:
    pixel_file = tmp_path / "pixel_hits/raw-chip-0-part-00000.parquet"
    pixel_file.parent.mkdir()
    pq.write_table(pa.table(_synthetic_parquet_rows()), pixel_file)
    output_file = tmp_path / "logs/timewalk-calibration.json"
    correction_file = tmp_path / "corrections/time-walk.json"

    calibration = calibrate_timewalk(
        [pixel_file],
        _settings(max_time_spread_ticks=2_000),
        output_file,
        correction_file,
    )

    correction = Tpx3TimewalkCorrection.model_validate_json(
        correction_file.read_bytes()
    )
    assert correction.model == calibration.selected_model
    assert correction.parameters == calibration.selected_parameters


def _synthetic_accumulator(
    model: str,
) -> RelativeDelayAccumulator:
    accumulator = RelativeDelayAccumulator()
    reference_tot = 900
    for time_block in range(5):
        for pixel_tot in range(50, 851, 50):
            if model == "linear":
                delay = round(-2.0 * (pixel_tot - reference_tot))
            else:
                delay = round(
                    100_000
                    * (
                        1 / (pixel_tot + 50)
                        - 1 / (reference_tot + 50)
                    )
                )
            accumulator.add_cluster(
                PixelCluster(
                    hits=[
                        PixelHit(
                            x=0,
                            y=0,
                            tot_raw=reference_tot,
                            timestamp_canonical=1_000_000,
                        ),
                        PixelHit(
                            x=1,
                            y=0,
                            tot_raw=pixel_tot,
                            timestamp_canonical=1_000_000 + delay,
                        ),
                    ]
                ),
                time_block=time_block,
            )
    return accumulator


def _synthetic_parquet_rows() -> dict[str, list[int]]:
    rows = {
        "local_x": [],
        "local_y": [],
        "tot_raw": [],
        "timestamp_canonical": [],
    }
    for cluster_index, pixel_tot in enumerate(range(100, 801, 50)):
        reference_time = cluster_index * 10_000
        delay = round(-2.0 * (pixel_tot - 900))
        rows["local_x"].extend([10, 11])
        rows["local_y"].extend([10, 10])
        rows["tot_raw"].extend([900, pixel_tot])
        rows["timestamp_canonical"].extend(
            [reference_time, reference_time + delay]
        )
    return rows
