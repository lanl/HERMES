from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisResults,
    HermesTpx3AnalysisState,
    HermesTpx3ReconstructionResult,
    HermesTpx3UnpackingResult,
    Tpx3SpidrSummary,
    Tpx3SpidrUnpackerProgram,
)
from hermes.state.models.shared_models import FileReference


def _analysis_state(tmp_path: Path, *raw_names: str) -> HermesTpx3AnalysisState:
    return HermesTpx3AnalysisState(
        unpacker_program=Tpx3SpidrUnpackerProgram(
            name="tpx3-spidr-cpp",
            executable_path=tmp_path / "bin/hermes-tpx3-spidr",
            version="0.1.0",
        ),
        analysis_directory=tmp_path / "analysis",
        tpx3_files=[
            FileReference(path=tmp_path / "rawTpx3" / raw_name)
            for raw_name in raw_names
        ],
        results=HermesTpx3AnalysisResults(
            unpacking=HermesTpx3UnpackingResult(
                status="completed",
                started_at=datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc),
                finished_at=datetime(2026, 7, 23, 12, 1, tzinfo=timezone.utc),
            )
        ),
    )


def _summary_data() -> dict[str, object]:
    return {
        "unpacking": {
            "chunks_read": 2,
            "packets_read": 3,
            "decoded_pixel_hits": 1,
            "decoded_tdc_triggers": 0,
            "decoded_global_timestamps": 0,
            "decoded_spidr_control_packets": 0,
            "decoded_tpx3_control_packets": 0,
            "decoded_unknown_packets": 0,
            "warnings": [],
            "errors": [],
        },
        "timestamp_processing": {
            "anchors": {
                "total": 0,
                "unpaired_low": 0,
                "unpaired_high": 0,
                "warnings": [],
            },
            "epoch_assignment": {
                "pixels_assigned": 1,
                "tdc_triggers_assigned": 0,
                "controls_assigned": 0,
                "ambiguous_timestamps": 0,
                "unresolved_timestamps": 0,
                "used_fallback": True,
                "warnings": [],
            },
        },
        "sorting": {
            "method": "in_memory",
            "memory_budget_bytes": 1_000_000,
            "estimated_memory_bytes": 128,
            "temporary_runs_created": 0,
        },
        "parquet": {
            "pixel_hits": {
                "row_count": 1,
                "files": [
                    "pixelHits/raw-chip-0-part-00000.parquet",
                ],
            },
            "tdc_triggers": {"row_count": 0, "files": []},
            "global_timestamps": {"row_count": 0, "files": []},
            "control_packets": {"row_count": 0, "files": []},
            "unknown_packets": {"row_count": 0, "files": []},
            "errors": [],
        },
        "processing_times_seconds": {
            "unpacking": 0.1,
            "epoch_assignment": 0.2,
            "conversion": 0.3,
            "sorting": 0.4,
            "parquet_writing": 0.5,
            "total": 1.5,
        },
    }


@pytest.mark.parametrize(
    "raw_names",
    [
        ("first.tpx3",),
        ("first.tpx3", "second.tpx3"),
    ],
)
def test_hermes_analysis_state_serializes_batch_fields(
    tmp_path: Path,
    raw_names: tuple[str, ...],
) -> None:
    dumped = _analysis_state(tmp_path, *raw_names).model_dump(mode="json")

    assert dumped["mode"] == "hermes"
    assert dumped["unpacker_program"]["name"] == "tpx3-spidr-cpp"
    assert dumped["analysis_directory"].endswith("analysis")
    assert [Path(file["path"]).name for file in dumped["tpx3_files"]] == list(
        raw_names
    )
    assert dumped["results"]["unpacking"]["status"] == "completed"
    assert dumped["results"]["reconstruction"] is None

    duplicated_fields = {
        "unpacking_runs",
        "command_args",
        "summary_json_file",
        "pixel_hit_count",
        "warnings",
        "errors",
        "exit_code",
    }
    assert duplicated_fields.isdisjoint(dumped)
    assert duplicated_fields.isdisjoint(dumped["results"]["unpacking"])


def test_hermes_analysis_state_requires_a_raw_tpx3_file(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        _analysis_state(tmp_path)


def test_hermes_analysis_state_rejects_duplicate_raw_filename_stems(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="filename stems must be unique"):
        HermesTpx3AnalysisState(
            unpacker_program=Tpx3SpidrUnpackerProgram(
                name="tpx3-spidr-cpp",
                executable_path=tmp_path / "hermes-tpx3-spidr",
            ),
            analysis_directory=tmp_path / "analysis",
            tpx3_files=[
                FileReference(path=tmp_path / "first/raw.tpx3"),
                FileReference(path=tmp_path / "second/raw.tpx3"),
            ],
        )


def test_empty_reconstruction_model_rejects_undefined_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        HermesTpx3ReconstructionResult(settings={})


def test_summary_validates_every_section() -> None:
    summary = Tpx3SpidrSummary.model_validate(_summary_data())

    assert summary.unpacking.decoded_pixel_hits == 1
    assert summary.timestamp_processing.epoch_assignment.used_fallback is True
    assert summary.sorting.method == "in_memory"
    assert summary.parquet.pixel_hits.row_count == 1
    assert summary.parquet.pixel_hits.files == [
        Path("pixelHits/raw-chip-0-part-00000.parquet")
    ]
    assert summary.processing_times_seconds.total == 1.5


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("unpacking", "decoded_pixel_hits"),
        ("sorting", "estimated_memory_bytes"),
        ("processing_times_seconds", "total"),
    ],
)
def test_summary_rejects_negative_counts_and_durations(
    section: str,
    field: str,
) -> None:
    summary_data = _summary_data()
    section_data = summary_data[section]
    assert isinstance(section_data, dict)
    section_data[field] = -1

    with pytest.raises(ValidationError, match=field):
        Tpx3SpidrSummary.model_validate(summary_data)


def test_summary_rejects_unknown_and_removed_fields() -> None:
    summary_data = _summary_data()
    summary_data["source"] = {"file_path": "raw.tpx3"}

    with pytest.raises(ValidationError, match="extra_forbidden"):
        Tpx3SpidrSummary.model_validate(summary_data)


@pytest.mark.parametrize(
    "file_path",
    [
        "/absolute/raw-chip-0-part-00000.parquet",
        "../pixelHits/raw-chip-0-part-00000.parquet",
        "tdcTriggers/raw-chip-0-part-00000.parquet",
    ],
)
def test_summary_rejects_invalid_pixel_parquet_paths(file_path: str) -> None:
    summary_data = _summary_data()
    parquet = summary_data["parquet"]
    assert isinstance(parquet, dict)
    pixel_hits = parquet["pixel_hits"]
    assert isinstance(pixel_hits, dict)
    pixel_hits["files"] = [file_path]

    with pytest.raises(ValidationError, match="pixel_hits Parquet paths"):
        Tpx3SpidrSummary.model_validate(summary_data)


@pytest.mark.parametrize(
    ("row_count", "files"),
    [
        (0, ["pixelHits/raw-chip-0-part-00000.parquet"]),
        (1, []),
    ],
)
def test_summary_requires_parquet_files_to_match_saved_rows(
    row_count: int,
    files: list[str],
) -> None:
    summary_data = _summary_data()
    parquet = summary_data["parquet"]
    assert isinstance(parquet, dict)
    pixel_hits = parquet["pixel_hits"]
    assert isinstance(pixel_hits, dict)
    pixel_hits["row_count"] = row_count
    pixel_hits["files"] = files

    with pytest.raises(ValidationError, match="category"):
        Tpx3SpidrSummary.model_validate(summary_data)
