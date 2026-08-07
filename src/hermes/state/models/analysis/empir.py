"""Typed settings and results for the three-step EMPIR analysis pipeline."""

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

# Values recorded while each external EMPIR program runs.
EmpirRunStatus = Literal["planned", "running", "completed", "failed"]
EmpirExternalTriggerMode = Literal["ignore", "reference", "frameSync"]
EmpirTiffFormat = Literal["tiff_w4", "tiff_w8"]


def _validate_suffix(
    path: Path,
    suffixes: tuple[str, ...],
    field_name: str,
) -> Path:
    """Require a path to use one of the allowed filename suffixes."""
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
    """Apply a filename-suffix check to a file entry."""
    _validate_suffix(file.path, suffixes, field_name)
    return file


class EmpirPixelToPhotonSettings(StrictBaseModel):
    """Settings passed to ``empir_pixel2photon_tpx3spidr``."""

    spatial_distance_pixels: float = Field(ge=0)
    time_distance_seconds: float = Field(ge=0)
    minimum_pixel_count: int = Field(ge=1)
    include_tdc1: bool = False


class EmpirPixelToPhotonResult(StrictBaseModel):
    """Recorded outcome from one pixel-to-photon process."""

    status: EmpirRunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    elapsed_seconds: float | None = Field(default=None, ge=0)
    exit_code: int | None = None
    saved_photon_file: FileReference | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EmpirPixelToPhotonRun(StrictBaseModel):
    """Input, requested output, command, and result for one raw TPX3 file."""

    input_tpx3_file: FileReference
    photon_file: Path
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
        """Require the pixel-to-photon input to be a TPX3 file."""
        return _validate_file_reference_suffix(
            value, (".tpx3",), "input_tpx3_file"
        )

    @field_validator("photon_file")
    @classmethod
    def validate_photon_file(cls, value: Path) -> Path:
        """Require EMPIR's photon output filename."""
        return _validate_suffix(
            value, (".empirphot",), "photon_file"
        )


class EmpirPixelToPhotonState(StrictBaseModel):
    """Program, shared settings, and runs for pixel-to-photon processing."""

    program: BinaryProgram
    settings: EmpirPixelToPhotonSettings
    runs: list[EmpirPixelToPhotonRun] = Field(min_length=1)


class EmpirPhotonToEventSettings(StrictBaseModel):
    """Settings passed to ``empir_photon2event``."""

    spatial_distance_pixels: float = Field(ge=0)
    time_distance_seconds: float = Field(ge=0)
    maximum_duration_seconds: float = Field(ge=0)


class EmpirPhotonToEventResult(StrictBaseModel):
    """Recorded outcome from one photon-to-event process."""

    status: EmpirRunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    elapsed_seconds: float | None = Field(default=None, ge=0)
    exit_code: int | None = None
    saved_event_file: FileReference | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EmpirPhotonToEventRun(StrictBaseModel):
    """Input, requested output, command, and result for one photon file."""

    input_photon_file: FileReference
    event_file: Path
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
        """Require the photon-to-event input to be an EMPIR photon file."""
        return _validate_file_reference_suffix(
            value, (".empirphot",), "input_photon_file"
        )

    @field_validator("event_file")
    @classmethod
    def validate_event_file(cls, value: Path) -> Path:
        """Require EMPIR's event output filename."""
        return _validate_suffix(
            value, (".empirevent",), "event_file"
        )


class EmpirPhotonToEventState(StrictBaseModel):
    """Program, shared settings, and runs for photon-to-event processing."""

    program: BinaryProgram
    settings: EmpirPhotonToEventSettings
    runs: list[EmpirPhotonToEventRun] = Field(min_length=1)


class EmpirEventToImageSettings(StrictBaseModel):
    """Settings passed to ``empir_event2image``."""

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
        """Check paired ranges and time-bin settings."""
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
    """Recorded outcome from the event-to-image process."""

    status: EmpirRunStatus = "planned"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    elapsed_seconds: float | None = Field(default=None, ge=0)
    exit_code: int | None = None
    saved_tiff_file: FileReference | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EmpirEventToImageState(StrictBaseModel):
    """Inputs, settings, requested TIFF, command, and image result."""

    program: BinaryProgram
    settings: EmpirEventToImageSettings
    input_event_files: list[FileReference] = Field(min_length=1)
    tiff_file: Path
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
        """Require every image input to be an EMPIR event file."""
        for file in value:
            _validate_file_reference_suffix(
                file, (".empirevent",), "input_event_files"
            )
        return value

    @field_validator("tiff_file")
    @classmethod
    def validate_tiff_file(cls, value: Path) -> Path:
        """Require the final output to use a TIFF filename."""
        return _validate_suffix(
            value, (".tif", ".tiff"), "tiff_file"
        )


class EmpirAnalysisState(StrictBaseModel):
    """Configuration and progress for one complete EMPIR analysis."""

    mode: Literal["empir"] = "empir"
    version: str | None = None
    save_photon_files: bool = False
    save_event_files: bool = False
    pixel_to_photon: EmpirPixelToPhotonState
    photon_to_event: EmpirPhotonToEventState
    event_to_image: EmpirEventToImageState

    @model_validator(mode="after")
    def validate_pipeline_paths(self) -> EmpirAnalysisState:
        """Require each step to read the preceding step's requested files."""
        # Some type-guard tests deliberately use model_construct() to create an
        # incomplete instance without validation. Normal model construction
        # still reports every missing stage before this validator runs.
        if not all(
            hasattr(self, field_name)
            for field_name in (
                "pixel_to_photon",
                "photon_to_event",
                "event_to_image",
            )
        ):
            return self

        # List order connects each upstream run to its downstream run.
        photon_files = [
            run.photon_file for run in self.pixel_to_photon.runs
        ]
        input_photon_files = [
            run.input_photon_file.path for run in self.photon_to_event.runs
        ]
        if photon_files != input_photon_files:
            msg = (
                "photon_to_event input files must match pixel_to_photon "
                "requested output files in order"
            )
            raise ValueError(msg)

        event_files = [
            run.event_file for run in self.photon_to_event.runs
        ]
        input_event_files = [
            file.path for file in self.event_to_image.input_event_files
        ]
        if event_files != input_event_files:
            msg = (
                "event_to_image input files must match photon_to_event "
                "requested output files in order"
            )
            raise ValueError(msg)

        return self
