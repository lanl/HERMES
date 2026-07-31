from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3ReconstructionResult,
    HermesTpx3UnpackingResult,
    Tpx3PhotonClusteringSettings,
    Tpx3PhotonReconstruction,
    Tpx3PhotonReconstructionSummary,
    Tpx3SpidrSummary,
    Tpx3Unpacking,
)
from hermes.state.models.shared_models import BinaryProgram, FileReference


def _analysis_state(tmp_path: Path, *raw_names: str) -> HermesTpx3AnalysisState:
    return HermesTpx3AnalysisState(
        analysis_directory=tmp_path / "analysis",
        unpacking=Tpx3Unpacking(
            program=BinaryProgram(
                name="tpx3-spidr-cpp",
                executable_path=tmp_path / "bin/hermes-tpx3-spidr",
                version="0.1.0",
            ),
            tpx3_files=[
                FileReference(path=tmp_path / "rawTpx3" / raw_name)
                for raw_name in raw_names
            ],
            results=[
                HermesTpx3UnpackingResult(
                    input_file=FileReference(path=tmp_path / "rawTpx3" / raw_name),
                    status="completed",
                    started_at=datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 7, 23, 12, 1, tzinfo=timezone.utc),
                )
                for raw_name in raw_names
            ],
        ),
    )


def _summary_data() -> dict[str, object]:
    return {
        "unpacking": {
            "bytes_read": 24,
            "chunks_read": 2,
            "packets_read": 3,
            "pixel_data_packets": 1,
            "tdc_timestamps": 0,
            "heartbeat_packets": 0,
            "spidr_control_packets": 0,
            "tpx3_control_packets": 0,
            "unrecognized_packets": 0,
            "tdc1_rising": 0,
            "tdc1_falling": 0,
            "tdc2_rising": 0,
            "tdc2_falling": 0,
            "unknown_tdc_edges": 0,
            "errors": [],
            "warnings": [],
        },
        "timestamp_processing": {
            "heartbeat_pairs": {
                "number_of_beats": 0,
            },
            "time_adjustments": {
                "pixel_packets": 1,
                "tdc_packets": 0,
                "control_packets": 0,
                "failed": 0,
            },
        },
        "sorting": {
            "strategy": "in_memory",
            "memory_budget_bytes": 1_000_000,
            "estimated_memory_bytes": 128,
            "temporary_runs_created": 0,
        },
        "parquet": {
            "pixel_data": {
                "row_count": 1,
                "files": [
                    "pixelHits/raw-chip-0-part-00000.parquet",
                ],
            },
            "tdc_timestamps": {"row_count": 0, "files": []},
            "heartbeat_packets": {"row_count": 0, "files": []},
            "control_packets": {"row_count": 0, "files": []},
            "unrecognized_packets": {"row_count": 0, "files": []},
            "errors": [],
        },
        "processing_times_seconds": {
            "canonical_time_seconds": 2.0345e-12,
            "unpacking": 0.1,
            "canonical_conversion": 0.3,
            "time_adjustments": 0.2,
            "sorting": 0.4,
            "parquet_writing": 0.5,
            "total": 1.5,
            "throughput": {
                "packets_per_second": 2.0,
                "megabytes_per_second": 3.0,
            },
        },
    }


def _clustering_settings_data() -> dict[str, object]:
    return {
        "max_time_spread_ticks": 491_520,
        "min_cluster_size": 2,
        "max_cluster_size": 64,
        "min_pixel_tot_raw": 1,
        "min_cluster_tot_raw": 2,
        "max_cluster_tot_raw": 65_472,
        "max_aspect_ratio": 3.0,
        "min_filled_fraction": 0.5,
    }


def _photon_summary_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "reconstruction": {
            "pixel_rows_read": 12,
            "pixel_rows_below_min_tot": 1,
            "components_formed": 3,
            "photon_count": 2,
            "rejected_component_count": 1,
            "rejection_counts": {
                "below_min_cluster_size": 1,
                "above_max_cluster_size": 0,
                "below_min_cluster_tot": 1,
                "above_max_cluster_tot": 0,
                "above_max_aspect_ratio": 0,
                "below_min_filled_fraction": 0,
            },
            "quality_flag_counts": {
                "saturated_pixel": 1,
                "bridged_components": 0,
            },
            "warnings": [],
            "errors": [],
        },
        "processing_times_seconds": {
            "parquet_reading": 0.1,
            "clustering_and_filtering": 0.2,
            "parquet_writing": 0.1,
            "total": 0.4,
            "throughput": {
                "pixels_per_second": 30.0,
                "photons_per_second": 5.0,
            },
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
    assert dumped["unpacking"]["program"]["name"] == "tpx3-spidr-cpp"
    assert dumped["analysis_directory"].endswith("analysis")
    assert [
        Path(file["path"]).name for file in dumped["unpacking"]["tpx3_files"]
    ] == list(raw_names)
    assert dumped["unpacking"]["results"][0]["status"] == "completed"
    assert dumped["photon_reconstruction"] is None


def test_hermes_analysis_state_requires_a_raw_tpx3_file(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        _analysis_state(tmp_path)


def test_hermes_analysis_state_rejects_duplicate_raw_filename_stems(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="filename stems must be unique"):
        HermesTpx3AnalysisState(
            analysis_directory=tmp_path / "analysis",
            unpacking=Tpx3Unpacking(
                program=BinaryProgram(
                    name="tpx3-spidr-cpp",
                    executable_path=tmp_path / "hermes-tpx3-spidr",
                ),
                tpx3_files=[
                    FileReference(path=tmp_path / "first/raw.tpx3"),
                    FileReference(path=tmp_path / "second/raw.tpx3"),
                ],
            ),
        )


def test_hermes_analysis_state_expands_raw_tpx3_file_list(
    tmp_path: Path,
) -> None:
    file_list_path = tmp_path / "lists/raw_tpx3_files.txt"
    file_list_path.parent.mkdir(parents=True)
    absolute_raw_tpx3_path = tmp_path / "absolute/second.tpx3"
    file_list_path.write_text(
        f"""
# One raw TPX3 file path per line.
../raw/first.tpx3

{absolute_raw_tpx3_path}
""",
        encoding="utf-8",
    )

    analysis = HermesTpx3AnalysisState.model_validate(
        {
            "analysis_directory": tmp_path / "analysis",
            "unpacking": {
                "program": {
                    "name": "tpx3-spidr-cpp",
                    "executable_path": tmp_path / "hermes-tpx3-spidr",
                },
                "tpx3_files": {"file_list": file_list_path},
            },
        }
    )

    assert [raw_file.path for raw_file in analysis.unpacking.tpx3_files] == [
        (file_list_path.parent / "../raw/first.tpx3").resolve(),
        absolute_raw_tpx3_path.resolve(),
    ]
    assert isinstance(analysis.unpacking.tpx3_files[0], FileReference)


@pytest.mark.parametrize(
    ("file_contents", "error"),
    [
        (None, "cannot read file list"),
        ("", "contains no file paths"),
        ("\n# no paths\n\n", "contains no file paths"),
    ],
)
def test_hermes_analysis_state_rejects_invalid_raw_tpx3_file_list(
    tmp_path: Path,
    file_contents: str | None,
    error: str,
) -> None:
    file_list_path = tmp_path / "raw_tpx3_files.txt"
    if file_contents is not None:
        file_list_path.write_text(file_contents, encoding="utf-8")

    with pytest.raises(ValidationError, match=error):
        HermesTpx3AnalysisState.model_validate(
            {
                "analysis_directory": tmp_path / "analysis",
                "unpacking": {
                    "program": {
                        "name": "tpx3-spidr-cpp",
                        "executable_path": tmp_path / "hermes-tpx3-spidr",
                    },
                    "tpx3_files": {"file_list": file_list_path},
                },
            }
        )


def test_hermes_analysis_state_checks_duplicate_stems_from_file_list(
    tmp_path: Path,
) -> None:
    file_list_path = tmp_path / "duplicate-stems.txt"
    file_list_path.write_text(
        "first/raw.tpx3\nsecond/raw.tpx3\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="filename stems must be unique"):
        HermesTpx3AnalysisState.model_validate(
            {
                "analysis_directory": tmp_path / "analysis",
                "unpacking": {
                    "program": {
                        "name": "tpx3-spidr-cpp",
                        "executable_path": tmp_path / "hermes-tpx3-spidr",
                    },
                    "tpx3_files": {"file_list": file_list_path},
                },
            }
        )


def test_reconstruction_result_defaults_and_rejects_undefined_fields(
    tmp_path: Path,
) -> None:
    result = HermesTpx3ReconstructionResult(
        input_file=FileReference(path=tmp_path / "pixelHits/raw.parquet"),
        output_file=tmp_path / "photons/raw.parquet",
    )

    assert result.status == "planned"
    assert result.started_at is None
    assert result.completed_at is None
    assert result.counts is None

    with pytest.raises(ValidationError, match="extra_forbidden"):
        HermesTpx3ReconstructionResult(
            input_file=FileReference(path=tmp_path / "pixelHits/raw.parquet"),
            output_file=tmp_path / "photons/raw.parquet",
            settings={},
        )


def test_photon_clustering_settings_use_structural_defaults() -> None:
    settings = Tpx3PhotonClusteringSettings.model_validate(
        _clustering_settings_data()
    )

    assert settings.adjacency == 8
    assert settings.position_averaging == "arithmetic"
    assert settings.photon_time_estimator == "leading_edge"
    assert settings.timewalk_calibration_file is None
    assert settings.save_photon_pixels is False


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("max_time_spread_ticks", 0, "greater than 0"),
        ("min_cluster_size", 0, "greater than 0"),
        ("min_pixel_tot_raw", 1024, "less than or equal to 1023"),
        ("max_aspect_ratio", 0.99, "greater than or equal to 1"),
        ("min_filled_fraction", 0, "greater than 0"),
        ("min_filled_fraction", 1.01, "less than or equal to 1"),
        ("adjacency", 6, "Input should be 4 or 8"),
    ],
)
def test_photon_clustering_settings_reject_invalid_ranges(
    field: str,
    value: object,
    error: str,
) -> None:
    data = _clustering_settings_data()
    data[field] = value

    with pytest.raises(ValidationError, match=error):
        Tpx3PhotonClusteringSettings.model_validate(data)


@pytest.mark.parametrize(
    ("minimum_field", "maximum_field"),
    [
        ("min_cluster_size", "max_cluster_size"),
        ("min_cluster_tot_raw", "max_cluster_tot_raw"),
    ],
)
def test_photon_clustering_settings_reject_inverted_bounds(
    minimum_field: str,
    maximum_field: str,
) -> None:
    data = _clustering_settings_data()
    data[minimum_field] = 10
    data[maximum_field] = 9

    with pytest.raises(ValidationError, match="less than or equal"):
        Tpx3PhotonClusteringSettings.model_validate(data)


@pytest.mark.parametrize(
    "reserved_estimator",
    ["brightest", "mean", "tot_weighted"],
)
def test_photon_clustering_settings_reject_reserved_time_estimators(
    reserved_estimator: str,
) -> None:
    data = _clustering_settings_data()
    data["photon_time_estimator"] = reserved_estimator

    with pytest.raises(ValidationError, match="reserved and not implemented"):
        Tpx3PhotonClusteringSettings.model_validate(data)


def test_hermes_analysis_state_accepts_photon_reconstruction(
    tmp_path: Path,
) -> None:
    analysis_directory = tmp_path / "analysis"
    state = HermesTpx3AnalysisState(
        analysis_directory=analysis_directory,
        unpacking=Tpx3Unpacking(
            program=BinaryProgram(
                name="tpx3-spidr-cpp",
                executable_path=tmp_path / "bin/hermes-tpx3-spidr",
            ),
            tpx3_files=[FileReference(path=tmp_path / "rawTpx3/raw.tpx3")],
        ),
        photon_reconstruction=Tpx3PhotonReconstruction(
            program=BinaryProgram(
                name="connected-components-cpp",
                executable_path=tmp_path / "bin/hermes-photon-clusterer",
            ),
            settings=Tpx3PhotonClusteringSettings.model_validate(
                _clustering_settings_data()
            ),
        ),
    )

    assert state.photon_reconstruction is not None
    assert state.photon_reconstruction.clustering_algorithm == (
        "connected_components"
    )
    assert state.photon_reconstruction.settings.adjacency == 8
    assert state.photon_reconstruction.pixel_parquet_files == "auto"


def test_hermes_analysis_state_derives_output_directories(
    tmp_path: Path,
) -> None:
    analysis_directory = tmp_path / "analysis"
    state = HermesTpx3AnalysisState(
        analysis_directory=analysis_directory,
        unpacking=Tpx3Unpacking(
            program=BinaryProgram(
                name="tpx3-spidr-cpp",
                executable_path=tmp_path / "bin/hermes-tpx3-spidr",
            ),
            tpx3_files=[FileReference(path=tmp_path / "rawTpx3/raw.tpx3")],
        ),
        photon_reconstruction=Tpx3PhotonReconstruction(
            program=BinaryProgram(
                name="connected-components-cpp",
                executable_path=tmp_path / "bin/hermes-photon-clusterer",
            ),
            settings=Tpx3PhotonClusteringSettings.model_validate(
                _clustering_settings_data()
            ),
        ),
    )

    assert state.unpacking.output_directory == analysis_directory
    assert (
        state.photon_reconstruction.output_directory
        == analysis_directory / "photons"
    )


def test_summary_validates_every_section() -> None:
    summary = Tpx3SpidrSummary.model_validate(_summary_data())

    assert summary.unpacking.pixel_data_packets == 1
    assert summary.timestamp_processing.time_adjustments.pixel_packets == 1
    assert summary.sorting.strategy == "in_memory"
    assert summary.parquet.pixel_data.row_count == 1
    assert summary.parquet.pixel_data.files == [
        Path("pixelHits/raw-chip-0-part-00000.parquet")
    ]
    assert summary.processing_times_seconds.canonical_time_seconds == 2.0345e-12
    assert (
        summary.processing_times_seconds.throughput.packets_per_second
        == 2.0
    )
    assert summary.processing_times_seconds.total == 1.5


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("unpacking", "pixel_data_packets"),
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
    pixel_data = parquet["pixel_data"]
    assert isinstance(pixel_data, dict)
    pixel_data["files"] = [file_path]

    with pytest.raises(ValidationError, match="pixel_data Parquet paths"):
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
    pixel_data = parquet["pixel_data"]
    assert isinstance(pixel_data, dict)
    pixel_data["row_count"] = row_count
    pixel_data["files"] = files

    with pytest.raises(ValidationError, match="category"):
        Tpx3SpidrSummary.model_validate(summary_data)


def test_photon_reconstruction_summary_validates_every_section() -> None:
    summary = Tpx3PhotonReconstructionSummary.model_validate(
        _photon_summary_data()
    )

    assert summary.schema_version == 1
    assert summary.reconstruction.photon_count == 2
    assert summary.reconstruction.components_formed == 3
    assert summary.reconstruction.rejection_counts.below_min_cluster_size == 1
    assert summary.reconstruction.quality_flag_counts.saturated_pixel == 1
    assert summary.processing_times_seconds.total == 0.4
    assert summary.processing_times_seconds.throughput.photons_per_second == 5.0


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("components_formed", 4, "components_formed"),
        ("pixel_rows_below_min_tot", 13, "cannot exceed"),
    ],
)
def test_photon_reconstruction_summary_rejects_inconsistent_values(
    field: str,
    value: object,
    error: str,
) -> None:
    summary_data = _photon_summary_data()
    reconstruction = summary_data["reconstruction"]
    assert isinstance(reconstruction, dict)
    reconstruction[field] = value

    with pytest.raises(ValidationError, match=error):
        Tpx3PhotonReconstructionSummary.model_validate(summary_data)


def test_photon_reconstruction_summary_rejects_quality_flags_over_photons() -> (
    None
):
    summary_data = _photon_summary_data()
    reconstruction = summary_data["reconstruction"]
    assert isinstance(reconstruction, dict)
    quality_flag_counts = reconstruction["quality_flag_counts"]
    assert isinstance(quality_flag_counts, dict)
    quality_flag_counts["bridged_components"] = 99

    with pytest.raises(ValidationError, match="quality flag counts cannot exceed"):
        Tpx3PhotonReconstructionSummary.model_validate(summary_data)
