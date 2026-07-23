from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes.state.models.analysis.empir import (
    EmpirAnalysisState,
    EmpirEventToImageSettings,
    EmpirEventToImageState,
    EmpirPhotonToEventRun,
    EmpirPhotonToEventSettings,
    EmpirPhotonToEventState,
    EmpirPixelToPhotonRun,
    EmpirPixelToPhotonSettings,
    EmpirPixelToPhotonState,
)
from hermes.state.models.shared_models import FileReference


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
            executable_path=tmp_path / "bin/empir_pixel2photon_tpx3spidr",
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
                    command_args=["-i", str(raw_file.path), "-o", str(photon_path)],
                )
            ],
        ),
        photon_to_event=EmpirPhotonToEventState(
            executable_path=tmp_path / "bin/empir_photon2event",
            settings=EmpirPhotonToEventSettings(
                spatial_distance_pixels=4,
                time_distance_seconds=100e-6,
                maximum_duration_seconds=500e-6,
            ),
            runs=[
                EmpirPhotonToEventRun(
                    input_photon_file=FileReference(path=photon_path),
                    requested_event_file=event_path,
                    command_args=["-i", str(photon_path), "-o", str(event_path)],
                )
            ],
        ),
        event_to_image=EmpirEventToImageState(
            executable_path=tmp_path / "bin/empir_event2image",
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
            command_args=["-i", str(event_path), "-o", "final/image.tiff"],
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
            executable_path=tmp_path / "empir_pixel2photon_tpx3spidr",
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
