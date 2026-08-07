from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes.state.models.analysis.empir import (
    EmpirAnalysisState,
    EmpirEventToImageResult,
    EmpirEventToImageSettings,
    EmpirEventToImageState,
    EmpirPhotonToEventResult,
    EmpirPhotonToEventRun,
    EmpirPhotonToEventSettings,
    EmpirPhotonToEventState,
    EmpirPixelToPhotonResult,
    EmpirPixelToPhotonRun,
    EmpirPixelToPhotonSettings,
    EmpirPixelToPhotonState,
)
from hermes.state.models.shared_models import BinaryProgram, FileReference


def _valid_empir_analysis_values(tmp_path: Path) -> dict[str, object]:
    photon_path = tmp_path / "raw.empirphot"
    event_path = tmp_path / "raw.empirevent"
    state = EmpirAnalysisState(
        pixel_to_photon=EmpirPixelToPhotonState(
            program=BinaryProgram(
                name="empir-pixel2photon",
                executable_path="empir_pixel2photon_tpx3spidr",
            ),
            settings=EmpirPixelToPhotonSettings(
                spatial_distance_pixels=5,
                time_distance_seconds=500e-9,
                minimum_pixel_count=3,
            ),
            runs=[
                EmpirPixelToPhotonRun(
                    input_tpx3_file=FileReference(path=tmp_path / "raw.tpx3"),
                    requested_photon_file=photon_path,
                )
            ],
        ),
        photon_to_event=EmpirPhotonToEventState(
            program=BinaryProgram(
                name="empir-photon2event",
                executable_path="empir_photon2event",
            ),
            settings=EmpirPhotonToEventSettings(
                spatial_distance_pixels=4,
                time_distance_seconds=100e-6,
                maximum_duration_seconds=500e-6,
            ),
            runs=[
                EmpirPhotonToEventRun(
                    input_photon_file=FileReference(path=photon_path),
                    requested_event_file=event_path,
                )
            ],
        ),
        event_to_image=EmpirEventToImageState(
            program=BinaryProgram(
                name="empir-event2image",
                executable_path="empir_event2image",
            ),
            settings=EmpirEventToImageSettings(image_width_pixels=512),
            input_event_files=[FileReference(path=event_path)],
            requested_tiff_file=tmp_path / "image.tiff",
        ),
    )
    return state.model_dump()


def test_empir_analysis_state_serializes_direct_binary_pipeline(
    tmp_path: Path,
) -> None:
    raw_file = FileReference(path=tmp_path / "raw.tpx3")
    photon_path = tmp_path / "raw.empirphot"
    event_path = tmp_path / "raw.empirevent"

    state = EmpirAnalysisState(
        version="1.0.0-r0",
        save_photon_files=False,
        save_event_files=True,
        pixel_to_photon=EmpirPixelToPhotonState(
            program=BinaryProgram(
                name="empir-pixel2photon",
                executable_path=tmp_path / "bin/empir_pixel2photon_tpx3spidr",
            ),
            settings=EmpirPixelToPhotonSettings(
                spatial_distance_pixels=5,
                time_distance_seconds=500e-9,
                minimum_pixel_count=3,
                include_tdc1=True,
            ),
            runs=[
                EmpirPixelToPhotonRun(
                    input_tpx3_file=raw_file,
                    requested_photon_file=photon_path,
                )
            ],
        ),
        photon_to_event=EmpirPhotonToEventState(
            program=BinaryProgram(
                name="empir-photon2event",
                executable_path=tmp_path / "bin/empir_photon2event",
            ),
            settings=EmpirPhotonToEventSettings(
                spatial_distance_pixels=4,
                time_distance_seconds=100e-6,
                maximum_duration_seconds=500e-6,
            ),
            runs=[
                EmpirPhotonToEventRun(
                    input_photon_file=FileReference(path=photon_path),
                    requested_event_file=event_path,
                )
            ],
        ),
        event_to_image=EmpirEventToImageState(
            program=BinaryProgram(
                name="empir-event2image",
                executable_path=tmp_path / "bin/empir_event2image",
            ),
            settings=EmpirEventToImageSettings(
                image_width_pixels=2048,
                image_height_pixels=2048,
                minimum_photon_count=3,
                minimum_psd=5e-6,
                external_trigger_mode="reference",
                time_bin_width_seconds=10e-6,
                time_bin_count=1000,
                tiff_format="tiff_w8",
                parallel=True,
            ),
            input_event_files=[FileReference(path=event_path)],
            requested_tiff_file=tmp_path / "final/image.tiff",
        ),
    )

    dumped = state.model_dump(mode="json")

    assert dumped["mode"] == "empir"
    assert dumped["pixel_to_photon"]["runs"][0]["input_tpx3_file"][
        "path"
    ].endswith("raw.tpx3")
    assert dumped["pixel_to_photon"]["runs"][0]["result"]["status"] == (
        "planned"
    )
    assert dumped["photon_to_event"]["runs"][0]["requested_event_file"].endswith(
        "raw.empirevent"
    )
    assert dumped["event_to_image"]["settings"]["external_trigger_mode"] == (
        "reference"
    )
    assert dumped["event_to_image"]["result"]["status"] == "planned"
    assert dumped["pixel_to_photon"]["runs"][0]["command_args"] == []
    assert dumped["photon_to_event"]["runs"][0]["command_args"] == []
    assert dumped["event_to_image"]["command_args"] == []


@pytest.mark.parametrize(
    "result_model",
    [
        EmpirPixelToPhotonResult,
        EmpirPhotonToEventResult,
        EmpirEventToImageResult,
    ],
)
def test_empir_results_require_nonnegative_elapsed_seconds(
    result_model: type[
        EmpirPixelToPhotonResult
        | EmpirPhotonToEventResult
        | EmpirEventToImageResult
    ],
) -> None:
    assert result_model(elapsed_seconds=0).elapsed_seconds == 0

    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        result_model(elapsed_seconds=-0.01)


@pytest.mark.parametrize(
    ("path_parts", "invalid_name", "message"),
    [
        (
            ("pixel_to_photon", "runs", 0, "input_tpx3_file", "path"),
            "raw.bin",
            "input_tpx3_file",
        ),
        (
            ("pixel_to_photon", "runs", 0, "requested_photon_file"),
            "raw.photons",
            "requested_photon_file",
        ),
        (
            ("photon_to_event", "runs", 0, "input_photon_file", "path"),
            "raw.photons",
            "input_photon_file",
        ),
        (
            ("photon_to_event", "runs", 0, "requested_event_file"),
            "raw.events",
            "requested_event_file",
        ),
        (
            ("event_to_image", "input_event_files", 0, "path"),
            "raw.events",
            "input_event_files",
        ),
        (
            ("event_to_image", "requested_tiff_file"),
            "image.png",
            "requested_tiff_file",
        ),
    ],
)
def test_empir_analysis_rejects_invalid_filename_suffixes(
    tmp_path: Path,
    path_parts: tuple[str | int, ...],
    invalid_name: str,
    message: str,
) -> None:
    values = _valid_empir_analysis_values(tmp_path)
    target: object = values
    for part in path_parts[:-1]:
        target = target[part]  # type: ignore[index]
    target[path_parts[-1]] = tmp_path / invalid_name  # type: ignore[index]

    with pytest.raises(ValidationError, match=message):
        EmpirAnalysisState.model_validate(values)


@pytest.mark.parametrize(
    ("path_parts", "replacement", "message"),
    [
        (
            ("photon_to_event", "runs", 0, "input_photon_file", "path"),
            "different.empirphot",
            "photon_to_event input files must match",
        ),
        (
            ("event_to_image", "input_event_files", 0, "path"),
            "different.empirevent",
            "event_to_image input files must match",
        ),
    ],
)
def test_empir_analysis_rejects_disconnected_pipeline_paths(
    tmp_path: Path,
    path_parts: tuple[str | int, ...],
    replacement: str,
    message: str,
) -> None:
    values = _valid_empir_analysis_values(tmp_path)
    target: object = values
    for part in path_parts[:-1]:
        target = target[part]  # type: ignore[index]
    target[path_parts[-1]] = tmp_path / replacement  # type: ignore[index]

    with pytest.raises(ValidationError, match=message):
        EmpirAnalysisState.model_validate(values)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"minimum_photon_count": 5, "maximum_photon_count": 4},
            "minimum_photon_count",
        ),
        ({"minimum_psd": 2.0, "maximum_psd": 1.0}, "minimum_psd"),
        ({"time_bin_width_seconds": 1e-3}, "must be set together"),
        ({"time_bin_count": 10}, "must be set together"),
    ],
)
def test_event_to_image_settings_reject_invalid_combinations(
    overrides: dict[str, int | float],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        EmpirEventToImageSettings(image_width_pixels=512, **overrides)


def test_empir_stage_requires_at_least_one_file(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        EmpirPixelToPhotonState(
            program=BinaryProgram(
                name="empir-pixel2photon",
                executable_path=tmp_path / "empir_pixel2photon_tpx3spidr",
            ),
            settings=EmpirPixelToPhotonSettings(
                spatial_distance_pixels=5,
                time_distance_seconds=500e-9,
                minimum_pixel_count=3,
            ),
            runs=[],
        )


def test_empir_settings_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EmpirPhotonToEventSettings(
            spatial_distance_pixels=4,
            time_distance_seconds=100e-6,
            maximum_duration_seconds=500e-6,
            untyped_options={},
        )
