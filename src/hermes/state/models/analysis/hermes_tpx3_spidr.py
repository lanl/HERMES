from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from hermes.state.models.shared_models import (
    BinaryProgram,
    FileReference,
    ResultStatus,
    StrictBaseModel,
)

# Canonical parquet-category subdirectory names the unpacker writes under the
# unpacking output directory. The unpacker binary creates these directories;
# this mapping lets HERMES validate the relative paths reported in its summary.
TPX3_PARQUET_CATEGORY_DIRECTORIES = {
    "pixel_data": "pixel_hits",
    "tdc_timestamps": "tdc_triggers",
    "heartbeat_packets": "global_timestamps",
    "control_packets": "control_packets",
    "unrecognized_packets": "unrecognized_packets",
}
SortingStrategy = Literal["in_memory", "external_merge"]
ClusteringAlgorithm = Literal["connected_components", "dbscan"]
PhotonTimeEstimator = Literal[
    "leading_edge",
    "brightest",
    "mean",
    "tot_weighted",
]


def _expand_file_list(value: object) -> object:
    """Expand a ``{"file_list": path}`` mapping into a list of file entries.

    Each non-empty, non-comment line of the referenced text file becomes one
    ``{"path": ...}`` entry. Relative lines resolve against the list's own
    directory. Any other value passes through unchanged.
    """
    if not isinstance(value, dict) or "file_list" not in value:
        return value

    if set(value) != {"file_list"}:
        raise ValueError("the file-list form must contain only file_list")

    file_list_value = value["file_list"]
    if not isinstance(file_list_value, str | Path):
        raise ValueError("file_list must be a file path")

    file_list_path = Path(file_list_value).expanduser().resolve(strict=False)
    try:
        lines = file_list_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read file list: {file_list_path}") from exc

    files: list[dict[str, Path]] = []
    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        path = Path(entry).expanduser()
        if not path.is_absolute():
            path = file_list_path.parent / path
        files.append({"path": path.resolve(strict=False)})

    if not files:
        raise ValueError(f"file list contains no file paths: {file_list_path}")

    return files


def _expand_results_list(value: object) -> object:
    """Expand a ``{"results_file": path}`` mapping into a list of result entries.

    Each non-blank line of the referenced JSON-lines file is one result entry,
    parsed straight back into a mapping the stage's result model validates. The
    paths inside each entry are written by HERMES and kept verbatim, so a saved
    and reloaded record holds the identical results. Any other value passes
    through unchanged.
    """
    if not isinstance(value, dict) or "results_file" not in value:
        return value

    if set(value) != {"results_file"}:
        raise ValueError("the results-file form must contain only results_file")

    results_file_value = value["results_file"]
    if not isinstance(results_file_value, str | Path):
        raise ValueError("results_file must be a file path")

    results_file_path = Path(results_file_value).expanduser().resolve(strict=False)
    try:
        lines = results_file_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read results file: {results_file_path}") from exc

    entries: list[object] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            entries.append(json.loads(text))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"results file has an invalid JSON line: {results_file_path}"
            ) from exc

    if not entries:
        raise ValueError(f"results file contains no entries: {results_file_path}")

    return entries


class HermesTpx3PhotonClusteringSettings(StrictBaseModel):
    max_time_spread_ticks: int = Field(
        gt=0,
        description="Longest time from a photon's first pixel to its last, in "
        "ticks of 25 ns / 12288 (491520 ticks is 1 microsecond).",
    )
    min_cluster_size: int = Field(
        gt=0,
        description="Fewest pixels a photon may have; no larger than "
        "max_cluster_size.",
    )
    max_cluster_size: int = Field(gt=0, description="Most pixels a photon may have.")
    min_pixel_tot_raw: int = Field(
        ge=0,
        le=1023,
        description="Pixels with a smaller tot_raw are dropped before clustering.",
    )
    min_cluster_tot_raw: int = Field(
        ge=0,
        description="Smallest sum of tot_raw over a photon's pixels; no larger "
        "than max_cluster_tot_raw.",
    )
    max_cluster_tot_raw: int = Field(
        ge=0, description="Largest sum of tot_raw over a photon's pixels."
    )
    max_aspect_ratio: float = Field(
        ge=1,
        description="Largest ratio of the long side to the short side of a "
        "photon's bounding box; rejects long tracks.",
    )
    min_filled_fraction: float = Field(
        gt=0,
        le=1,
        description="Smallest share of a photon's bounding box that its pixels "
        "must fill; rejects sparse clusters.",
    )
    adjacency: Literal[4, 8] = Field(
        default=8,
        description="4: pixels join when they share a side. 8: corners count too.",
    )
    position_averaging: Literal["arithmetic"] = Field(
        default="arithmetic",
        description="How a photon's x and y are found; only the plain mean of "
        "its pixels for now.",
    )
    photon_time_estimator: PhotonTimeEstimator = Field(
        default="leading_edge",
        description="How a photon's time is found; only leading_edge (its "
        "earliest pixel) runs for now.",
    )
    timewalk_calibration_file: Literal["default"] | Path | None = Field(
        default=None,
        description='Time-walk correction of photon times: "default" uses the '
        "calibration shipped with HERMES, a path uses that JSON file, and null "
        "turns the correction off.",
    )

    @field_validator("photon_time_estimator")
    @classmethod
    def reject_reserved_time_estimators(
        cls,
        value: PhotonTimeEstimator,
    ) -> PhotonTimeEstimator:
        if value != "leading_edge":
            raise ValueError(
                f"photon_time_estimator={value!r} is reserved and not implemented"
            )
        return value

    @model_validator(mode="after")
    def require_ordered_bounds(self) -> HermesTpx3PhotonClusteringSettings:
        if self.min_cluster_size > self.max_cluster_size:
            raise ValueError(
                "min_cluster_size must be less than or equal to max_cluster_size"
            )
        if self.min_cluster_tot_raw > self.max_cluster_tot_raw:
            raise ValueError(
                "min_cluster_tot_raw must be less than or equal to "
                "max_cluster_tot_raw"
            )
        return self


class HermesTpx3PhotonClustering(StrictBaseModel):
    # Groups the clustering choice: which algorithm runs, whether to also save
    # the source pixels of each photon, and the algorithm's numeric settings.
    name: ClusteringAlgorithm = Field(
        default="connected_components",
        description="Only connected_components runs; dbscan is not available yet.",
    )
    save_photon_pixels: bool = Field(
        default=False,
        description="Also write pixel_clusters/ files that list each photon's "
        "pixels.",
    )
    settings: HermesTpx3PhotonClusteringSettings


# Fixed detector width in pixels; the event grid spans one 256 x 256 chip. Used
# to derive the spatial-grid cell width the same way the C++ binary does.
EVENT_CHIP_WIDTH_PIXELS = 256


class HermesTpx3EventReconstructionSettings(StrictBaseModel):
    # One field per key the event-reconstructor binary reads, with the same
    # bounds its validateReconParams enforces. model_dump(mode="json") produces
    # exactly these keys, which is what is written to the binary's settings file.
    spatial_link_radius_pixels: float = Field(
        gt=0,
        description="Photons this close or closer, in sensor pixels, can join "
        "one event.",
    )
    spatial_cells_per_axis: int = Field(
        ge=1,
        le=EVENT_CHIP_WIDTH_PIXELS,
        description="Grid cells per axis used to find nearby photons quickly; it "
        "changes speed, not the events. 256 / spatial_cells_per_axis, rounded "
        "up, must be at least spatial_link_radius_pixels.",
    )
    max_time_difference_ticks: float = Field(
        gt=0,
        description="Photons this close in time or closer, in ticks of "
        "25 ns / 12288, can join one event (4915200 ticks is 10 microseconds).",
    )
    max_event_duration_ticks: float = Field(
        gt=0,
        description="Events that last longer, in ticks, get the "
        "duration_exceeded flag and are kept (14745600 ticks is 30 "
        "microseconds).",
    )
    min_photon_count: int = Field(
        ge=1,
        description="Recorded for later analysis only; events with fewer "
        "photons are still kept.",
    )
    save_event_photons: bool = Field(
        default=False,
        description="Also write event_photons/ files that list each event's "
        "photons.",
    )

    @model_validator(mode="after")
    def require_cell_width_at_least_link_radius(
        self,
    ) -> HermesTpx3EventReconstructionSettings:
        # The binary rejects a grid so fine that the derived cell width falls
        # below the linking radius, because its fixed 3x3 cell search would then
        # miss genuine neighbors. Mirror that here so an invalid grid is caught
        # before the binary runs. The cell width rounds up, matching the binary.
        cell_width = -(-EVENT_CHIP_WIDTH_PIXELS // self.spatial_cells_per_axis)
        if cell_width < self.spatial_link_radius_pixels:
            raise ValueError(
                "spatial_cells_per_axis is too large for "
                "spatial_link_radius_pixels: the derived cell width would be "
                "smaller than the linking radius"
            )
        return self


# ---------------------------------------------------------------------------
# Unpacker summary (parsed from the unpacker binary's summary JSON)
# ---------------------------------------------------------------------------


class Tpx3MeasurementInfoSummary(StrictBaseModel):
    # The measurement identity the binary copies from --measurement-id and --run
    # so the summary names the measurement and run it belongs to.
    measurement_id: str = Field(min_length=1)
    run: str = Field(min_length=1)


class Tpx3SpidrUnpackingSummary(StrictBaseModel):
    bytes_read: int = Field(ge=0)
    chunks_read: int = Field(ge=0)
    packets_read: int = Field(ge=0)
    pixel_data_packets: int = Field(ge=0)
    tdc_timestamps: int = Field(ge=0)
    heartbeat_packets: int = Field(ge=0)
    spidr_control_packets: int = Field(ge=0)
    tpx3_control_packets: int = Field(ge=0)
    unrecognized_packets: int = Field(ge=0)
    tdc1_rising: int = Field(ge=0)
    tdc1_falling: int = Field(ge=0)
    tdc2_rising: int = Field(ge=0)
    tdc2_falling: int = Field(ge=0)
    unknown_tdc_edges: int = Field(ge=0)
    errors: list[str]
    warnings: list[str]


class Tpx3SpidrHeartbeatPairsSummary(StrictBaseModel):
    number_of_beats: int = Field(ge=0)
    # The earliest and latest global timestamp in the file, over all chips, in
    # canonical ticks; None when the file has none.
    first_timestamp_canonical: int | None = Field(default=None, ge=0)
    last_timestamp_canonical: int | None = Field(default=None, ge=0)
    # The global timestamp from an earlier raw file that the runner gave with
    # --previous-global-timestamp; None when it was not given.
    previous_file_timestamp_canonical: int | None = Field(default=None, ge=0)


class Tpx3SpidrTimeAdjustmentsSummary(StrictBaseModel):
    pixel_packets: int = Field(ge=0)
    tdc_packets: int = Field(ge=0)
    control_packets: int = Field(ge=0)
    failed: int = Field(ge=0)


class Tpx3SpidrTimestampProcessingSummary(StrictBaseModel):
    heartbeat_pairs: Tpx3SpidrHeartbeatPairsSummary
    time_adjustments: Tpx3SpidrTimeAdjustmentsSummary


class Tpx3SpidrSortingSummary(StrictBaseModel):
    strategy: SortingStrategy
    memory_budget_bytes: int = Field(ge=0)
    estimated_memory_bytes: int = Field(ge=0)
    sorting_time_seconds: float = Field(ge=0)


class Tpx3SpidrParquetCategorySummary(StrictBaseModel):
    row_count: int = Field(ge=0)
    files: list[Path]

    @model_validator(mode="after")
    def require_files_for_saved_rows(self) -> Tpx3SpidrParquetCategorySummary:
        if self.row_count == 0 and self.files:
            raise ValueError("a category with zero rows cannot list Parquet files")
        if self.row_count > 0 and not self.files:
            raise ValueError("a category with saved rows must list a Parquet file")
        return self


class Tpx3SpidrOutputParquetSummary(StrictBaseModel):
    pixel_data: Tpx3SpidrParquetCategorySummary
    tdc_timestamps: Tpx3SpidrParquetCategorySummary
    heartbeat_packets: Tpx3SpidrParquetCategorySummary
    control_packets: Tpx3SpidrParquetCategorySummary
    unrecognized_packets: Tpx3SpidrParquetCategorySummary
    errors: list[str]

    @model_validator(mode="after")
    def require_category_directory(self) -> Tpx3SpidrOutputParquetSummary:
        # The binary writes each Parquet path as the analysis directory it was
        # given joined with the category subdirectory and filename, so every
        # path ends with ``<category-directory>/<filename>``. Check that
        # trailing directory segment without assuming where the analysis
        # directory itself lives.
        for field_name, expected_directory in (
            TPX3_PARQUET_CATEGORY_DIRECTORIES.items()
        ):
            category = getattr(self, field_name)
            for file_path in category.files:
                if ".." in file_path.parts:
                    raise ValueError(
                        f"{field_name} Parquet paths must not contain '..'"
                    )
                if file_path.parent.name != expected_directory:
                    raise ValueError(
                        f"{field_name} Parquet paths must sit in a "
                        f"{expected_directory}/ directory"
                    )
        return self


class Tpx3SpidrThroughputSummary(StrictBaseModel):
    packets_per_second: float = Field(ge=0)
    megabytes_per_second: float = Field(ge=0)


class Tpx3SpidrProcessingTimesSummary(StrictBaseModel):
    canonical_time_seconds: float = Field(gt=0)
    unpacking: float = Field(ge=0)
    canonical_conversion: float = Field(ge=0)
    time_adjustments: float = Field(ge=0)
    sorting: float = Field(ge=0)
    parquet_writing: float = Field(ge=0)
    total: float = Field(ge=0)
    throughput: Tpx3SpidrThroughputSummary


class Tpx3SpidrSummary(StrictBaseModel):
    measurement_info: Tpx3MeasurementInfoSummary
    inputfile: Path
    unpacking: Tpx3SpidrUnpackingSummary
    timestamp_processing: Tpx3SpidrTimestampProcessingSummary
    sorting: Tpx3SpidrSortingSummary
    output_parquet: Tpx3SpidrOutputParquetSummary
    processing_times_seconds: Tpx3SpidrProcessingTimesSummary


# ---------------------------------------------------------------------------
# Reconstruction summary (parsed from the clusterer binary's sidecar JSON)
# ---------------------------------------------------------------------------


class HermesTpx3PhotonRejectionCountsSummary(StrictBaseModel):
    below_min_cluster_size: int = Field(ge=0)
    above_max_cluster_size: int = Field(ge=0)
    below_min_cluster_tot: int = Field(ge=0)
    above_max_cluster_tot: int = Field(ge=0)
    above_max_aspect_ratio: int = Field(ge=0)
    below_min_filled_fraction: int = Field(ge=0)


class HermesTpx3PhotonQualityFlagCountsSummary(StrictBaseModel):
    saturated_pixel: int = Field(ge=0)
    bridged_components: int = Field(ge=0)


class HermesTpx3PhotonReconstructionCountsSummary(StrictBaseModel):
    pixels_read: int = Field(ge=0)
    clusters_formed: int = Field(ge=0)
    rejected_clusters: int = Field(ge=0)
    rejection_reasons: HermesTpx3PhotonRejectionCountsSummary
    quality_flag_counts: HermesTpx3PhotonQualityFlagCountsSummary
    warnings: list[str]
    errors: list[str]
    total_photons: int = Field(ge=0)

    @model_validator(mode="after")
    def require_cluster_counts_to_match(
        self,
    ) -> HermesTpx3PhotonReconstructionCountsSummary:
        if self.total_photons + self.rejected_clusters != self.clusters_formed:
            raise ValueError(
                "clusters_formed must equal total_photons plus rejected_clusters"
            )
        if (
            self.quality_flag_counts.saturated_pixel > self.total_photons
            or self.quality_flag_counts.bridged_components > self.total_photons
        ):
            raise ValueError("quality flag counts cannot exceed total_photons")
        return self


class HermesTpx3PhotonClusteringEchoSummary(StrictBaseModel):
    # The clustering algorithm and the complete settings the run used, echoed by
    # the binary. The binary owns the settings shape and renders it verbatim, so
    # it is kept as a plain mapping rather than re-validated field by field.
    algorithm: ClusteringAlgorithm
    settings: dict[str, float | int | bool | str | None]


class HermesTpx3PhotonTimingSummary(StrictBaseModel):
    estimator: PhotonTimeEstimator
    correction_model: Literal["none", "inverse", "linear"]
    calibration_file: Path | None
    parameters: dict[str, float]
    high_tot_anchor: float | None


class HermesTpx3PhotonParquetCategorySummary(StrictBaseModel):
    row_count: int = Field(ge=0)
    files: list[Path]

    @model_validator(mode="after")
    def require_files_for_saved_rows(
        self,
    ) -> HermesTpx3PhotonParquetCategorySummary:
        if self.row_count == 0 and self.files:
            raise ValueError("a table with zero rows cannot list Parquet files")
        if self.row_count > 0 and not self.files:
            raise ValueError("a table with saved rows must list a Parquet file")
        return self


class HermesTpx3PhotonPixelClustersSummary(StrictBaseModel):
    requested: bool
    row_count: int = Field(ge=0)
    files: list[Path]

    @model_validator(mode="after")
    def require_files_for_saved_rows(
        self,
    ) -> HermesTpx3PhotonPixelClustersSummary:
        if self.row_count == 0 and self.files:
            raise ValueError("a table with zero rows cannot list Parquet files")
        if self.row_count > 0 and not self.files:
            raise ValueError("a table with saved rows must list a Parquet file")
        return self


class HermesTpx3PhotonParquetSummary(StrictBaseModel):
    input_pixel_data_file: list[Path]
    photons: HermesTpx3PhotonParquetCategorySummary
    pixel_clusters: HermesTpx3PhotonPixelClustersSummary


class HermesTpx3PhotonThroughputSummary(StrictBaseModel):
    pixels_per_second: float = Field(ge=0)
    photons_per_second: float = Field(ge=0)


class HermesTpx3PhotonProcessingTimesSummary(StrictBaseModel):
    parquet_reading: float = Field(ge=0)
    clustering_and_filtering: float = Field(ge=0)
    parquet_writing: float = Field(ge=0)
    total: float = Field(ge=0)
    throughput: HermesTpx3PhotonThroughputSummary


class HermesTpx3PhotonReconstructionSummary(StrictBaseModel):
    measurement_info: Tpx3MeasurementInfoSummary
    reconstruction: HermesTpx3PhotonReconstructionCountsSummary
    clustering: HermesTpx3PhotonClusteringEchoSummary
    photon_timing: HermesTpx3PhotonTimingSummary
    parquet_files: HermesTpx3PhotonParquetSummary
    processing_times_seconds: HermesTpx3PhotonProcessingTimesSummary


# ---------------------------------------------------------------------------
# Event reconstruction summary (parsed from the event-reconstructor binary JSON)
# ---------------------------------------------------------------------------


class HermesTpx3EventQualityFlagCountsSummary(StrictBaseModel):
    single_photon: int = Field(ge=0)
    duration_exceeded: int = Field(ge=0)


class HermesTpx3EventReconstructionCountsSummary(StrictBaseModel):
    photons_read: int = Field(ge=0)
    components_formed: int = Field(ge=0)
    event_count: int = Field(ge=0)
    quality_flag_counts: HermesTpx3EventQualityFlagCountsSummary
    min_photon_count_below: int = Field(ge=0)
    warnings: list[str]
    errors: list[str]

    @model_validator(mode="after")
    def require_event_counts_to_match(
        self,
    ) -> HermesTpx3EventReconstructionCountsSummary:
        # Every closed component becomes exactly one event; the stage records
        # min_photon_count_below but never discards, so these counts are equal.
        if self.event_count != self.components_formed:
            raise ValueError("event_count must equal components_formed")
        # Components partition the photons and each holds at least one photon, so
        # there can be no more events than photons.
        if self.event_count > self.photons_read:
            raise ValueError("event_count cannot exceed photons_read")
        # Each per-event count is a subset of the events.
        for name, value in (
            ("single_photon", self.quality_flag_counts.single_photon),
            ("duration_exceeded", self.quality_flag_counts.duration_exceeded),
            ("min_photon_count_below", self.min_photon_count_below),
        ):
            if value > self.event_count:
                raise ValueError(f"{name} cannot exceed event_count")
        return self


class HermesTpx3EventClusteringSummary(StrictBaseModel):
    algorithm: ClusteringAlgorithm
    # The binary owns its settings shape and renders it verbatim, so this is kept
    # as a plain mapping rather than re-validated field by field. For
    # connected_components it carries the six settings keys plus the derived cell
    # width the binary reports for diagnostics.
    settings: dict[str, float | int | bool]


class HermesTpx3EventTimingSummary(StrictBaseModel):
    estimator: Literal["earliest_photon"] = "earliest_photon"


class HermesTpx3EventParquetCategorySummary(StrictBaseModel):
    row_count: int = Field(ge=0)
    files: list[Path]

    @model_validator(mode="after")
    def require_files_for_saved_rows(self) -> HermesTpx3EventParquetCategorySummary:
        if self.row_count == 0 and self.files:
            raise ValueError("a category with zero rows cannot list Parquet files")
        if self.row_count > 0 and not self.files:
            raise ValueError("a category with saved rows must list a Parquet file")
        return self


class HermesTpx3EventParquetSummary(StrictBaseModel):
    input_photon_events_files: list[Path]
    event_candidates: HermesTpx3EventParquetCategorySummary
    # event_photons is present only when save_event_photons was set.
    event_photons: HermesTpx3EventParquetCategorySummary | None = None


class HermesTpx3EventThroughputSummary(StrictBaseModel):
    photons_per_second: float = Field(ge=0)
    events_per_second: float = Field(ge=0)


class HermesTpx3EventProcessingTimesSummary(StrictBaseModel):
    photon_reading: float = Field(ge=0)
    clustering: float = Field(ge=0)
    parquet_writing: float = Field(ge=0)
    total: float = Field(ge=0)
    throughput: HermesTpx3EventThroughputSummary


class HermesTpx3EventReconstructionSummary(StrictBaseModel):
    schema_version: Literal[1] = 1
    reconstruction: HermesTpx3EventReconstructionCountsSummary
    clustering: HermesTpx3EventClusteringSummary
    event_timing: HermesTpx3EventTimingSummary
    parquet: HermesTpx3EventParquetSummary
    processing_times_seconds: HermesTpx3EventProcessingTimesSummary


# ---------------------------------------------------------------------------
# Per-file results
# ---------------------------------------------------------------------------


class HermesTpx3UnpackingResult(StrictBaseModel):
    input_file: FileReference
    status: ResultStatus


class HermesTpx3PhotonReconstructionResult(StrictBaseModel):
    input_file: FileReference
    output_file: Path
    status: ResultStatus
    counts: HermesTpx3PhotonReconstructionCountsSummary | None = None


class HermesTpx3EventReconstructionResult(StrictBaseModel):
    # Event reconstruction is whole-sensor: one result per raw TPX3 filename
    # stem, covering every chip's photons together, rather than one per file.
    raw_file_stem: str
    output_file: Path
    status: ResultStatus
    counts: HermesTpx3EventReconstructionCountsSummary | None = None


# ---------------------------------------------------------------------------
# Stage containers
# ---------------------------------------------------------------------------


class Tpx3UnpackingRuntimeOptions(StrictBaseModel):
    overwrite: bool = Field(
        default=False,
        description="Unpack a raw file again even when its outputs already "
        "exist; otherwise it is skipped.",
    )
    time_sort: bool = Field(
        default=True,
        description="Sort each output file by timestamp_canonical.",
    )
    delete_raw_after_unpack: bool = Field(
        default=False,
        description="Delete each raw .tpx3 file after it unpacks without "
        "error, to free disk space. While the camera is recording, files are "
        "kept until the recording ends, since SERVAL may still be writing them. "
        "This cannot be undone.",
    )


class Tpx3Unpacking(StrictBaseModel):
    program: BinaryProgram = Field(
        description="The unpacker: name tpx3-spidr-cpp, executable_path "
        "hermes-tpx3-spidr.",
    )
    tpx3_files: Literal["auto"] | list[FileReference] = Field(
        default="auto",
        description='"auto": every .tpx3 in environment.raw_data_directory. Or a '
        "list of {path: ...} entries, or {file_list: <text file with one path "
        "per line>}.",
    )
    runtime_options: Tpx3UnpackingRuntimeOptions = Field(
        default_factory=Tpx3UnpackingRuntimeOptions
    )
    results: list[HermesTpx3UnpackingResult] = Field(default_factory=list)

    @field_validator("tpx3_files", mode="before")
    @classmethod
    def expand_tpx3_file_list(cls, value: object) -> object:
        return _expand_file_list(value)

    @field_validator("tpx3_files", mode="after")
    @classmethod
    def require_non_empty_file_list(cls, value: object) -> object:
        if isinstance(value, list) and not value:
            raise ValueError(
                "tpx3_files must be 'auto' or a non-empty file list"
            )
        return value

    @field_validator("results", mode="before")
    @classmethod
    def expand_results_list(cls, value: object) -> object:
        return _expand_results_list(value)

    @model_validator(mode="after")
    def require_unique_stems(self) -> Tpx3Unpacking:
        if not isinstance(self.tpx3_files, list):
            return self
        stems = [raw_file.path.stem for raw_file in self.tpx3_files]
        duplicate_stems = sorted(
            stem for stem in set(stems) if stems.count(stem) > 1
        )
        if duplicate_stems:
            raise ValueError(
                "raw TPX3 filename stems must be unique: "
                + ", ".join(duplicate_stems)
            )
        return self


class HermesTpx3PhotonReconstructionRuntimeOptions(StrictBaseModel):
    overwrite: bool = Field(
        default=False,
        description="Redo a pixel file even when its outputs already exist; "
        "otherwise it is skipped.",
    )


class HermesTpx3PhotonReconstruction(StrictBaseModel):
    program: BinaryProgram = Field(
        description="The photon program: name photon-clusterer-cpp, "
        "executable_path hermes-photon-clusterer.",
    )
    pixel_files: Literal["auto"] | list[FileReference] = Field(
        default="auto",
        description='"auto": every file in pixel_hits/ in the analysis folder. '
        "Or a list of {path: ...} entries, or {file_list: <text file with one "
        "path per line>}.",
    )
    clustering_algorithm: HermesTpx3PhotonClustering
    runtime_options: HermesTpx3PhotonReconstructionRuntimeOptions = Field(
        default_factory=HermesTpx3PhotonReconstructionRuntimeOptions
    )
    results: list[HermesTpx3PhotonReconstructionResult] = Field(default_factory=list)

    @field_validator("pixel_files", mode="before")
    @classmethod
    def expand_pixel_file_list(cls, value: object) -> object:
        return _expand_file_list(value)

    @field_validator("pixel_files", mode="after")
    @classmethod
    def require_non_empty_file_list(cls, value: object) -> object:
        if isinstance(value, list) and not value:
            raise ValueError(
                "pixel_files must be 'auto' or a non-empty file list"
            )
        return value

    @field_validator("results", mode="before")
    @classmethod
    def expand_results_list(cls, value: object) -> object:
        return _expand_results_list(value)


class HermesTpx3EventReconstructionRuntimeOptions(StrictBaseModel):
    overwrite: bool = Field(
        default=False,
        description="Redo a raw file's events even when its outputs already "
        "exist; otherwise it is skipped.",
    )


class HermesTpx3EventReconstruction(StrictBaseModel):
    program: BinaryProgram = Field(
        description="The event program: name event-reconstructor-cpp, "
        "executable_path hermes-event-reconstructor.",
    )
    photon_parquet_files: Literal["auto"] | list[FileReference] = Field(
        default="auto",
        description='"auto": every file in photons/ in the analysis folder. Or a '
        "list of {path: ...} entries, or {file_list: <text file with one path "
        "per line>}.",
    )
    clustering_algorithm: ClusteringAlgorithm = Field(
        default="connected_components",
        description="Only connected_components runs; dbscan is not available yet.",
    )
    settings: HermesTpx3EventReconstructionSettings
    runtime_options: HermesTpx3EventReconstructionRuntimeOptions = Field(
        default_factory=HermesTpx3EventReconstructionRuntimeOptions
    )
    results: list[HermesTpx3EventReconstructionResult] = Field(
        default_factory=list
    )

    @field_validator("photon_parquet_files", mode="before")
    @classmethod
    def expand_photon_file_list(cls, value: object) -> object:
        return _expand_file_list(value)

    @field_validator("photon_parquet_files", mode="after")
    @classmethod
    def require_non_empty_file_list(cls, value: object) -> object:
        if isinstance(value, list) and not value:
            raise ValueError(
                "photon_parquet_files must be 'auto' or a non-empty file list"
            )
        return value

    @field_validator("results", mode="before")
    @classmethod
    def expand_results_list(cls, value: object) -> object:
        return _expand_results_list(value)


# ---------------------------------------------------------------------------
# Sensor layout
# ---------------------------------------------------------------------------


SensorLayoutKind = Literal["single_chip", "quad"]


class SensorLayout(StrictBaseModel):
    # How the detector's chips assemble into one sensor coordinate frame. A
    # single-chip camera uses its 256x256 pixel space unchanged; a quad tiles
    # four chips 2x2 with a four-pixel dead gap into a 516x516 sensor. Photon
    # reconstruction maps each chip's photon x/y into this shared frame so the
    # event stage can group light that lands on more than one chip. Named
    # SensorLayout to stay distinct from the SERVAL /detector/layout response
    # model (detector.py), which is a different concept.
    kind: SensorLayoutKind = Field(
        default="quad",
        description="quad: four chips tiled 2x2 into one 516x516 frame with a "
        "four-pixel gap. single_chip: one 256x256 chip.",
    )


# ---------------------------------------------------------------------------
# Analysis state
# ---------------------------------------------------------------------------


class HermesTpx3AnalysisState(StrictBaseModel):
    mode: Literal["hermes"] = Field(
        default="hermes",
        description="hermes runs the HERMES programs. (empir runs EMPIR and "
        "has other fields.)",
    )
    resource_limit_percent: int = Field(
        default=90,
        ge=1,
        le=100,
        description="Share of the CPU cores and free memory HERMES uses when it "
        "picks how many files to work on at once.",
    )
    detector_layout: SensorLayout = Field(
        default_factory=SensorLayout,
        description="How the chips fit together; photon and event x and y are "
        "in this frame.",
    )
    # Optional so reconstruction can run on its own when unpacking is already
    # done and the pixel/photon files it needs are already on disk.
    unpacking: Tpx3Unpacking | None = Field(
        default=None, description="Leave out to skip unpacking."
    )
    photon_reconstruction: HermesTpx3PhotonReconstruction | None = Field(
        default=None, description="Leave out to skip photon reconstruction."
    )
    event_reconstruction: HermesTpx3EventReconstruction | None = Field(
        default=None, description="Leave out to skip event reconstruction."
    )
