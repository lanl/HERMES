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

EmpirRunStatus = Literal["planned", "running", "completed", "failed"]
EmpirExternalTriggerMode = Literal["ignore", "reference", "frameSync"]
EmpirTiffFormat = Literal["tiff_w4", "tiff_w8"]


def _validate_suffix(
    path: Path,
    suffixes: tuple[str, ...],
    field_name: str,
) -> Path:
    if path.suffix.lower() not in suffixes:
        expected = " or ".join(suffixes)
        msg = f"{field_name} must use the {expected} filename suffix"
        raise ValueError(msg)
    return path


def _validate_file_reference_suffix(
    file: FileReference,
    suffixes: tuple[str, ...],
    field_name: str,
) -> FileReference:
    _validate_suffix(file.path, suffixes, field_name)
    return file


class EmpirPixelToPhotonSettings(StrictBaseModel):
    spatial_distance_pixels: float = Field(ge=0)
    time_distance_seconds: float = Field(ge=0)
    minimum_pixel_count: int = Field(ge=1)
    include_tdc1: bool = False


class EmpirPixelToPhotonResult(StrictBaseModel):
    status: EmpirRunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    elapsed_seconds: float | None = Field(default=None, ge=0)
    exit_code: int | None = None
    saved_photon_file: FileReference | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EmpirPixelToPhotonRun(StrictBaseModel):
    input_tpx3_file: FileReference
    requested_photon_file: Path
    command_args: list[str] = Field(
        default_factory=list,
        description="Built and saved by the EMPIR runner.",
    )
    result: EmpirPixelToPhotonResult = Field(
        default_factory=EmpirPixelToPhotonResult
    )

    @field_validator("input_tpx3_file")
    @classmethod
    def validate_input_tpx3_file(
        cls, value: FileReference
    ) -> FileReference:
        return _validate_file_reference_suffix(
            value, (".tpx3",), "input_tpx3_file"
        )

    @field_validator("requested_photon_file")
    @classmethod
    def validate_requested_photon_file(cls, value: Path) -> Path:
        return _validate_suffix(
            value, (".empirphot",), "requested_photon_file"
        )


class EmpirPixelToPhotonState(StrictBaseModel):
    program: BinaryProgram
    settings: EmpirPixelToPhotonSettings
    runs: list[EmpirPixelToPhotonRun] = Field(min_length=1)


class EmpirPhotonToEventSettings(StrictBaseModel):
    spatial_distance_pixels: float = Field(ge=0)
    time_distance_seconds: float = Field(ge=0)
    maximum_duration_seconds: float = Field(ge=0)


class EmpirPhotonToEventResult(StrictBaseModel):
    status: EmpirRunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    elapsed_seconds: float | None = Field(default=None, ge=0)
    exit_code: int | None = None
    saved_event_file: FileReference | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EmpirPhotonToEventRun(StrictBaseModel):
    input_photon_file: FileReference
    requested_event_file: Path
    command_args: list[str] = Field(
        default_factory=list,
        description="Built and saved by the EMPIR runner.",
    )
    result: EmpirPhotonToEventResult = Field(
        default_factory=EmpirPhotonToEventResult
    )

    @field_validator("input_photon_file")
    @classmethod
    def validate_input_photon_file(
        cls, value: FileReference
    ) -> FileReference:
        return _validate_file_reference_suffix(
            value, (".empirphot",), "input_photon_file"
        )

    @field_validator("requested_event_file")
    @classmethod
    def validate_requested_event_file(cls, value: Path) -> Path:
        return _validate_suffix(
            value, (".empirevent",), "requested_event_file"
        )


class EmpirPhotonToEventState(StrictBaseModel):
    program: BinaryProgram
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
    status: EmpirRunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    elapsed_seconds: float | None = Field(default=None, ge=0)
    exit_code: int | None = None
    saved_tiff_file: FileReference | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EmpirEventToImageState(StrictBaseModel):
    program: BinaryProgram
    settings: EmpirEventToImageSettings
    input_event_files: list[FileReference] = Field(min_length=1)
    requested_tiff_file: Path
    command_args: list[str] = Field(
        default_factory=list,
        description="Built and saved by the EMPIR runner.",
    )
    result: EmpirEventToImageResult = Field(default_factory=EmpirEventToImageResult)

    @field_validator("input_event_files")
    @classmethod
    def validate_input_event_files(
        cls, value: list[FileReference]
    ) -> list[FileReference]:
        for file in value:
            _validate_file_reference_suffix(
                file, (".empirevent",), "input_event_files"
            )
        return value

    @field_validator("requested_tiff_file")
    @classmethod
    def validate_requested_tiff_file(cls, value: Path) -> Path:
        return _validate_suffix(
            value, (".tif", ".tiff"), "requested_tiff_file"
        )


class EmpirAnalysisState(StrictBaseModel):
    mode: Literal["empir"] = "empir"
    version: str | None = None
    save_photon_files: bool = False
    save_event_files: bool = False
    pixel_to_photon: EmpirPixelToPhotonState
    photon_to_event: EmpirPhotonToEventState
    event_to_image: EmpirEventToImageState

    @model_validator(mode="after")
    def validate_pipeline_paths(self) -> EmpirAnalysisState:
        requested_photon_files = [
            run.requested_photon_file for run in self.pixel_to_photon.runs
        ]
        input_photon_files = [
            run.input_photon_file.path for run in self.photon_to_event.runs
        ]
        if requested_photon_files != input_photon_files:
            msg = (
                "photon_to_event input files must match pixel_to_photon "
                "requested output files in order"
            )
            raise ValueError(msg)

        requested_event_files = [
            run.requested_event_file for run in self.photon_to_event.runs
        ]
        input_event_files = [
            file.path for file in self.event_to_image.input_event_files
        ]
        if requested_event_files != input_event_files:
            msg = (
                "event_to_image input files must match photon_to_event "
                "requested output files in order"
            )
            raise ValueError(msg)

        return self
