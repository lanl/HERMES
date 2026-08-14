from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hermes.runner.analysis.hermes.event_reconstruction import (
    HermesEventReconstructionPreflightError,
    check_previous_reconstructed_file,
    derive_event_reconstruction_command,
    derive_output_path,
    derive_summary_path,
    resolve_photon_files,
    validate_program_and_algorithm,
)
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3EventReconstruction,
    HermesTpx3EventReconstructionSettings,
    HermesTpx3PhotonClustering,
    HermesTpx3PhotonClusteringSettings,
    HermesTpx3PhotonReconstruction,
    Tpx3Unpacking,
)
from hermes.state.models.shared_models import BinaryProgram, FileReference


def _settings(**overrides: Any) -> HermesTpx3EventReconstructionSettings:
    base: dict[str, Any] = {
        "spatial_link_radius_pixels": 10.0,
        "spatial_cells_per_axis": 5,
        "max_time_difference_ticks": 4915200.0,
        "max_event_duration_ticks": 14745600.0,
        "min_photon_count": 1,
        "save_event_photons": False,
    }
    base.update(overrides)
    return HermesTpx3EventReconstructionSettings(**base)


def _analysis(
    tmp_path: Path,
    *photon_names: str,
    settings: HermesTpx3EventReconstructionSettings | None = None,
    clustering_algorithm: str = "connected_components",
    with_event_reconstruction: bool = True,
) -> HermesTpx3AnalysisState:
    unpacker_exe = tmp_path / "bin/hermes-tpx3-spidr"
    unpacker_exe.parent.mkdir(parents=True, exist_ok=True)
    unpacker_exe.touch()
    unpacker_exe.chmod(0o755)

    clusterer_exe = tmp_path / "bin/hermes-photon-clusterer"
    clusterer_exe.touch()
    clusterer_exe.chmod(0o755)

    event_exe = tmp_path / "bin/hermes-event-reconstructor"
    event_exe.touch()
    event_exe.chmod(0o755)

    analysis_directory = tmp_path / "analysis"

    # A raw TPX3 file is required to build the unpacking stage.
    raw_path = tmp_path / "rawTpx3" / "run_000000.tpx3"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.touch()

    # Photon Parquet inputs for event reconstruction live under photons/.
    photon_directory = analysis_directory / "photons"
    for photon_name in photon_names:
        photon_path = photon_directory / photon_name
        photon_path.parent.mkdir(parents=True, exist_ok=True)
        photon_path.touch()

    event_reconstruction = None
    if with_event_reconstruction:
        event_reconstruction = HermesTpx3EventReconstruction(
            program=BinaryProgram(
                name="event-reconstructor-cpp",
                executable_path=event_exe,
                version="0.1.0",
            ),
            settings=settings or _settings(),
            clustering_algorithm=clustering_algorithm,
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
        photon_reconstruction=HermesTpx3PhotonReconstruction(
            program=BinaryProgram(
                name="photon-clusterer-cpp",
                executable_path=clusterer_exe,
                version="0.1.0",
            ),
            clustering_algorithm=HermesTpx3PhotonClustering(
                settings=HermesTpx3PhotonClusteringSettings(
                    max_time_spread_ticks=491520,
                    min_cluster_size=2,
                    max_cluster_size=64,
                    min_pixel_tot_raw=1,
                    min_cluster_tot_raw=2,
                    max_cluster_tot_raw=65472,
                    max_aspect_ratio=3.0,
                    min_filled_fraction=0.5,
                ),
            ),
        ),
        event_reconstruction=event_reconstruction,
    )


# ---- resolve_photon_files -----------------------------------------------


def test_resolve_photon_files_auto_gathers_photons(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000-chip-0-part-00000.parquet",
        "run_000000-chip-1-part-00000.parquet",
    )
    resolved = resolve_photon_files(analysis, tmp_path / "analysis")
    assert [file.path.name for file in resolved] == [
        "run_000000-chip-0-part-00000.parquet",
        "run_000000-chip-1-part-00000.parquet",
    ]


def test_resolve_photon_files_excludes_photon_pixels(tmp_path: Path) -> None:
    # The photon stage writes a diagnostic photon-pixels file beside each photon
    # file; it is a different schema and must not be fed to event reconstruction.
    analysis = _analysis(
        tmp_path,
        "run_000000-chip-0-part-00000.parquet",
        "run_000000-chip-0-part-00000-photon-pixels.parquet",
    )
    resolved = resolve_photon_files(analysis, tmp_path / "analysis")
    assert [file.path.name for file in resolved] == [
        "run_000000-chip-0-part-00000.parquet"
    ]


# ---- skip detection -----------------------------------------------------


def test_fresh_file_is_not_previously_reconstructed(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    analysis_root = tmp_path / "analysis"
    input_file = resolve_photon_files(analysis, analysis_root)[0]
    assert not check_previous_reconstructed_file(analysis_root, input_file)


def test_summary_marks_file_previously_reconstructed(tmp_path: Path) -> None:
    analysis_root = tmp_path / "analysis"
    input_file = FileReference(
        path=analysis_root / "photons" / "run_000000-chip-0-part-00000.parquet"
    )
    summary_path = derive_summary_path(
        derive_output_path(analysis_root, input_file)
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.touch()

    assert check_previous_reconstructed_file(analysis_root, input_file)


def test_event_parquet_without_summary_is_not_complete(tmp_path: Path) -> None:
    # An event parquet without a summary is an incomplete run; the summary is the
    # completion marker, matching the binary's zero-event behavior where only the
    # summary is produced.
    analysis_root = tmp_path / "analysis"
    input_file = FileReference(
        path=analysis_root / "photons" / "run_000000-chip-0-part-00000.parquet"
    )
    output_file = derive_output_path(analysis_root, input_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.touch()

    assert not check_previous_reconstructed_file(analysis_root, input_file)


# ---- validate_program_and_algorithm -------------------------------------


def test_validate_rejects_dbscan(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000-chip-0-part-00000.parquet",
        clustering_algorithm="dbscan",
    )
    with pytest.raises(
        HermesEventReconstructionPreflightError, match="not implemented"
    ):
        validate_program_and_algorithm(analysis.event_reconstruction)


def test_validate_rejects_missing_executable(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    analysis.event_reconstruction.program.executable_path.unlink()
    with pytest.raises(
        HermesEventReconstructionPreflightError, match="executable does not exist"
    ):
        validate_program_and_algorithm(analysis.event_reconstruction)


def test_resolve_requires_event_reconstruction_config(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000-chip-0-part-00000.parquet",
        with_event_reconstruction=False,
    )
    with pytest.raises(
        HermesEventReconstructionPreflightError, match="not configured"
    ):
        resolve_photon_files(analysis, tmp_path / "analysis")


# ---- derive_event_reconstruction_command --------------------------------


def test_command_passes_named_flags_and_settings(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    event_reconstruction = analysis.event_reconstruction
    input_file = FileReference(
        path=tmp_path / "analysis"
        / "photons"
        / "run_000000-chip-0-part-00000.parquet"
    )
    output_file = derive_output_path(tmp_path / "analysis", input_file)
    command = derive_event_reconstruction_command(
        event_reconstruction,
        input_file,
        output_file,
        tmp_path / "settings.json",
    )
    assert command[1:] == [
        "--input",
        str(input_file.path),
        "--output",
        str(output_file),
        "--settings",
        str(tmp_path / "settings.json"),
    ]
    assert "--overwrite" not in command


def test_command_appends_overwrite_when_requested(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    event_reconstruction = analysis.event_reconstruction
    input_file = FileReference(
        path=tmp_path / "analysis"
        / "photons"
        / "run_000000-chip-0-part-00000.parquet"
    )
    command = derive_event_reconstruction_command(
        event_reconstruction,
        input_file,
        derive_output_path(tmp_path / "analysis", input_file),
        tmp_path / "settings.json",
        overwrite=True,
    )
    assert command[-1] == "--overwrite"
