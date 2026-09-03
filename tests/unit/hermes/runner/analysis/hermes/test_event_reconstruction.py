from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hermes.runner.analysis.hermes.event_reconstruction import (
    HermesEventReconstructionPreflightError,
    check_previous_reconstructed_file,
    derive_batch_event_reconstruction_command,
    derive_event_reconstruction_command,
    derive_output_path,
    derive_summary_path,
    execute_event_reconstruction_batch,
    group_photon_files_by_stem,
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
    grouped: dict[str, list[Path]] = {}

    def fake_execute_batch(
        analysis: Any,
        analysis_root: Path,
        raw_file_stems: list[str],
        grouping: dict[str, list[Path]],
        *,
        overwrite: bool = False,
    ) -> list[HermesTpx3EventReconstructionResult | None]:
        calls.extend(raw_file_stems)
        grouped.update(grouping)
        return [
            HermesTpx3EventReconstructionResult(
                raw_file_stem=raw_file_stem,
                output_file=derive_output_path(analysis_root, raw_file_stem),
                status="completed",
            )
            for raw_file_stem in raw_file_stems
        ]

    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.run.execute_event_reconstruction_batch",
        fake_execute_batch,
    )

    run_hermes_analysis(manager)

    assert calls == ["run_000000"]
    # Both chips of the one stem were grouped together and handed to the batch.
    assert [path.name for path in grouped["run_000000"]] == [
        "run_000000_chip_0_photon_00000.parquet",
        "run_000000_chip_1_photon_00000.parquet",
    ]
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

    def fake_execute_batch(
        analysis: Any,
        analysis_root: Path,
        raw_file_stems: list[str],
        grouping: dict[str, list[Path]],
        *,
        overwrite: bool = False,
    ) -> list[HermesTpx3EventReconstructionResult | None]:
        return [
            HermesTpx3EventReconstructionResult(
                raw_file_stem=raw_file_stem,
                output_file=derive_output_path(analysis_root, raw_file_stem),
                status="completed",
            )
            for raw_file_stem in raw_file_stems
        ]

    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.run.execute_event_reconstruction_batch",
        fake_execute_batch,
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

    def fake_execute_batch(
        analysis: Any,
        analysis_root: Path,
        raw_file_stems: list[str],
        grouping: dict[str, list[Path]],
        *,
        overwrite: bool = False,
    ) -> list[HermesTpx3EventReconstructionResult | None]:
        # A stem that failed comes back as None in the batch's per-stem list; the
        # rest of the batch still succeeds.
        return [
            None
            if raw_file_stem == "boom"
            else HermesTpx3EventReconstructionResult(
                raw_file_stem=raw_file_stem,
                output_file=derive_output_path(analysis_root, raw_file_stem),
                status="completed",
            )
            for raw_file_stem in raw_file_stems
        ]

    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.run.execute_event_reconstruction_batch",
        fake_execute_batch,
    )

    run_hermes_analysis(manager)

    results = {
        r.raw_file_stem: r.status
        for r in manager.get_state().analysis.event_reconstruction.results
    }
    assert results == {"run_000000": "completed", "boom": "failed"}


# ---- group_photon_files_by_stem -----------------------------------------


def test_group_photon_files_by_stem_groups_and_sorts(tmp_path: Path) -> None:
    # Every chip and part of one stem is grouped under it, and each group is
    # sorted so parts read in a stable order regardless of directory order.
    analysis = _analysis(
        tmp_path,
        "run_000000_chip_1_photon_00000.parquet",
        "run_000000_chip_0_photon_00001.parquet",
        "run_000000_chip_0_photon_00000.parquet",
        "run_000001_chip_0_photon_00000.parquet",
    )
    grouping = group_photon_files_by_stem(analysis, tmp_path / "analysis")
    assert sorted(grouping) == ["run_000000", "run_000001"]
    assert [path.name for path in grouping["run_000000"]] == [
        "run_000000_chip_0_photon_00000.parquet",
        "run_000000_chip_0_photon_00001.parquet",
        "run_000000_chip_1_photon_00000.parquet",
    ]
    assert [path.name for path in grouping["run_000001"]] == [
        "run_000001_chip_0_photon_00000.parquet",
    ]


def test_group_photon_files_by_stem_missing_directory(tmp_path: Path) -> None:
    # No photon files means the photons directory is never created; grouping is
    # empty rather than an error.
    analysis = _analysis(tmp_path)
    assert group_photon_files_by_stem(analysis, tmp_path / "analysis") == {}


# ---- derive_batch_event_reconstruction_command --------------------------


def test_batch_command_passes_input_list_and_settings(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000_chip_0_photon_00000.parquet")
    analysis_root = tmp_path / "analysis"
    command = derive_batch_event_reconstruction_command(
        analysis.event_reconstruction,
        analysis_root,
        tmp_path / "list.txt",
        tmp_path / "settings.json",
    )
    assert command[1:] == [
        "--input",
        str(analysis_root),
        "--input-list",
        str(tmp_path / "list.txt"),
        "--settings",
        str(tmp_path / "settings.json"),
    ]
    assert "--overwrite" not in command


def test_batch_command_appends_overwrite_when_requested(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000_chip_0_photon_00000.parquet")
    command = derive_batch_event_reconstruction_command(
        analysis.event_reconstruction,
        tmp_path / "analysis",
        tmp_path / "list.txt",
        tmp_path / "settings.json",
        overwrite=True,
    )
    assert command[-1] == "--overwrite"


# ---- execute_event_reconstruction_batch ---------------------------------


def _valid_event_summary_dict() -> dict[str, Any]:
    """A minimal valid event reconstruction summary the binary would write."""
    return {
        "schema_version": 1,
        "reconstruction": {
            "photons_read": 10,
            "components_formed": 3,
            "event_count": 3,
            "quality_flag_counts": {"single_photon": 1, "duration_exceeded": 0},
            "min_photon_count_below": 0,
            "warnings": [],
            "errors": [],
        },
        "clustering": {
            "algorithm": "connected_components",
            "settings": {
                "spatial_link_radius_pixels": 10.0,
                "spatial_cells_per_axis": 5,
                "max_time_difference_ticks": 4915200.0,
                "max_event_duration_ticks": 14745600.0,
                "min_photon_count": 1,
                "save_event_photons": False,
                "derived_cell_width": 104,
            },
        },
        "event_timing": {"estimator": "earliest_photon"},
        "parquet": {
            "input_photon_events_files": [],
            "event_candidates": {"row_count": 0, "files": []},
        },
        "processing_times_seconds": {
            "photon_reading": 0.0,
            "clustering": 0.0,
            "parquet_writing": 0.0,
            "total": 0.0,
            "throughput": {
                "photons_per_second": 0.0,
                "events_per_second": 0.0,
            },
        },
    }


def test_batch_confirms_each_stem_from_its_own_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One process reconstructs both stems; each stem's result comes from its own
    # summary. The good stem's summary is written and confirmed; the bad stem's
    # is not, so it comes back None while the good stem still succeeds.
    analysis = _analysis(
        tmp_path,
        "good_chip_0_photon_00000.parquet",
        "bad_chip_0_photon_00000.parquet",
    )
    analysis_root = tmp_path / "analysis"
    grouping = group_photon_files_by_stem(analysis, analysis_root)

    captured: dict[str, list[str]] = {}

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        # The binary is handed the grouped photon paths in the list file, so it
        # never scans the photons directory.
        list_index = command.index("--input-list") + 1
        captured["photon_paths"] = (
            Path(command[list_index]).read_text().splitlines()
        )
        # Write only the good stem's summary; the bad stem gets none.
        summary_path = derive_summary_path(analysis_root, "good")
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(_valid_event_summary_dict()))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.event_reconstruction.subprocess.run",
        fake_run,
    )

    results = execute_event_reconstruction_batch(
        analysis, analysis_root, ["good", "bad"], grouping
    )

    assert captured["photon_paths"] == [
        str(grouping["good"][0]),
        str(grouping["bad"][0]),
    ]
    assert results[0] is not None
    assert results[0].raw_file_stem == "good"
    assert results[0].status == "completed"
    assert results[0].counts.event_count == 3
    assert results[1] is None


def test_batch_marks_every_stem_failed_when_launch_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis(
        tmp_path,
        "good_chip_0_photon_00000.parquet",
        "bad_chip_0_photon_00000.parquet",
    )
    analysis_root = tmp_path / "analysis"
    grouping = group_photon_files_by_stem(analysis, analysis_root)

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        raise OSError("cannot launch")

    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.event_reconstruction.subprocess.run",
        fake_run,
    )

    results = execute_event_reconstruction_batch(
        analysis, analysis_root, ["good", "bad"], grouping
    )
    assert results == [None, None]
