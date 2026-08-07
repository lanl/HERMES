"""Tests for EMPIR event-to-image command construction."""

from pathlib import Path

import pytest
from loguru import logger

from hermes.runner.analysis.empir.event_to_image import (
    build_event_to_image_command,
    execute_event_to_image,
)
from hermes.state.models.analysis.empir import (
    EmpirEventToImageSettings,
    EmpirEventToImageState,
)
from hermes.state.models.shared_models import BinaryProgram, FileReference
from _fake_program import write_fake_empir_program


def _stage(
    tmp_path: Path,
    settings: EmpirEventToImageSettings,
    *,
    input_count: int = 1,
) -> EmpirEventToImageState:
    """Build one event-to-image stage for command tests."""
    return EmpirEventToImageState(
        program=BinaryProgram(
            name="empir-event2image",
            executable_path="empir_event2image",
        ),
        settings=settings,
        input_event_files=[
            FileReference(path=tmp_path / f"input-{index}.empirevent")
            for index in range(input_count)
        ],
        requested_tiff_file=tmp_path / "image.tiff",
    )


def test_build_event_to_image_minimal_command(tmp_path: Path) -> None:
    """Omit every unset image option and pass exact event files with ``-i``."""
    stage = _stage(
        tmp_path,
        EmpirEventToImageSettings(image_width_pixels=512),
    )
    executable = tmp_path / "bin/empir_event2image"

    assert build_event_to_image_command(stage, executable) == [
        str(executable),
        "-i",
        str(tmp_path / "input-0.empirevent"),
        "-o",
        str(tmp_path / "image.tiff"),
        "-x",
        "512",
    ]


@pytest.mark.parametrize(("parallel", "serialized"), [(True, "true"), (False, "false")])
def test_build_event_to_image_full_command(
    tmp_path: Path,
    parallel: bool,
    serialized: str,
) -> None:
    """Map every optional image setting and lowercase the parallel value."""
    stage = _stage(
        tmp_path,
        EmpirEventToImageSettings(
            image_width_pixels=2048,
            image_height_pixels=1024,
            minimum_photon_count=3,
            maximum_photon_count=20,
            minimum_psd=5e-6,
            maximum_psd=2e-5,
            external_trigger_mode="frameSync",
            time_bin_width_seconds=10e-6,
            time_bin_count=1000,
            tiff_format="tiff_w8",
            parallel=parallel,
        ),
        input_count=2,
    )
    executable = tmp_path / "bin/empir_event2image"

    assert build_event_to_image_command(stage, executable) == [
        str(executable),
        "-i",
        f"{tmp_path / 'input-0.empirevent'},{tmp_path / 'input-1.empirevent'}",
        "-o",
        str(tmp_path / "image.tiff"),
        "-x",
        "2048",
        "-y",
        "1024",
        "-m",
        "3",
        "-M",
        "20",
        "-p",
        "5e-06",
        "-P",
        "2e-05",
        "-E",
        "frameSync",
        "-t",
        "1e-05",
        "-T",
        "1000",
        "--fileFormat",
        "tiff_w8",
        "--parallel",
        serialized,
    ]


def test_execute_event_to_image_records_result_and_logs(tmp_path: Path) -> None:
    """Run event-to-image with multiple exact inputs and verify its TIFF."""
    stage = _stage(
        tmp_path,
        EmpirEventToImageSettings(image_width_pixels=512),
        input_count=2,
    )
    for input_file in stage.input_event_files:
        input_file.path.write_text("success", encoding="utf-8")
    executable = tmp_path / "bin/empir_event2image"
    write_fake_empir_program(executable)
    records: list[dict[str, object]] = []
    sink_id = logger.add(lambda message: records.append(message.record))

    try:
        result = execute_event_to_image(stage, executable)
    finally:
        logger.remove(sink_id)

    assert result.status == "completed"
    assert result.saved_tiff_file is not None
    assert result.saved_tiff_file.path == stage.requested_tiff_file
    completed = next(
        record["extra"]
        for record in records
        if record["extra"].get("event_type")
        == "analysis.empir.event_to_image.completed"
    )
    assert completed["input_files"] == [
        str(file.path) for file in stage.input_event_files
    ]
    assert completed["input_file_count"] == 2
