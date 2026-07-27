from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from hermes.state.models.shared_models import FileReference, StrictBaseModel

AnalysisRunStatus = Literal["planned", "running", "completed", "failed"]
SortingStrategy = Literal["in_memory", "external_merge"]
ClusteringAlgorithm = Literal["connected_components", "dbscan"]
PhotonTimeEstimator = Literal[
    "leading_edge",
    "brightest",
    "mean",
    "tot_weighted",
]
PhotonCorrectionModel = Literal["none", "linear", "inverse"]


class Tpx3SpidrUnpackerProgram(StrictBaseModel):
    name: str = Field(min_length=1)
    executable_path: Path
    version: str | None = None


class HermesTpx3UnpackingResult(StrictBaseModel):
    status: AnalysisRunStatus = "planned"
    started_at: datetime | None = None
    finished_at: datetime | None = None


class PhotonReconstructorProgram(StrictBaseModel):
    name: str = Field(min_length=1)
    executable_path: Path
    version: str | None = None


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


class Tpx3PhotonReconstructionConfiguration(StrictBaseModel):
    program: PhotonReconstructorProgram
    pixel_data_directory: Path
    photon_output_directory: Path
    settings: Tpx3PhotonClusteringSettings
    clustering_algorithm: ClusteringAlgorithm = "connected_components"


class HermesTpx3ReconstructionResult(StrictBaseModel):
    status: AnalysisRunStatus = "planned"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    photon_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class HermesTpx3AnalysisResults(StrictBaseModel):
    unpacking: HermesTpx3UnpackingResult = Field(
        default_factory=HermesTpx3UnpackingResult
    )
    reconstruction: HermesTpx3ReconstructionResult | None = None


class HermesTpx3AnalysisState(StrictBaseModel):
    mode: Literal["hermes"] = "hermes"
    unpacker_program: Tpx3SpidrUnpackerProgram
    analysis_directory: Path
    tpx3_files: list[FileReference] = Field(min_length=1)
    resource_limit_percent: int = Field(default=90, ge=1, le=100)
    photon_reconstruction: Tpx3PhotonReconstructionConfiguration | None = None
    results: HermesTpx3AnalysisResults = Field(
        default_factory=HermesTpx3AnalysisResults
    )

    @model_validator(mode="after")
    def validate_analysis_paths_and_inputs(self) -> HermesTpx3AnalysisState:
        stems = [raw_file.path.stem for raw_file in self.tpx3_files]
        duplicate_stems = sorted(
            stem for stem in set(stems) if stems.count(stem) > 1
        )
        if duplicate_stems:
            duplicates = ", ".join(duplicate_stems)
            raise ValueError(f"raw TPX3 filename stems must be unique: {duplicates}")

        reconstruction = self.photon_reconstruction
        if reconstruction is not None:
            expected_pixel_directory = self.analysis_directory / "pixelHits"
            if reconstruction.pixel_data_directory != expected_pixel_directory:
                raise ValueError(
                    "photon reconstruction pixel_data_directory must equal "
                    "analysis_directory / 'pixelHits'"
                )
            expected_photon_directory = self.analysis_directory / "photons"
            if reconstruction.photon_output_directory != expected_photon_directory:
                raise ValueError(
                    "photon reconstruction photon_output_directory must equal "
                    "analysis_directory / 'photons'"
                )
        return self


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
        expected_directories = {
            "pixel_data": "pixelHits",
            "tdc_timestamps": "tdcTriggers",
            "heartbeat_packets": "globalTimestamps",
            "control_packets": "controlPackets",
            "unrecognized_packets": "unknownPackets",
        }
        for field_name, expected_directory in expected_directories.items():
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


class Tpx3PhotonClusteringSummary(StrictBaseModel):
    algorithm: ClusteringAlgorithm
    settings: Tpx3PhotonClusteringSettings


class Tpx3PhotonTimingSummary(StrictBaseModel):
    estimator: Literal["leading_edge"]
    correction_model: PhotonCorrectionModel
    calibration_file: Path | None
    parameters: dict[str, float]
    high_tot_anchor: float | None = Field(ge=0, le=1023)

    @model_validator(mode="after")
    def require_correction_details(self) -> Tpx3PhotonTimingSummary:
        if self.correction_model == "none":
            if (
                self.calibration_file is not None
                or self.parameters
                or self.high_tot_anchor is not None
            ):
                raise ValueError(
                    "correction_model='none' cannot include calibration details"
                )
        elif (
            self.calibration_file is None
            or not self.parameters
            or self.high_tot_anchor is None
        ):
            raise ValueError(
                "a fitted correction requires a calibration file, parameters, "
                "and high_tot_anchor"
            )
        return self


class Tpx3PhotonParquetFilesSummary(StrictBaseModel):
    row_count: int = Field(ge=0)
    files: list[Path]

    @model_validator(mode="after")
    def require_files_for_saved_rows(self) -> Tpx3PhotonParquetFilesSummary:
        if self.row_count == 0 and self.files:
            raise ValueError("a file group with zero rows cannot list Parquet files")
        if self.row_count > 0 and not self.files:
            raise ValueError("a file group with saved rows must list a Parquet file")
        return self


class Tpx3PhotonPixelsParquetSummary(Tpx3PhotonParquetFilesSummary):
    requested: bool

    @model_validator(mode="after")
    def require_no_unrequested_membership_files(
        self,
    ) -> Tpx3PhotonPixelsParquetSummary:
        if not self.requested and (self.row_count != 0 or self.files):
            raise ValueError(
                "unrequested photon_pixels must have zero rows and no files"
            )
        return self


class Tpx3PhotonParquetSummary(StrictBaseModel):
    input_pixel_data_files: list[Path] = Field(min_length=1)
    photon_events: Tpx3PhotonParquetFilesSummary
    photon_pixels: Tpx3PhotonPixelsParquetSummary

    @model_validator(mode="after")
    def require_relative_category_paths(self) -> Tpx3PhotonParquetSummary:
        for input_path in self.input_pixel_data_files:
            if (
                input_path.is_absolute()
                or ".." in input_path.parts
                or len(input_path.parts) != 2
                or input_path.parts[0] != "pixelHits"
            ):
                raise ValueError(
                    "input pixel_data paths must be relative and begin with "
                    "pixelHits/"
                )

        file_groups = (
            ("photon-events", self.photon_events.files),
            ("photon-pixels", self.photon_pixels.files),
        )
        for filename_marker, files in file_groups:
            for file_path in files:
                if (
                    file_path.is_absolute()
                    or ".." in file_path.parts
                    or len(file_path.parts) != 2
                    or file_path.parts[0] != "photons"
                    or filename_marker not in file_path.name
                    or file_path.suffix != ".parquet"
                ):
                    raise ValueError(
                        f"{filename_marker} paths must be relative Parquet "
                        "paths beginning with photons/"
                    )
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
    clustering: Tpx3PhotonClusteringSummary
    photon_timing: Tpx3PhotonTimingSummary
    parquet: Tpx3PhotonParquetSummary
    processing_times_seconds: Tpx3PhotonProcessingTimesSummary

    @model_validator(mode="after")
    def require_matching_settings_and_counts(
        self,
    ) -> Tpx3PhotonReconstructionSummary:
        settings = self.clustering.settings
        if settings.photon_time_estimator != self.photon_timing.estimator:
            raise ValueError(
                "photon timing estimator must match the clustering settings"
            )
        if settings.save_photon_pixels != self.parquet.photon_pixels.requested:
            raise ValueError(
                "photon_pixels requested value must match save_photon_pixels"
            )
        if (
            settings.timewalk_calibration_file
            != self.photon_timing.calibration_file
        ):
            raise ValueError(
                "photon timing calibration file must match clustering settings"
            )
        if (
            self.reconstruction.photon_count
            != self.parquet.photon_events.row_count
        ):
            raise ValueError(
                "photon_events row_count must match reconstruction photon_count"
            )
        return self
