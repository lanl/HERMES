from __future__ import annotations

import heapq
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable, Iterator, Literal

import matplotlib
import numpy as np
import pyarrow.parquet as pq
from loguru import logger
from pydantic import Field, model_validator

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    Tpx3PhotonClusteringSettings,
)
from hermes.state.models.shared_models import StrictBaseModel

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

_CANONICAL_TIME_SECONDS = 25e-9 / 12_288
_CALIBRATION_DIRECTORY = (
    Path(__file__).resolve().parents[4] / "calibrations" / "tpx3"
)
_TIME_BLOCK_COUNT = 5
_PIXEL_FILENAME = re.compile(
    r"^(?P<stem>.+)-chip-(?P<chip>\d+)-part-(?P<part>\d{5})\.parquet$"
)
_CALIBRATION_LOGGER = logger.bind(
    domain="analysis",
    mode="hermes",
    step="timewalk_calibration",
)


@dataclass(frozen=True, slots=True)
class PixelHit:
    x: int
    y: int
    tot_raw: int
    timestamp_canonical: int


@dataclass(slots=True)
class PixelCluster:
    hits: list[PixelHit]
    bridged_components: bool = False


@dataclass(slots=True)
class _OpenCluster:
    cluster_id: int
    hits: list[PixelHit]
    coordinates: set[tuple[int, int]]
    min_timestamp: int
    max_timestamp: int
    bridged_components: bool = False


@dataclass(slots=True)
class _DelayMoments:
    count: int = 0
    delay_sum: float = 0.0
    delay_square_sum: float = 0.0

    def add(self, delay: int) -> None:
        self.count += 1
        self.delay_sum += delay
        self.delay_square_sum += delay * delay


@dataclass(slots=True)
class RelativeDelayAccumulator:
    moments: dict[tuple[int, int, int], _DelayMoments] = field(
        default_factory=dict
    )
    pair_count: int = 0

    def add_cluster(self, cluster: PixelCluster, time_block: int) -> None:
        if len(cluster.hits) < 2:
            return
        reference = min(
            enumerate(cluster.hits),
            key=lambda indexed_hit: (
                indexed_hit[1].timestamp_canonical,
                indexed_hit[0],
            ),
        )[1]
        for hit in cluster.hits:
            if hit is reference:
                continue
            delay = hit.timestamp_canonical - reference.timestamp_canonical
            key = (time_block, hit.tot_raw, reference.tot_raw)
            self.moments.setdefault(key, _DelayMoments()).add(delay)
            self.pair_count += 1

    def arrays(self) -> _DelayArrays:
        keys = list(self.moments)
        return _DelayArrays(
            time_block=np.asarray([key[0] for key in keys], dtype=np.int16),
            pixel_tot=np.asarray([key[1] for key in keys], dtype=np.float64),
            reference_tot=np.asarray(
                [key[2] for key in keys],
                dtype=np.float64,
            ),
            count=np.asarray(
                [self.moments[key].count for key in keys],
                dtype=np.float64,
            ),
            delay_sum=np.asarray(
                [self.moments[key].delay_sum for key in keys],
                dtype=np.float64,
            ),
            delay_square_sum=np.asarray(
                [self.moments[key].delay_square_sum for key in keys],
                dtype=np.float64,
            ),
        )


@dataclass(frozen=True, slots=True)
class _DelayArrays:
    time_block: np.ndarray
    pixel_tot: np.ndarray
    reference_tot: np.ndarray
    count: np.ndarray
    delay_sum: np.ndarray
    delay_square_sum: np.ndarray

    def subset(self, mask: np.ndarray) -> _DelayArrays:
        return _DelayArrays(
            time_block=self.time_block[mask],
            pixel_tot=self.pixel_tot[mask],
            reference_tot=self.reference_tot[mask],
            count=self.count[mask],
            delay_sum=self.delay_sum[mask],
            delay_square_sum=self.delay_square_sum[mask],
        )


class TimewalkSubsetFit(StrictBaseModel):
    time_block: int = Field(ge=0, lt=_TIME_BLOCK_COUNT)
    parameters: dict[str, float]


class TimewalkCandidateFit(StrictBaseModel):
    model: Literal["linear", "inverse"]
    parameters: dict[str, float]
    rmse_ticks: float = Field(ge=0)
    held_out_rmse_ticks: float = Field(ge=0)
    residual_tot_correlation: float = Field(ge=-1, le=1)
    subset_fits: list[TimewalkSubsetFit]


class TimewalkTotBin(StrictBaseModel):
    tot_raw: int = Field(ge=0, le=1023)
    pair_count: int = Field(gt=0)
    mean_relative_delay_ticks: float
    linear_prediction_ticks: float
    inverse_prediction_ticks: float
    linear_residual_ticks: float
    inverse_residual_ticks: float


class Tpx3TimewalkCorrection(StrictBaseModel):
    """Small correction file consumed by the reconstruction clusterer."""

    model: Literal["linear", "inverse"]
    parameters: dict[str, float]
    high_tot_anchor: float = Field(ge=0, le=1023)
    time_unit: Literal["canonical_ticks"] = "canonical_ticks"
    date_created: date
    note: str | None = None


class Tpx3TimewalkCalibration(StrictBaseModel):
    schema_version: Literal[1] = 1
    canonical_time_seconds: float = Field(gt=0)
    input_pixel_data_files: list[Path] = Field(min_length=1)
    clustering_settings: Tpx3PhotonClusteringSettings
    components_considered: int = Field(ge=0)
    components_used: int = Field(gt=0)
    pixel_pairs: int = Field(gt=0)
    high_tot_anchor: float = Field(ge=0, le=1023)
    candidate_fits: list[TimewalkCandidateFit] = Field(min_length=2)
    selected_model: Literal["linear", "inverse"]
    selected_parameters: dict[str, float]
    selection_reason: str = Field(min_length=1)
    tot_bins: list[TimewalkTotBin] = Field(min_length=1)
    comparison_plot: Path

    @model_validator(mode="after")
    def require_both_candidate_models(self) -> Tpx3TimewalkCalibration:
        models = [candidate.model for candidate in self.candidate_fits]
        if sorted(models) != ["inverse", "linear"]:
            raise ValueError(
                "candidate_fits must contain one linear and one inverse fit"
            )
        if self.selected_model not in models:
            raise ValueError("selected_model must name one candidate fit")
        selected_fit = next(
            candidate
            for candidate in self.candidate_fits
            if candidate.model == self.selected_model
        )
        if self.selected_parameters != selected_fit.parameters:
            raise ValueError(
                "selected_parameters must match the selected candidate fit"
            )
        if self.components_used > self.components_considered:
            raise ValueError(
                "components_used cannot exceed components_considered"
            )
        return self


def iter_connected_components(
    hits: Iterable[PixelHit],
    settings: Tpx3PhotonClusteringSettings,
) -> Iterator[PixelCluster]:
    open_clusters: dict[int, _OpenCluster] = {}
    coordinate_index: dict[tuple[int, int], set[int]] = defaultdict(set)
    expiration_heap: list[tuple[int, int]] = []
    next_cluster_id = 0

    def close_cluster(cluster_id: int) -> PixelCluster | None:
        cluster = open_clusters.pop(cluster_id, None)
        if cluster is None:
            return None
        for coordinate in cluster.coordinates:
            cluster_ids = coordinate_index[coordinate]
            cluster_ids.discard(cluster_id)
            if not cluster_ids:
                del coordinate_index[coordinate]
        return PixelCluster(
            hits=cluster.hits,
            bridged_components=cluster.bridged_components,
        )

    for hit in hits:
        while expiration_heap:
            min_timestamp, cluster_id = expiration_heap[0]
            cluster = open_clusters.get(cluster_id)
            if cluster is None or cluster.min_timestamp != min_timestamp:
                heapq.heappop(expiration_heap)
                continue
            if (
                hit.timestamp_canonical - min_timestamp
                <= settings.max_time_spread_ticks
            ):
                break
            heapq.heappop(expiration_heap)
            closed = close_cluster(cluster_id)
            if closed is not None:
                yield closed

        adjacent_ids: set[int] = set()
        for dx, dy in _neighbor_offsets(settings.adjacency):
            adjacent_ids.update(
                coordinate_index.get((hit.x + dx, hit.y + dy), ())
            )

        if not adjacent_ids:
            cluster_id = next_cluster_id
            next_cluster_id += 1
            cluster = _OpenCluster(
                cluster_id=cluster_id,
                hits=[hit],
                coordinates={(hit.x, hit.y)},
                min_timestamp=hit.timestamp_canonical,
                max_timestamp=hit.timestamp_canonical,
            )
            open_clusters[cluster_id] = cluster
            coordinate_index[(hit.x, hit.y)].add(cluster_id)
            heapq.heappush(
                expiration_heap,
                (cluster.min_timestamp, cluster_id),
            )
            continue

        surviving_id = min(adjacent_ids)
        surviving = open_clusters[surviving_id]
        surviving.hits.append(hit)
        surviving.max_timestamp = hit.timestamp_canonical
        surviving.coordinates.add((hit.x, hit.y))
        coordinate_index[(hit.x, hit.y)].add(surviving_id)

        if len(adjacent_ids) > 1:
            surviving.bridged_components = True
        for merged_id in sorted(adjacent_ids - {surviving_id}):
            merged = open_clusters.pop(merged_id)
            surviving.hits.extend(merged.hits)
            surviving.coordinates.update(merged.coordinates)
            surviving.min_timestamp = min(
                surviving.min_timestamp,
                merged.min_timestamp,
            )
            surviving.bridged_components = (
                surviving.bridged_components
                or merged.bridged_components
            )
            for coordinate in merged.coordinates:
                cluster_ids = coordinate_index[coordinate]
                cluster_ids.discard(merged_id)
                cluster_ids.add(surviving_id)

    for cluster_id in sorted(
        open_clusters,
        key=lambda value: (
            open_clusters[value].min_timestamp,
            value,
        ),
    ):
        closed = close_cluster(cluster_id)
        if closed is not None:
            yield closed


def cluster_pixel_hits(
    hits: Iterable[PixelHit],
    settings: Tpx3PhotonClusteringSettings,
) -> list[PixelCluster]:
    filtered_hits = (
        hit for hit in hits if hit.tot_raw >= settings.min_pixel_tot_raw
    )
    return list(iter_connected_components(filtered_hits, settings))


def cluster_passes_calibration_filters(
    cluster: PixelCluster,
    settings: Tpx3PhotonClusteringSettings,
) -> bool:
    pixel_count = len(cluster.hits)
    if not settings.min_cluster_size <= pixel_count <= settings.max_cluster_size:
        return False

    integrated_tot = sum(hit.tot_raw for hit in cluster.hits)
    if not (
        settings.min_cluster_tot_raw
        <= integrated_tot
        <= settings.max_cluster_tot_raw
    ):
        return False

    coordinates = {(hit.x, hit.y) for hit in cluster.hits}
    xs = [coordinate[0] for coordinate in coordinates]
    ys = [coordinate[1] for coordinate in coordinates]
    width = max(xs) - min(xs) + 1
    height = max(ys) - min(ys) + 1
    aspect_ratio = max(width, height) / min(width, height)
    filled_fraction = len(coordinates) / (width * height)
    return (
        aspect_ratio <= settings.max_aspect_ratio
        and filled_fraction >= settings.min_filled_fraction
    )


def fit_timewalk_models(
    accumulator: RelativeDelayAccumulator,
) -> tuple[
    TimewalkCandidateFit,
    TimewalkCandidateFit,
    list[TimewalkTotBin],
]:
    arrays = accumulator.arrays()
    if arrays.count.size == 0:
        raise ValueError("time-walk fitting requires at least one pixel pair")

    linear_parameters = _fit_linear(arrays)
    inverse_parameters = _fit_inverse(arrays)
    linear_rmse = _rmse(arrays, "linear", linear_parameters)
    inverse_rmse = _rmse(arrays, "inverse", inverse_parameters)
    linear_held_out = _held_out_rmse(arrays, "linear")
    inverse_held_out = _held_out_rmse(arrays, "inverse")
    bins = _build_tot_bins(
        arrays,
        linear_parameters,
        inverse_parameters,
    )

    linear_fit = TimewalkCandidateFit(
        model="linear",
        parameters=linear_parameters,
        rmse_ticks=linear_rmse,
        held_out_rmse_ticks=linear_held_out,
        residual_tot_correlation=_residual_correlation(
            bins,
            "linear",
        ),
        subset_fits=_subset_fits(arrays, "linear"),
    )
    inverse_fit = TimewalkCandidateFit(
        model="inverse",
        parameters=inverse_parameters,
        rmse_ticks=inverse_rmse,
        held_out_rmse_ticks=inverse_held_out,
        residual_tot_correlation=_residual_correlation(
            bins,
            "inverse",
        ),
        subset_fits=_subset_fits(arrays, "inverse"),
    )
    return linear_fit, inverse_fit, bins


def calibrate_timewalk(
    pixel_data_files: list[Path],
    settings: Tpx3PhotonClusteringSettings,
    output_file: Path,
    correction_file: Path | None = None,
) -> Tpx3TimewalkCalibration:
    grouped_files = _group_pixel_files(pixel_data_files)
    if not grouped_files:
        raise ValueError("no pixel_data Parquet files were supplied")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    comparison_plot = output_file.with_name(
        f"{output_file.stem}-comparison.png"
    )
    _CALIBRATION_LOGGER.info(
        "analysis.timewalk_calibration.started",
        event_type="analysis.timewalk_calibration.started",
        pixel_data_file_count=len(pixel_data_files),
        output_file=str(output_file),
        comparison_plot=str(comparison_plot),
        clustering_settings=settings.model_dump(mode="json"),
    )

    accumulator = RelativeDelayAccumulator()
    components_considered = 0
    components_used = 0
    grouped_items = sorted(grouped_files.items())
    for group_index, (_, files) in enumerate(grouped_items):
        time_block = min(
            _TIME_BLOCK_COUNT - 1,
            group_index * _TIME_BLOCK_COUNT // len(grouped_items),
        )
        filtered_hits = (
            hit
            for hit in _iter_pixel_hits(files)
            if hit.tot_raw >= settings.min_pixel_tot_raw
        )
        for cluster in iter_connected_components(filtered_hits, settings):
            components_considered += 1
            if not cluster_passes_calibration_filters(cluster, settings):
                continue
            components_used += 1
            accumulator.add_cluster(cluster, time_block)

    linear_fit, inverse_fit, bins = fit_timewalk_models(accumulator)
    selected_model, selection_reason = _select_model(
        linear_fit,
        inverse_fit,
    )
    high_tot_anchor = _weighted_percentile(
        accumulator.arrays().reference_tot,
        accumulator.arrays().count,
        0.95,
    )
    _write_comparison_plot(
        bins,
        linear_fit,
        inverse_fit,
        comparison_plot,
    )

    calibration = Tpx3TimewalkCalibration(
        canonical_time_seconds=_CANONICAL_TIME_SECONDS,
        input_pixel_data_files=[
            _relative_pixel_path(path) for path in pixel_data_files
        ],
        clustering_settings=settings,
        components_considered=components_considered,
        components_used=components_used,
        pixel_pairs=accumulator.pair_count,
        high_tot_anchor=high_tot_anchor,
        candidate_fits=[linear_fit, inverse_fit],
        selected_model=selected_model,
        selected_parameters=(
            linear_fit.parameters
            if selected_model == "linear"
            else inverse_fit.parameters
        ),
        selection_reason=selection_reason,
        tot_bins=bins,
        comparison_plot=comparison_plot,
    )
    output_file.write_text(
        calibration.model_dump_json(indent=2),
        encoding="utf-8",
    )

    resolved_correction_file = (
        correction_file
        if correction_file is not None
        else _CALIBRATION_DIRECTORY / f"{output_file.stem}-correction.json"
    )
    correction = Tpx3TimewalkCorrection(
        model=selected_model,
        parameters=calibration.selected_parameters,
        high_tot_anchor=high_tot_anchor,
        date_created=date.today(),
        note=selection_reason,
    )
    resolved_correction_file.parent.mkdir(parents=True, exist_ok=True)
    resolved_correction_file.write_text(
        correction.model_dump_json(indent=2),
        encoding="utf-8",
    )

    _CALIBRATION_LOGGER.info(
        "analysis.timewalk_calibration.completed",
        event_type="analysis.timewalk_calibration.completed",
        output_file=str(output_file),
        correction_file=str(resolved_correction_file),
        comparison_plot=str(comparison_plot),
        components_considered=components_considered,
        components_used=components_used,
        pixel_pairs=accumulator.pair_count,
        selected_model=selected_model,
        linear_held_out_rmse_ticks=linear_fit.held_out_rmse_ticks,
        inverse_held_out_rmse_ticks=inverse_fit.held_out_rmse_ticks,
    )
    return calibration


def _neighbor_offsets(adjacency: Literal[4, 8]) -> tuple[tuple[int, int], ...]:
    if adjacency == 4:
        return ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))
    return tuple(
        (dx, dy)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
    )


def _group_pixel_files(
    pixel_data_files: list[Path],
) -> dict[tuple[str, int], list[Path]]:
    grouped: dict[tuple[str, int], list[tuple[int, Path]]] = defaultdict(list)
    for path in pixel_data_files:
        match = _PIXEL_FILENAME.fullmatch(path.name)
        if match is None:
            raise ValueError(f"invalid pixel_data filename: {path}")
        grouped[(match.group("stem"), int(match.group("chip")))].append(
            (int(match.group("part")), path)
        )

    result: dict[tuple[str, int], list[Path]] = {}
    for key, parts in grouped.items():
        part_indexes = sorted(part for part, _ in parts)
        if part_indexes != list(range(len(part_indexes))):
            raise ValueError(f"pixel_data parts must be contiguous for {key}")
        result[key] = [path for _, path in sorted(parts)]
    return result


def _iter_pixel_hits(files: list[Path]) -> Iterator[PixelHit]:
    columns = ["local_x", "local_y", "tot_raw", "timestamp_canonical"]
    for path in files:
        parquet_file = pq.ParquetFile(path)
        for batch in parquet_file.iter_batches(
            batch_size=65_536,
            columns=columns,
        ):
            x_values = batch.column(0).to_numpy(zero_copy_only=False)
            y_values = batch.column(1).to_numpy(zero_copy_only=False)
            tot_values = batch.column(2).to_numpy(zero_copy_only=False)
            timestamp_values = batch.column(3).to_numpy(zero_copy_only=False)
            for x, y, tot_raw, timestamp in zip(
                x_values,
                y_values,
                tot_values,
                timestamp_values,
                strict=True,
            ):
                yield PixelHit(
                    x=int(x),
                    y=int(y),
                    tot_raw=int(tot_raw),
                    timestamp_canonical=int(timestamp),
                )


def _fit_linear(arrays: _DelayArrays) -> dict[str, float]:
    x = arrays.pixel_tot - arrays.reference_tot
    denominator = float(np.sum(arrays.count * x * x))
    if denominator == 0:
        raise ValueError("linear time-walk fit has no ToT variation")
    m = float(np.sum(x * arrays.delay_sum) / denominator)
    return {"m": m}


def _fit_inverse(arrays: _DelayArrays) -> dict[str, float]:
    log_b_values = np.linspace(math.log(0.01), math.log(4096.0), 320)
    errors = np.asarray(
        [
            _inverse_fit_for_b(arrays, math.exp(log_b))[1]
            for log_b in log_b_values
        ]
    )
    best_index = int(np.argmin(errors))
    lower_index = max(0, best_index - 1)
    upper_index = min(len(log_b_values) - 1, best_index + 1)
    lower = float(log_b_values[lower_index])
    upper = float(log_b_values[upper_index])
    if lower == upper:
        best_b = math.exp(float(log_b_values[best_index]))
        best_a, _ = _inverse_fit_for_b(arrays, best_b)
        return {"a": best_a, "b": best_b}

    golden_ratio = (math.sqrt(5) - 1) / 2
    left = upper - golden_ratio * (upper - lower)
    right = lower + golden_ratio * (upper - lower)
    for _ in range(60):
        left_error = _inverse_fit_for_b(arrays, math.exp(left))[1]
        right_error = _inverse_fit_for_b(arrays, math.exp(right))[1]
        if left_error <= right_error:
            upper = right
            right = left
            left = upper - golden_ratio * (upper - lower)
        else:
            lower = left
            left = right
            right = lower + golden_ratio * (upper - lower)

    best_b = math.exp((lower + upper) / 2)
    best_a, _ = _inverse_fit_for_b(arrays, best_b)
    return {"a": best_a, "b": best_b}


def _inverse_fit_for_b(
    arrays: _DelayArrays,
    b: float,
) -> tuple[float, float]:
    x = (
        1.0 / (arrays.pixel_tot + b)
        - 1.0 / (arrays.reference_tot + b)
    )
    denominator = float(np.sum(arrays.count * x * x))
    if denominator == 0:
        return 0.0, math.inf
    a = float(np.sum(x * arrays.delay_sum) / denominator)
    prediction = a * x
    error = _sum_squared_error(arrays, prediction)
    return a, error


def _predict(
    arrays: _DelayArrays,
    model: Literal["linear", "inverse"],
    parameters: dict[str, float],
) -> np.ndarray:
    if model == "linear":
        return parameters["m"] * (
            arrays.pixel_tot - arrays.reference_tot
        )
    return parameters["a"] * (
        1.0 / (arrays.pixel_tot + parameters["b"])
        - 1.0 / (arrays.reference_tot + parameters["b"])
    )


def _sum_squared_error(
    arrays: _DelayArrays,
    prediction: np.ndarray,
) -> float:
    return float(
        np.sum(
            arrays.delay_square_sum
            - 2 * prediction * arrays.delay_sum
            + arrays.count * prediction * prediction
        )
    )


def _rmse(
    arrays: _DelayArrays,
    model: Literal["linear", "inverse"],
    parameters: dict[str, float],
) -> float:
    prediction = _predict(arrays, model, parameters)
    return math.sqrt(
        max(0.0, _sum_squared_error(arrays, prediction))
        / float(np.sum(arrays.count))
    )


def _fit_model(
    arrays: _DelayArrays,
    model: Literal["linear", "inverse"],
) -> dict[str, float]:
    if model == "linear":
        return _fit_linear(arrays)
    return _fit_inverse(arrays)


def _held_out_rmse(
    arrays: _DelayArrays,
    model: Literal["linear", "inverse"],
) -> float:
    squared_error = 0.0
    pair_count = 0.0
    blocks = sorted(set(int(value) for value in arrays.time_block))
    if len(blocks) < 2:
        parameters = _fit_model(arrays, model)
        return _rmse(arrays, model, parameters)

    for block in blocks:
        held_out_mask = arrays.time_block == block
        training = arrays.subset(~held_out_mask)
        held_out = arrays.subset(held_out_mask)
        parameters = _fit_model(training, model)
        prediction = _predict(held_out, model, parameters)
        squared_error += _sum_squared_error(held_out, prediction)
        pair_count += float(np.sum(held_out.count))
    return math.sqrt(max(0.0, squared_error) / pair_count)


def _subset_fits(
    arrays: _DelayArrays,
    model: Literal["linear", "inverse"],
) -> list[TimewalkSubsetFit]:
    fits: list[TimewalkSubsetFit] = []
    for block in sorted(set(int(value) for value in arrays.time_block)):
        subset = arrays.subset(arrays.time_block == block)
        fits.append(
            TimewalkSubsetFit(
                time_block=block,
                parameters=_fit_model(subset, model),
            )
        )
    return fits


def _build_tot_bins(
    arrays: _DelayArrays,
    linear_parameters: dict[str, float],
    inverse_parameters: dict[str, float],
) -> list[TimewalkTotBin]:
    bins: list[TimewalkTotBin] = []
    for tot_raw in sorted(set(int(value) for value in arrays.pixel_tot)):
        subset = arrays.subset(arrays.pixel_tot == tot_raw)
        pair_count = int(np.sum(subset.count))
        observed = float(np.sum(subset.delay_sum) / pair_count)
        linear_prediction = float(
            np.sum(
                subset.count
                * _predict(subset, "linear", linear_parameters)
            )
            / pair_count
        )
        inverse_prediction = float(
            np.sum(
                subset.count
                * _predict(subset, "inverse", inverse_parameters)
            )
            / pair_count
        )
        bins.append(
            TimewalkTotBin(
                tot_raw=tot_raw,
                pair_count=pair_count,
                mean_relative_delay_ticks=observed,
                linear_prediction_ticks=linear_prediction,
                inverse_prediction_ticks=inverse_prediction,
                linear_residual_ticks=observed - linear_prediction,
                inverse_residual_ticks=observed - inverse_prediction,
            )
        )
    return bins


def _residual_correlation(
    bins: list[TimewalkTotBin],
    model: Literal["linear", "inverse"],
) -> float:
    if len(bins) < 2:
        return 0.0
    x = np.asarray([value.tot_raw for value in bins], dtype=np.float64)
    residuals = np.asarray(
        [
            (
                value.linear_residual_ticks
                if model == "linear"
                else value.inverse_residual_ticks
            )
            for value in bins
        ],
        dtype=np.float64,
    )
    weights = np.asarray(
        [value.pair_count for value in bins],
        dtype=np.float64,
    )
    x_mean = float(np.average(x, weights=weights))
    residual_mean = float(np.average(residuals, weights=weights))
    covariance = float(
        np.sum(weights * (x - x_mean) * (residuals - residual_mean))
    )
    x_variance = float(np.sum(weights * (x - x_mean) ** 2))
    residual_variance = float(
        np.sum(weights * (residuals - residual_mean) ** 2)
    )
    if x_variance == 0 or residual_variance == 0:
        return 0.0
    return covariance / math.sqrt(x_variance * residual_variance)


def _select_model(
    linear_fit: TimewalkCandidateFit,
    inverse_fit: TimewalkCandidateFit,
) -> tuple[Literal["linear", "inverse"], str]:
    if linear_fit.held_out_rmse_ticks == 0:
        return (
            "linear",
            "linear retained because it has zero held-out error",
        )
    improvement = (
        linear_fit.held_out_rmse_ticks - inverse_fit.held_out_rmse_ticks
    ) / linear_fit.held_out_rmse_ticks
    inverse_residual_is_better = abs(
        inverse_fit.residual_tot_correlation
    ) < abs(linear_fit.residual_tot_correlation)
    if improvement >= 0.05 and inverse_residual_is_better:
        return (
            "inverse",
            "inverse held-out RMSE improved by at least 5 percent and left "
            "less ToT-dependent residual correlation",
        )
    return (
        "linear",
        "linear retained because the inverse model did not produce both a "
        "5 percent held-out RMSE improvement and lower residual correlation",
    )


def _weighted_percentile(
    values: np.ndarray,
    weights: np.ndarray,
    fraction: float,
) -> float:
    order = np.argsort(values)
    sorted_values = values[order]
    cumulative = np.cumsum(weights[order])
    threshold = fraction * float(cumulative[-1])
    index = min(
        int(np.searchsorted(cumulative, threshold, side="left")),
        len(sorted_values) - 1,
    )
    return float(sorted_values[index])


def _write_comparison_plot(
    bins: list[TimewalkTotBin],
    linear_fit: TimewalkCandidateFit,
    inverse_fit: TimewalkCandidateFit,
    output_path: Path,
) -> None:
    minimum_plot_count = max(
        100,
        round(max(value.pair_count for value in bins) * 0.0001),
    )
    plotted_bins = [
        value for value in bins if value.pair_count >= minimum_plot_count
    ]
    tot = [value.tot_raw for value in plotted_bins]
    observed = [value.mean_relative_delay_ticks for value in plotted_bins]
    linear_prediction = [
        value.linear_prediction_ticks for value in plotted_bins
    ]
    inverse_prediction = [
        value.inverse_prediction_ticks for value in plotted_bins
    ]
    linear_residual = [
        value.linear_residual_ticks for value in plotted_bins
    ]
    inverse_residual = [
        value.inverse_residual_ticks for value in plotted_bins
    ]

    figure, axes = plt.subplots(2, 1, figsize=(9, 8), sharex=True)
    axes[0].scatter(tot, observed, s=8, alpha=0.5, label="binned data")
    axes[0].plot(tot, linear_prediction, label="linear")
    axes[0].plot(tot, inverse_prediction, label="inverse")
    axes[0].set_ylabel("Relative delay (canonical ticks)")
    axes[0].set_title(
        "Cluster-relative ToA versus ToT\n"
        f"held-out RMSE: linear={linear_fit.held_out_rmse_ticks:.3g}, "
        f"inverse={inverse_fit.held_out_rmse_ticks:.3g}; "
        f"bins shown have at least {minimum_plot_count} pairs"
    )
    axes[0].legend()
    axes[0].grid(alpha=0.2)

    axes[1].plot(tot, linear_residual, label="linear residual")
    axes[1].plot(tot, inverse_residual, label="inverse residual")
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_xlabel("Pixel ToT (raw)")
    axes[1].set_ylabel("Residual (canonical ticks)")
    axes[1].legend()
    axes[1].grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _relative_pixel_path(path: Path) -> Path:
    if path.parent.name == "pixel_hits":
        return Path("pixel_hits") / path.name
    return path
