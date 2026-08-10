from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hermes.runner.analysis.hermes.photon_reconstruction import (
    HermesPhotonReconstructionPreflightError,
    check_previous_reconstructed_file,
    derive_output_path,
    derive_reconstruction_command,
    derive_summary_path,
    resolve_pixel_files,
    validate_program_and_algorithm,
)
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3PhotonClustering,
    HermesTpx3PhotonClusteringSettings,
    HermesTpx3PhotonReconstruction,
    Tpx3Unpacking,
)
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import BinaryProgram, FileReference


def _settings(**overrides: Any) -> HermesTpx3PhotonClusteringSettings:
    base: dict[str, Any] = {
        "max_time_spread_ticks": 491520,
        "min_cluster_size": 2,
        "max_cluster_size": 64,
        "min_pixel_tot_raw": 1,
        "min_cluster_tot_raw": 2,
        "max_cluster_tot_raw": 65472,
        "max_aspect_ratio": 3.0,
        "min_filled_fraction": 0.5,
    }
    base.update(overrides)
    return HermesTpx3PhotonClusteringSettings(**base)


def _analysis(
    tmp_path: Path,
    *pixel_names: str,
    settings: HermesTpx3PhotonClusteringSettings | None = None,
    clustering_algorithm: str = "connected_components",
    with_reconstruction: bool = True,
) -> HermesTpx3AnalysisState:
    unpacker_exe = tmp_path / "bin/hermes-tpx3-spidr"
    unpacker_exe.parent.mkdir(parents=True, exist_ok=True)
    unpacker_exe.touch()

    clusterer_exe = tmp_path / "bin/hermes-photon-clusterer"
    clusterer_exe.touch()

    analysis_directory = tmp_path / "analysis"

    # A raw TPX3 file is required to build the unpacking stage; the
    # reconstruction stage reads pixel Parquet files it creates below.
    raw_path = tmp_path / "rawTpx3" / "run_000000.tpx3"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.touch()

    # Pixel Parquet inputs for reconstruction live under pixel_hits/.
    pixel_directory = analysis_directory / "pixel_hits"
    for pixel_name in pixel_names:
        pixel_path = pixel_directory / pixel_name
        pixel_path.parent.mkdir(parents=True, exist_ok=True)
        pixel_path.touch()

    reconstruction = None
    if with_reconstruction:
        reconstruction = HermesTpx3PhotonReconstruction(
            program=BinaryProgram(
                name="photon-clusterer-cpp",
                executable_path=clusterer_exe,
                version="0.1.0",
            ),
            clustering_algorithm=HermesTpx3PhotonClustering(
                name=clustering_algorithm,
                settings=settings or _settings(),
            ),
        )

    return HermesTpx3AnalysisState(
        unpacking=Tpx3Unpacking(
            program=BinaryProgram(
                name="tpx3-spidr-cpp",
                executable_path=unpacker_exe,
                version="0.1.0",
            ),
            tpx3_files=[FileReference(path=raw_path)],
        ),
        photon_reconstruction=reconstruction,
    )


def _measurement_info() -> MeasurementInfo:
    return MeasurementInfo(measurement_id="stage-5", run="test-run")


# ---- skip detection -----------------------------------------------------


def test_fresh_file_is_not_previously_reconstructed(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000_chip_0_pixels_00000.parquet")
    analysis_root = tmp_path / "analysis"
    input_file = resolve_pixel_files(analysis, analysis_root)[0]
    assert not check_previous_reconstructed_file(analysis_root, input_file)


def test_summary_marks_file_previously_reconstructed(tmp_path: Path) -> None:
    analysis_root = tmp_path / "analysis"
    input_file = FileReference(
        path=analysis_root / "pixel_hits" / "run_000000_chip_0_pixels_00000.parquet"
    )
    summary_path = derive_summary_path(analysis_root, input_file)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.touch()

    assert check_previous_reconstructed_file(analysis_root, input_file)


def test_photon_parquet_without_summary_is_not_complete(tmp_path: Path) -> None:
    # A photon parquet without a summary is an incomplete run; the summary is the
    # completion marker, matching the binary's zero-photon behavior where only
    # the summary is produced.
    analysis_root = tmp_path / "analysis"
    input_file = FileReference(
        path=analysis_root / "pixel_hits" / "run_000000_chip_0_pixels_00000.parquet"
    )
    output_file = derive_output_path(analysis_root, input_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.touch()

    assert not check_previous_reconstructed_file(analysis_root, input_file)


# ---- validate_program_and_algorithm -------------------------------------


def test_validate_rejects_dbscan(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000_chip_0_pixels_00000.parquet",
        clustering_algorithm="dbscan",
    )
    with pytest.raises(
        HermesPhotonReconstructionPreflightError, match="not implemented"
    ):
        validate_program_and_algorithm(analysis.photon_reconstruction)


def test_validate_rejects_missing_executable(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000_chip_0_pixels_00000.parquet")
    analysis.photon_reconstruction.program.executable_path.unlink()
    with pytest.raises(
        HermesPhotonReconstructionPreflightError, match="executable does not exist"
    ):
        validate_program_and_algorithm(analysis.photon_reconstruction)


def test_resolve_requires_reconstruction_config(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000_chip_0_pixels_00000.parquet",
        with_reconstruction=False,
    )
    with pytest.raises(
        HermesPhotonReconstructionPreflightError, match="not configured"
    ):
        resolve_pixel_files(analysis, tmp_path / "analysis")


# ---- derive_reconstruction_command --------------------------------------


def test_command_passes_named_flags_and_settings(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000_chip_0_pixels_00000.parquet")
    reconstruction = analysis.photon_reconstruction
    analysis_root = tmp_path / "analysis"
    input_file = FileReference(
        path=analysis_root
        / "pixel_hits"
        / "run_000000_chip_0_pixels_00000.parquet"
    )
    command = derive_reconstruction_command(
        reconstruction,
        analysis_root,
        input_file,
        tmp_path / "settings.json",
        _measurement_info(),
    )
    assert command[1:] == [
        "--input",
        str(input_file.path),
        "--output",
        str(analysis_root),
        "--measurement-id",
        "stage-5",
        "--run",
        "test-run",
        "--settings",
        str(tmp_path / "settings.json"),
    ]
    assert "--overwrite" not in command


def test_command_appends_overwrite_when_requested(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000_chip_0_pixels_00000.parquet")
    reconstruction = analysis.photon_reconstruction
    analysis_root = tmp_path / "analysis"
    input_file = FileReference(
        path=analysis_root
        / "pixel_hits"
        / "run_000000_chip_0_pixels_00000.parquet"
    )
    command = derive_reconstruction_command(
        reconstruction,
        analysis_root,
        input_file,
        tmp_path / "settings.json",
        _measurement_info(),
        overwrite=True,
    )
    assert command[-1] == "--overwrite"
