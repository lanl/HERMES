from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from hermes.state.models.shared_models import FileReference, StrictBaseModel

AnalysisRunStatus = Literal[
    "planned",
    "running",
    "completed",
    "failed",
    "skipped",
    "unknown",
]
EmpirExternalTriggerMode = Literal["ignore", "reference", "frameSync"]
EmpirTiffFormat = Literal["tiff_w4", "tiff_w8"]


class EmpirPixelToPhotonSettings(StrictBaseModel):
    spatial_distance_pixels: float = Field(ge=0)
    time_distance_seconds: float = Field(ge=0)
    minimum_pixel_count: int = Field(ge=1)
    include_tdc1: bool = False


class EmpirPixelToPhotonResult(StrictBaseModel):
    status: AnalysisRunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exit_code: int | None = None
    saved_photon_file: FileReference | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EmpirPixelToPhotonRun(StrictBaseModel):
    input_tpx3_file: FileReference
    requested_photon_file: Path
    command_args: list[str] = Field(default_factory=list)
    result: EmpirPixelToPhotonResult = Field(
        default_factory=EmpirPixelToPhotonResult
    )


class EmpirPixelToPhotonState(StrictBaseModel):
    executable_path: Path
    settings: EmpirPixelToPhotonSettings
    runs: list[EmpirPixelToPhotonRun] = Field(min_length=1)


class EmpirPhotonToEventSettings(StrictBaseModel):
    spatial_distance_pixels: float = Field(ge=0)
    time_distance_seconds: float = Field(ge=0)
    maximum_duration_seconds: float = Field(ge=0)


class EmpirPhotonToEventResult(StrictBaseModel):
    status: AnalysisRunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exit_code: int | None = None
    saved_event_file: FileReference | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EmpirPhotonToEventRun(StrictBaseModel):
    input_photon_file: FileReference
    requested_event_file: Path
    command_args: list[str] = Field(default_factory=list)
    result: EmpirPhotonToEventResult = Field(
        default_factory=EmpirPhotonToEventResult
    )


class EmpirPhotonToEventState(StrictBaseModel):
    executable_path: Path
    settings: EmpirPhotonToEventSettings
    runs: list[EmpirPhotonToEventRun] = Field(min_length=1)


class EmpirEventToImageSettings(StrictBaseModel):
    image_width_pixels: int = Field(gt=0)
    image_height_pixels: int | None = Field(default=None, gt=0)
    minimum_photon_count: int | None = Field(default=None, ge=0)
    maximum_photon_count: int | None = Field(default=None, ge=0)
    minimum_psd: float | None = Field(default=None, ge=0)
    maximum_psd: float | None = Field(default=None, ge=0)
    external_trigger_mode: EmpirExternalTriggerMode | None = None
    time_bin_width_seconds: float | None = Field(default=None, gt=0)
    time_bin_count: int | None = Field(default=None, gt=0)
    tiff_format: EmpirTiffFormat | None = None
    parallel: bool | None = None

    @model_validator(mode="after")
    def validate_ranges_and_time_bins(self) -> EmpirEventToImageSettings:
        if (
            self.minimum_photon_count is not None
            and self.maximum_photon_count is not None
            and self.minimum_photon_count > self.maximum_photon_count
        ):
            msg = "minimum_photon_count must not exceed maximum_photon_count"
            raise ValueError(msg)

        if (
            self.minimum_psd is not None
            and self.maximum_psd is not None
            and self.minimum_psd > self.maximum_psd
        ):
            msg = "minimum_psd must not exceed maximum_psd"
            raise ValueError(msg)

        if (self.time_bin_width_seconds is None) != (self.time_bin_count is None):
            msg = "time_bin_width_seconds and time_bin_count must be set together"
            raise ValueError(msg)

        return self


class EmpirEventToImageResult(StrictBaseModel):
    status: AnalysisRunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exit_code: int | None = None
    saved_tiff_file: FileReference | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EmpirEventToImageState(StrictBaseModel):
    executable_path: Path
    settings: EmpirEventToImageSettings
    input_event_files: list[FileReference] = Field(min_length=1)
    requested_tiff_file: Path
    command_args: list[str] = Field(default_factory=list)
    result: EmpirEventToImageResult = Field(default_factory=EmpirEventToImageResult)


class EmpirAnalysisState(StrictBaseModel):
    mode: Literal["empir"] = "empir"
    version: str | None = None
    save_photon_files: bool = False
    save_event_files: bool = False
    pixel_to_photon: EmpirPixelToPhotonState
    photon_to_event: EmpirPhotonToEventState
    event_to_image: EmpirEventToImageState
