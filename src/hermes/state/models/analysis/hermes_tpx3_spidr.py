from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from hermes.state.models.shared_models import FileReference, StrictBaseModel

AnalysisRunStatus = Literal["planned", "running", "completed", "failed"]
SortingStrategy = Literal["in_memory", "external_merge"]


class Tpx3SpidrUnpackerProgram(StrictBaseModel):
    name: str = Field(min_length=1)
    executable_path: Path
    version: str | None = None


class HermesTpx3UnpackingResult(StrictBaseModel):
    status: AnalysisRunStatus = "planned"
    started_at: datetime | None = None
    finished_at: datetime | None = None


class HermesTpx3ReconstructionResult(StrictBaseModel):
    pass


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
    results: HermesTpx3AnalysisResults = Field(
        default_factory=HermesTpx3AnalysisResults
    )

    @model_validator(mode="after")
    def require_unique_raw_filename_stems(self) -> HermesTpx3AnalysisState:
        stems = [raw_file.path.stem for raw_file in self.tpx3_files]
        duplicate_stems = sorted(
            stem for stem in set(stems) if stems.count(stem) > 1
        )
        if duplicate_stems:
            duplicates = ", ".join(duplicate_stems)
            raise ValueError(f"raw TPX3 filename stems must be unique: {duplicates}")
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
