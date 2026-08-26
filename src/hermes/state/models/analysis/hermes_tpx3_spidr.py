from __future__ import annotations

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


class HermesTpx3PhotonClusteringSettings(StrictBaseModel):
    max_time_spread_ticks: int = Field(gt=0)
    min_cluster_size: int = Field(gt=0)
    max_cluster_size: int = Field(gt=0)
    min_pixel_tot_raw: int = Field(ge=0, le=1023)
    min_cluster_tot_raw: int = Field(ge=0)
    max_cluster_tot_raw: int = Field(ge=0)
    max_aspect_ratio: float = Field(ge=1)
    min_filled_fraction: float = Field(gt=0, le=1)
    adjacency: Literal[4, 8] = 8
    position_averaging: Literal["arithmetic"] = "arithmetic"
    photon_time_estimator: PhotonTimeEstimator = "leading_edge"
    timewalk_calibration_file: Path | None = None

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
    name: ClusteringAlgorithm = "connected_components"
    save_photon_pixels: bool = False
    settings: HermesTpx3PhotonClusteringSettings


# Fixed detector width in pixels; the event grid spans one 256 x 256 chip. Used
# to derive the spatial-grid cell width the same way the C++ binary does.
EVENT_CHIP_WIDTH_PIXELS = 256


class HermesTpx3EventReconstructionSettings(StrictBaseModel):
    # One field per key the event-reconstructor binary reads, with the same
    # bounds its validateReconParams enforces. model_dump(mode="json") produces
    # exactly these keys, which is what is written to the binary's settings file.
    spatial_link_radius_pixels: float = Field(gt=0)
    spatial_cells_per_axis: int = Field(ge=1, le=EVENT_CHIP_WIDTH_PIXELS)
    max_time_difference_ticks: float = Field(gt=0)
    max_event_duration_ticks: float = Field(gt=0)
    min_photon_count: int = Field(ge=1)
    save_event_photons: bool = False

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
    overwrite: bool = False
    time_sort: bool = True
    # Delete each raw .tpx3 file after it has been successfully unpacked, to
    # reclaim disk during long runs. Off by default; deletion is irreversible.
    delete_raw_after_unpack: bool = False


class Tpx3Unpacking(StrictBaseModel):
    program: BinaryProgram
    # "auto" gathers every *.tpx3 in the run's raw data directory; a list names
    # specific raw files to unpack.
    tpx3_files: Literal["auto"] | list[FileReference] = "auto"
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
    overwrite: bool = False


class HermesTpx3PhotonReconstruction(StrictBaseModel):
    program: BinaryProgram
    # "auto" gathers pixel files from the unpacking stage's output; a list names
    # specific pixel_hits Parquet files to reconstruct.
    pixel_files: Literal["auto"] | list[FileReference] = "auto"
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


class HermesTpx3EventReconstructionRuntimeOptions(StrictBaseModel):
    overwrite: bool = False


class HermesTpx3EventReconstruction(StrictBaseModel):
    program: BinaryProgram
    # "auto" gathers photon files from the photon reconstruction stage's output;
    # a list names specific photon_events Parquet files to reconstruct.
    photon_parquet_files: Literal["auto"] | list[FileReference] = "auto"
    clustering_algorithm: ClusteringAlgorithm = "connected_components"
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
    kind: SensorLayoutKind = "quad"


# ---------------------------------------------------------------------------
# Analysis state
# ---------------------------------------------------------------------------


class HermesTpx3AnalysisState(StrictBaseModel):
    mode: Literal["hermes"] = "hermes"
    resource_limit_percent: int = Field(default=90, ge=1, le=100)
    detector_layout: SensorLayout = Field(default_factory=SensorLayout)
    # Optional so reconstruction can run on its own when unpacking is already
    # done and the pixel/photon files it needs are already on disk.
    unpacking: Tpx3Unpacking | None = None
    photon_reconstruction: HermesTpx3PhotonReconstruction | None = None
    event_reconstruction: HermesTpx3EventReconstruction | None = None
