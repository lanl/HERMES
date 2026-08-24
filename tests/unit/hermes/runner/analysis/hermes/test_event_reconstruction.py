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
    resolve_raw_file_stems,
    validate_program_and_algorithm,
)
from hermes.runner.analysis.hermes.run import run_hermes_analysis
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3EventReconstruction,
    HermesTpx3EventReconstructionResult,
    HermesTpx3EventReconstructionSettings,
    HermesTpx3PhotonClustering,
    HermesTpx3PhotonClusteringSettings,
    HermesTpx3PhotonReconstruction,
    Tpx3Unpacking,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import BinaryProgram, FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_manager import StateManager


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
    photon_parquet_files: Any = "auto",
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
            photon_parquet_files=photon_parquet_files,
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


# ---- resolve_raw_file_stems ---------------------------------------------


def test_resolve_raw_file_stems_collapses_chips_and_parts(tmp_path: Path) -> None:
    # Two chips and two parts of one raw stem collapse to a single stem, because
    # whole-sensor reconstruction runs the whole raw stem together.
    analysis = _analysis(
        tmp_path,
        "run_000000_chip_0_photon_00000.parquet",
        "run_000000_chip_0_photon_00001.parquet",
        "run_000000_chip_1_photon_00000.parquet",
    )
    stems = resolve_raw_file_stems(analysis, tmp_path / "analysis")
    assert stems == ["run_000000"]


def test_resolve_raw_file_stems_sorts_unique_stems(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000001_chip_0_photon_00000.parquet",
        "run_000000_chip_0_photon_00000.parquet",
        "run_000000_chip_1_photon_00000.parquet",
    )
    stems = resolve_raw_file_stems(analysis, tmp_path / "analysis")
    assert stems == ["run_000000", "run_000001"]


def test_resolve_raw_file_stems_explicit_list(tmp_path: Path) -> None:
    analysis_root = tmp_path / "analysis"
    explicit = [
        FileReference(
            path=analysis_root / "photons" / "run_000000_chip_0_photon_00000.parquet"
        ),
        FileReference(
            path=analysis_root / "photons" / "run_000000_chip_1_photon_00000.parquet"
        ),
    ]
    analysis = _analysis(tmp_path, photon_parquet_files=explicit)
    stems = resolve_raw_file_stems(analysis, analysis_root)
    assert stems == ["run_000000"]


def test_resolve_raw_file_stems_rejects_malformed_name(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "not_a_photon_file.parquet")
    with pytest.raises(
        HermesEventReconstructionPreflightError, match="photon filename"
    ):
        resolve_raw_file_stems(analysis, tmp_path / "analysis")


def test_resolve_requires_event_reconstruction_config(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000_chip_0_photon_00000.parquet",
        with_event_reconstruction=False,
    )
    with pytest.raises(
        HermesEventReconstructionPreflightError, match="not configured"
    ):
        resolve_raw_file_stems(analysis, tmp_path / "analysis")


# ---- skip detection -----------------------------------------------------


def test_fresh_stem_is_not_previously_reconstructed(tmp_path: Path) -> None:
    analysis_root = tmp_path / "analysis"
    assert not check_previous_reconstructed_file(analysis_root, "run_000000")


def test_summary_marks_stem_previously_reconstructed(tmp_path: Path) -> None:
    analysis_root = tmp_path / "analysis"
    summary_path = derive_summary_path(analysis_root, "run_000000")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.touch()

    assert check_previous_reconstructed_file(analysis_root, "run_000000")


def test_event_parquet_without_summary_is_not_complete(tmp_path: Path) -> None:
    # An event parquet without a summary is an incomplete run; the summary is the
    # completion marker, matching the binary's zero-event behavior where only the
    # summary is produced.
    analysis_root = tmp_path / "analysis"
    output_file = derive_output_path(analysis_root, "run_000000")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.touch()

    assert not check_previous_reconstructed_file(analysis_root, "run_000000")


# ---- path derivation ----------------------------------------------------


def test_derive_output_path_uses_underscore_event_candidates(
    tmp_path: Path,
) -> None:
    analysis_root = tmp_path / "analysis"
    output_file = derive_output_path(analysis_root, "run_000000")
    assert output_file == (
        analysis_root / "events" / "run_000000_event_candidates.parquet"
    )


def test_derive_summary_path_uses_event_reconstruction_logs(
    tmp_path: Path,
) -> None:
    analysis_root = tmp_path / "analysis"
    summary_path = derive_summary_path(analysis_root, "run_000000")
    assert summary_path == (
        analysis_root
        / "logs"
        / "event_reconstruction"
        / "run_000000_event_reconstruction_summary.json"
    )


# ---- validate_program_and_algorithm -------------------------------------


def test_validate_rejects_dbscan(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000_chip_0_photon_00000.parquet",
        clustering_algorithm="dbscan",
    )
    with pytest.raises(
        HermesEventReconstructionPreflightError, match="not implemented"
    ):
        validate_program_and_algorithm(analysis.event_reconstruction)


def test_validate_rejects_missing_executable(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000_chip_0_photon_00000.parquet")
    analysis.event_reconstruction.program.executable_path.unlink()
    with pytest.raises(
        HermesEventReconstructionPreflightError, match="executable does not exist"
    ):
        validate_program_and_algorithm(analysis.event_reconstruction)


# ---- derive_event_reconstruction_command --------------------------------


def test_command_passes_named_flags_and_settings(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000_chip_0_photon_00000.parquet")
    event_reconstruction = analysis.event_reconstruction
    analysis_root = tmp_path / "analysis"
    command = derive_event_reconstruction_command(
        event_reconstruction,
        analysis_root,
        "run_000000",
        tmp_path / "settings.json",
    )
    assert command[1:] == [
        "--input",
        str(analysis_root),
        "--raw-file-stem",
        "run_000000",
        "--settings",
        str(tmp_path / "settings.json"),
    ]
    assert "--overwrite" not in command


def test_command_appends_overwrite_when_requested(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000_chip_0_photon_00000.parquet")
    event_reconstruction = analysis.event_reconstruction
    command = derive_event_reconstruction_command(
        event_reconstruction,
        tmp_path / "analysis",
        "run_000000",
        tmp_path / "settings.json",
        overwrite=True,
    )
    assert command[-1] == "--overwrite"


# ---- run.py grouping by raw stem ----------------------------------------


def _event_only_record(
    analysis: HermesTpx3AnalysisState,
    tmp_path: Path,
) -> HermesRecord:
    return HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id="stage-3", run="test-run"
        ),
        environment=RuntimeEnvironment(
            working_directory=tmp_path,
            analysis_directory=tmp_path / "analysis",
        ),
        acquisition=None,
        analysis=analysis,
    )


def test_run_groups_two_chips_of_one_stem_into_one_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Whole-sensor reconstruction runs once per raw stem, so two chips of one
    # stem produce a single reconstruction call and a single result.
    analysis = _analysis(
        tmp_path,
        "run_000000_chip_0_photon_00000.parquet",
        "run_000000_chip_1_photon_00000.parquet",
    )
    analysis.unpacking = None
    analysis.photon_reconstruction = None
    manager = StateManager(
        _event_only_record(analysis, tmp_path),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )

    calls: list[str] = []

    def fake_execute(
        analysis: Any,
        analysis_root: Path,
        raw_file_stem: str,
        *,
        overwrite: bool = False,
    ) -> HermesTpx3EventReconstructionResult:
        calls.append(raw_file_stem)
        return HermesTpx3EventReconstructionResult(
            raw_file_stem=raw_file_stem,
            output_file=derive_output_path(analysis_root, raw_file_stem),
            status="completed",
        )

    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.run.execute_event_reconstruction",
        fake_execute,
    )

    run_hermes_analysis(manager)

    assert calls == ["run_000000"]
    results = manager.get_state().analysis.event_reconstruction.results
    assert [(r.raw_file_stem, r.status) for r in results] == [
        ("run_000000", "completed")
    ]


def test_run_skips_stems_with_existing_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000_chip_0_photon_00000.parquet",
        "run_000001_chip_0_photon_00000.parquet",
    )
    analysis.unpacking = None
    analysis.photon_reconstruction = None
    analysis_root = tmp_path / "analysis"
    # run_000000 already has a summary, so only run_000001 is reconstructed.
    summary_path = derive_summary_path(analysis_root, "run_000000")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.touch()
    manager = StateManager(
        _event_only_record(analysis, tmp_path),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )

    def fake_execute(
        analysis: Any,
        analysis_root: Path,
        raw_file_stem: str,
        *,
        overwrite: bool = False,
    ) -> HermesTpx3EventReconstructionResult:
        return HermesTpx3EventReconstructionResult(
            raw_file_stem=raw_file_stem,
            output_file=derive_output_path(analysis_root, raw_file_stem),
            status="completed",
        )

    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.run.execute_event_reconstruction",
        fake_execute,
    )

    run_hermes_analysis(manager)

    results = {
        r.raw_file_stem: r.status
        for r in manager.get_state().analysis.event_reconstruction.results
    }
    assert results == {"run_000000": "skipped", "run_000001": "completed"}


def test_run_marks_failed_stem_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000_chip_0_photon_00000.parquet",
        "boom_chip_0_photon_00000.parquet",
    )
    analysis.unpacking = None
    analysis.photon_reconstruction = None
    manager = StateManager(
        _event_only_record(analysis, tmp_path),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )

    from hermes.runner.analysis.hermes.event_reconstruction import (
        HermesEventReconstructionExecutionError,
    )

    def fake_execute(
        analysis: Any,
        analysis_root: Path,
        raw_file_stem: str,
        *,
        overwrite: bool = False,
    ) -> HermesTpx3EventReconstructionResult:
        if raw_file_stem == "boom":
            raise HermesEventReconstructionExecutionError("boom failed")
        return HermesTpx3EventReconstructionResult(
            raw_file_stem=raw_file_stem,
            output_file=derive_output_path(analysis_root, raw_file_stem),
            status="completed",
        )

    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.run.execute_event_reconstruction",
        fake_execute,
    )

    run_hermes_analysis(manager)

    results = {
        r.raw_file_stem: r.status
        for r in manager.get_state().analysis.event_reconstruction.results
    }
    assert results == {"run_000000": "completed", "boom": "failed"}
