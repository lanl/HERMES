from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from hermes.state.models.shared_models import (
    BinaryProgram,
    FileReference,
    StrictBaseModel,
)

HermesTpx3RunStatus = Literal[
    "planned", "running", "completed", "skipped", "failed"
]

# Canonical parquet-category subdirectory names the unpacker writes under the
# unpacking output directory. The unpacker binary creates these directories;
# this mapping lets HERMES validate the relative paths reported in its summary.
TPX3_PARQUET_CATEGORY_DIRECTORIES = {
    "pixel_data": "pixelHits",
    "tdc_timestamps": "tdcTriggers",
    "heartbeat_packets": "globalTimestamps",
    "control_packets": "controlPackets",
    "unrecognized_packets": "unknownPackets",
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


class Tpx3PhotonClusteringSettings(StrictBaseModel):
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
    save_photon_pixels: bool = False

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
    def require_ordered_bounds(self) -> Tpx3PhotonClusteringSettings:
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


# Fixed detector width in pixels; the event grid spans one 256 x 256 chip. Used
# to derive the spatial-grid cell width the same way the C++ binary does.
EVENT_CHIP_WIDTH_PIXELS = 256


class Tpx3EventReconstructionSettings(StrictBaseModel):
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
    ) -> Tpx3EventReconstructionSettings:
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
# Unpacker summary (parsed from the unpacker binary's sidecar JSON)
# ---------------------------------------------------------------------------


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
    temporary_runs_created: int = Field(ge=0)


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


class Tpx3SpidrParquetSummary(StrictBaseModel):
    pixel_data: Tpx3SpidrParquetCategorySummary
    tdc_timestamps: Tpx3SpidrParquetCategorySummary
    heartbeat_packets: Tpx3SpidrParquetCategorySummary
    control_packets: Tpx3SpidrParquetCategorySummary
    unrecognized_packets: Tpx3SpidrParquetCategorySummary
    errors: list[str]

    @model_validator(mode="after")
    def require_category_relative_paths(self) -> Tpx3SpidrParquetSummary:
        for field_name, expected_directory in (
            TPX3_PARQUET_CATEGORY_DIRECTORIES.items()
        ):
            category = getattr(self, field_name)
            for file_path in category.files:
                if file_path.is_absolute() or ".." in file_path.parts:
                    raise ValueError(
                        f"{field_name} Parquet paths must be relative to the "
                        "analysis directory"
                    )
                if not file_path.parts or file_path.parts[0] != expected_directory:
                    raise ValueError(
                        f"{field_name} Parquet paths must begin with "
                        f"{expected_directory}/"
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
    unpacking: Tpx3SpidrUnpackingSummary
    timestamp_processing: Tpx3SpidrTimestampProcessingSummary
    sorting: Tpx3SpidrSortingSummary
    parquet: Tpx3SpidrParquetSummary
    processing_times_seconds: Tpx3SpidrProcessingTimesSummary


# ---------------------------------------------------------------------------
# Reconstruction summary (parsed from the clusterer binary's sidecar JSON)
# ---------------------------------------------------------------------------


class Tpx3PhotonRejectionCountsSummary(StrictBaseModel):
    below_min_cluster_size: int = Field(ge=0)
    above_max_cluster_size: int = Field(ge=0)
    below_min_cluster_tot: int = Field(ge=0)
    above_max_cluster_tot: int = Field(ge=0)
    above_max_aspect_ratio: int = Field(ge=0)
    below_min_filled_fraction: int = Field(ge=0)


class Tpx3PhotonQualityFlagCountsSummary(StrictBaseModel):
    saturated_pixel: int = Field(ge=0)
    bridged_components: int = Field(ge=0)


class Tpx3PhotonReconstructionCountsSummary(StrictBaseModel):
    pixel_rows_read: int = Field(ge=0)
    pixel_rows_below_min_tot: int = Field(ge=0)
    components_formed: int = Field(ge=0)
    photon_count: int = Field(ge=0)
    rejected_component_count: int = Field(ge=0)
    rejection_counts: Tpx3PhotonRejectionCountsSummary
    quality_flag_counts: Tpx3PhotonQualityFlagCountsSummary
    warnings: list[str]
    errors: list[str]

    @model_validator(mode="after")
    def require_component_counts_to_match(
        self,
    ) -> Tpx3PhotonReconstructionCountsSummary:
        if self.pixel_rows_below_min_tot > self.pixel_rows_read:
            raise ValueError(
                "pixel_rows_below_min_tot cannot exceed pixel_rows_read"
            )
        if (
            self.photon_count + self.rejected_component_count
            != self.components_formed
        ):
            raise ValueError(
                "components_formed must equal photon_count plus "
                "rejected_component_count"
            )
        if (
            self.quality_flag_counts.saturated_pixel > self.photon_count
            or self.quality_flag_counts.bridged_components > self.photon_count
        ):
            raise ValueError("quality flag counts cannot exceed photon_count")
        return self


class Tpx3PhotonThroughputSummary(StrictBaseModel):
    pixels_per_second: float = Field(ge=0)
    photons_per_second: float = Field(ge=0)


class Tpx3PhotonProcessingTimesSummary(StrictBaseModel):
    parquet_reading: float = Field(ge=0)
    clustering_and_filtering: float = Field(ge=0)
    parquet_writing: float = Field(ge=0)
    total: float = Field(ge=0)
    throughput: Tpx3PhotonThroughputSummary


class Tpx3PhotonReconstructionSummary(StrictBaseModel):
    schema_version: Literal[1] = 1
    reconstruction: Tpx3PhotonReconstructionCountsSummary
    processing_times_seconds: Tpx3PhotonProcessingTimesSummary


# ---------------------------------------------------------------------------
# Event reconstruction summary (parsed from the event-reconstructor binary JSON)
# ---------------------------------------------------------------------------


class Tpx3EventQualityFlagCountsSummary(StrictBaseModel):
    single_photon: int = Field(ge=0)
    duration_exceeded: int = Field(ge=0)


class Tpx3EventReconstructionCountsSummary(StrictBaseModel):
    photons_read: int = Field(ge=0)
    components_formed: int = Field(ge=0)
    event_count: int = Field(ge=0)
    quality_flag_counts: Tpx3EventQualityFlagCountsSummary
    min_photon_count_below: int = Field(ge=0)
    warnings: list[str]
    errors: list[str]

    @model_validator(mode="after")
    def require_event_counts_to_match(
        self,
    ) -> Tpx3EventReconstructionCountsSummary:
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


class Tpx3EventClusteringSummary(StrictBaseModel):
    algorithm: ClusteringAlgorithm
    # The binary owns its settings shape and renders it verbatim, so this is kept
    # as a plain mapping rather than re-validated field by field. For
    # connected_components it carries the six settings keys plus the derived cell
    # width the binary reports for diagnostics.
    settings: dict[str, float | int | bool]


class Tpx3EventTimingSummary(StrictBaseModel):
    estimator: Literal["earliest_photon"] = "earliest_photon"


class Tpx3EventParquetCategorySummary(StrictBaseModel):
    row_count: int = Field(ge=0)
    files: list[Path]

    @model_validator(mode="after")
    def require_files_for_saved_rows(self) -> Tpx3EventParquetCategorySummary:
        if self.row_count == 0 and self.files:
            raise ValueError("a category with zero rows cannot list Parquet files")
        if self.row_count > 0 and not self.files:
            raise ValueError("a category with saved rows must list a Parquet file")
        return self


class Tpx3EventParquetSummary(StrictBaseModel):
    input_photon_events_files: list[Path]
    event_candidates: Tpx3EventParquetCategorySummary
    # event_photons is present only when save_event_photons was set.
    event_photons: Tpx3EventParquetCategorySummary | None = None


class Tpx3EventThroughputSummary(StrictBaseModel):
    photons_per_second: float = Field(ge=0)
    events_per_second: float = Field(ge=0)


class Tpx3EventProcessingTimesSummary(StrictBaseModel):
    photon_reading: float = Field(ge=0)
    clustering: float = Field(ge=0)
    parquet_writing: float = Field(ge=0)
    total: float = Field(ge=0)
    throughput: Tpx3EventThroughputSummary


class Tpx3EventReconstructionSummary(StrictBaseModel):
    schema_version: Literal[1] = 1
    reconstruction: Tpx3EventReconstructionCountsSummary
    clustering: Tpx3EventClusteringSummary
    event_timing: Tpx3EventTimingSummary
    parquet: Tpx3EventParquetSummary
    processing_times_seconds: Tpx3EventProcessingTimesSummary


# ---------------------------------------------------------------------------
# Per-file results
# ---------------------------------------------------------------------------


class HermesTpx3UnpackingResult(StrictBaseModel):
    input_file: FileReference
    status: HermesTpx3RunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None


class HermesTpx3ReconstructionResult(StrictBaseModel):
    input_file: FileReference
    output_file: Path
    status: HermesTpx3RunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    counts: Tpx3PhotonReconstructionCountsSummary | None = None


class HermesTpx3EventReconstructionResult(StrictBaseModel):
    input_file: FileReference
    output_file: Path
    status: HermesTpx3RunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    counts: Tpx3EventReconstructionCountsSummary | None = None


# ---------------------------------------------------------------------------
# Stage containers
# ---------------------------------------------------------------------------


class Tpx3UnpackingRuntimeOptions(StrictBaseModel):
    overwrite: bool = False
    time_sort: bool = True


class Tpx3Unpacking(StrictBaseModel):
    program: BinaryProgram
    tpx3_files: list[FileReference] = Field(min_length=1)
    output_directory: Path | None = None
    runtime_options: Tpx3UnpackingRuntimeOptions = Field(
        default_factory=Tpx3UnpackingRuntimeOptions
    )
    results: list[HermesTpx3UnpackingResult] = Field(default_factory=list)

    @field_validator("tpx3_files", mode="before")
    @classmethod
    def expand_tpx3_file_list(cls, value: object) -> object:
        return _expand_file_list(value)

    @model_validator(mode="after")
    def require_unique_stems(self) -> Tpx3Unpacking:
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


class Tpx3PhotonReconstructionRuntimeOptions(StrictBaseModel):
    overwrite: bool = False


class Tpx3PhotonReconstruction(StrictBaseModel):
    program: BinaryProgram
    # "auto" gathers pixel files from the unpacking stage's output; a list names
    # specific pixelHits Parquet files to reconstruct.
    pixel_parquet_files: Literal["auto"] | list[FileReference] = "auto"
    output_directory: Path | None = None
    clustering_algorithm: ClusteringAlgorithm = "connected_components"
    settings: Tpx3PhotonClusteringSettings
    runtime_options: Tpx3PhotonReconstructionRuntimeOptions = Field(
        default_factory=Tpx3PhotonReconstructionRuntimeOptions
    )
    results: list[HermesTpx3ReconstructionResult] = Field(default_factory=list)

    @field_validator("pixel_parquet_files", mode="before")
    @classmethod
    def expand_pixel_file_list(cls, value: object) -> object:
        return _expand_file_list(value)

    @field_validator("pixel_parquet_files", mode="after")
    @classmethod
    def require_non_empty_file_list(cls, value: object) -> object:
        if isinstance(value, list) and not value:
            raise ValueError(
                "pixel_parquet_files must be 'auto' or a non-empty file list"
            )
        return value


class Tpx3EventReconstructionRuntimeOptions(StrictBaseModel):
    overwrite: bool = False


class Tpx3EventReconstruction(StrictBaseModel):
    program: BinaryProgram
    # "auto" gathers photon files from the photon reconstruction stage's output;
    # a list names specific photon_events Parquet files to reconstruct.
    photon_parquet_files: Literal["auto"] | list[FileReference] = "auto"
    output_directory: Path | None = None
    clustering_algorithm: ClusteringAlgorithm = "connected_components"
    settings: Tpx3EventReconstructionSettings
    runtime_options: Tpx3EventReconstructionRuntimeOptions = Field(
        default_factory=Tpx3EventReconstructionRuntimeOptions
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
# Analysis state
# ---------------------------------------------------------------------------


class HermesTpx3AnalysisState(StrictBaseModel):
    mode: Literal["hermes"] = "hermes"
    analysis_directory: Path
    resource_limit_percent: int = Field(default=90, ge=1, le=100)
    # Optional so reconstruction can run on its own when unpacking is already
    # done and the pixel/photon files it needs are already on disk.
    unpacking: Tpx3Unpacking | None = None
    photon_reconstruction: Tpx3PhotonReconstruction | None = None
    event_reconstruction: Tpx3EventReconstruction | None = None

    @model_validator(mode="after")
    def derive_output_directories(self) -> HermesTpx3AnalysisState:
        if self.unpacking is not None and self.unpacking.output_directory is None:
            self.unpacking.output_directory = self.analysis_directory
        reconstruction = self.photon_reconstruction
        if reconstruction is not None and reconstruction.output_directory is None:
            reconstruction.output_directory = self.analysis_directory / "photons"
        event_reconstruction = self.event_reconstruction
        if (
            event_reconstruction is not None
            and event_reconstruction.output_directory is None
        ):
            event_reconstruction.output_directory = (
                self.analysis_directory / "events"
            )
        return self
