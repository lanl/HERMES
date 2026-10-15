from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from loguru import logger

from hermes.runner.analysis.hermes.photon_reconstruction import (
    HermesPhotonReconstructionPreflightError,
    build_clustering_settings_json,
    check_previous_reconstructed_file,
    derive_output_path,
    derive_reconstruction_command,
    derive_summary_path,
    load_photon_timing,
    resolve_pixel_files,
    validate_program_and_algorithm,
)
from hermes.runner.analysis.hermes.run import run_hermes_analysis
from hermes.shipped_files import default_timewalk_calibration
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3PhotonClustering,
    HermesTpx3PhotonClusteringSettings,
    HermesTpx3PhotonReconstruction,
    HermesTpx3PhotonReconstructionResult,
    HermesTpx3PhotonTimingSummary,
    Tpx3Unpacking,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import BinaryProgram, FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_manager import StateManager


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
    unpacker_exe.chmod(0o755)

    clusterer_exe = tmp_path / "bin/hermes-photon-clusterer"
    clusterer_exe.touch()
    clusterer_exe.chmod(0o755)

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


def _write_summary(
    analysis_root: Path,
    input_file: FileReference,
    timing: HermesTpx3PhotonTimingSummary,
) -> None:
    summary_path = derive_summary_path(analysis_root, input_file)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps({
        "measurement_info": {"measurement_id": "stage-5", "run": "test-run"},
        "reconstruction": {
            "pixels_read": 0, "clusters_formed": 0, "rejected_clusters": 0,
            "total_photons": 0, "warnings": [], "errors": [],
            "rejection_reasons": {
                "below_min_cluster_size": 0, "above_max_cluster_size": 0,
                "below_min_cluster_tot": 0, "above_max_cluster_tot": 0,
                "above_max_aspect_ratio": 0, "below_min_filled_fraction": 0,
            },
            "quality_flag_counts": {"saturated_pixel": 0, "bridged_components": 0},
        },
        "clustering": {"algorithm": "connected_components", "settings": {}},
        "photon_timing": timing.model_dump(mode="json"),
        "parquet_files": {
            "input_pixel_data_file": [str(input_file.path)],
            "photons": {"row_count": 0, "files": []},
            "pixel_clusters": {"requested": False, "row_count": 0, "files": []},
        },
        "processing_times_seconds": {
            "parquet_reading": 0, "clustering_and_filtering": 0,
            "parquet_writing": 0, "total": 0,
            "throughput": {"pixels_per_second": 0, "photons_per_second": 0},
        },
    }), encoding="utf-8")


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


def test_output_paths_keep_pixel_file_chip_number(tmp_path: Path) -> None:
    analysis_root = tmp_path / "analysis"
    chip0 = FileReference(
        path=analysis_root / "pixel_hits" / "run_000000_chip_0_pixels_00000.parquet"
    )
    chip1 = FileReference(
        path=analysis_root / "pixel_hits" / "run_000000_chip_1_pixels_00000.parquet"
    )

    assert derive_output_path(analysis_root, chip0) == (
        analysis_root / "photons" / "run_000000_chip_0_photon_00000.parquet"
    )
    assert derive_output_path(analysis_root, chip1) == (
        analysis_root / "photons" / "run_000000_chip_1_photon_00000.parquet"
    )
    assert derive_summary_path(analysis_root, chip0) == (
        analysis_root
        / "logs"
        / "photon_reconstruction"
        / "run_000000_chip_0_photon_reconstruction_summary_00000.json"
    )
    assert derive_summary_path(analysis_root, chip1) == (
        analysis_root
        / "logs"
        / "photon_reconstruction"
        / "run_000000_chip_1_photon_reconstruction_summary_00000.json"
    )


def test_summary_path_keeps_part_index_distinct(tmp_path: Path) -> None:
    # A chip's later parts must not overwrite part 00000's summary, or
    # check_previous_reconstructed_file would skip them on rerun.
    analysis_root = tmp_path / "analysis"
    part0 = FileReference(
        path=analysis_root / "pixel_hits" / "run_000000_chip_0_pixels_00000.parquet"
    )
    part1 = FileReference(
        path=analysis_root / "pixel_hits" / "run_000000_chip_0_pixels_00001.parquet"
    )

    assert derive_summary_path(analysis_root, part0) != derive_summary_path(
        analysis_root, part1
    )


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


# ---- build_clustering_settings_json -------------------------------------


def test_settings_json_resolves_default_timewalk_calibration(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000_chip_0_pixels_00000.parquet",
        settings=_settings(timewalk_calibration_file="default"),
    )

    settings_json = build_clustering_settings_json(analysis)

    # The binary needs a real file, never the literal keyword.
    assert settings_json["timewalk"]["calibration_file"] == str(
        default_timewalk_calibration()
    )


def test_settings_json_keeps_explicit_timewalk_path(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000_chip_0_pixels_00000.parquet",
        settings=_settings(timewalk_calibration_file="/tmp/my-cal.json"),
    )

    settings_json = build_clustering_settings_json(analysis)

    assert settings_json["timewalk"]["calibration_file"] == "/tmp/my-cal.json"


def test_settings_json_omits_correction_when_unset(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000_chip_0_pixels_00000.parquet")

    settings_json = build_clustering_settings_json(analysis)

    assert settings_json["timewalk"] == {"method": "none", "calibration_file": None}


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


def test_run_keeps_completed_results_the_record_already_lists(
    tmp_path: Path,
) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000_chip_0_pixels_00000.parquet",
        "run_000001_chip_0_pixels_00000.parquet",
    )
    analysis.unpacking = None
    analysis_root = tmp_path / "analysis"
    listed, other = resolve_pixel_files(analysis, analysis_root)
    for input_file in (listed, other):
        _write_summary(analysis_root, input_file, load_photon_timing(analysis))
    # The first pixel file was reconstructed by an earlier pass of this run.
    analysis.photon_reconstruction.results = [
        HermesTpx3PhotonReconstructionResult(
            input_file=listed,
            output_file=derive_output_path(analysis_root, listed),
            status="completed",
        )
    ]
    manager = StateManager(
        HermesRecord(
            measurement_info=_measurement_info(),
            environment=RuntimeEnvironment(
                working_directory=tmp_path,
                analysis_directory=analysis_root,
            ),
            acquisition=None,
            analysis=analysis,
        ),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )
    records: list[dict[str, Any]] = []
    sink_id = logger.add(
        lambda message: records.append(message.record),
        filter=lambda record: record["extra"].get("event_type")
        == "analysis.tpx3_reconstruction.skipped",
    )
    try:
        run_hermes_analysis(manager)
    finally:
        logger.remove(sink_id)

    results = {
        result.input_file.path.name: result.status
        for result in manager.get_state().analysis.photon_reconstruction.results
    }
    assert results == {
        "run_000000_chip_0_pixels_00000.parquet": "completed",
        "run_000001_chip_0_pixels_00000.parquet": "skipped",
    }
    assert [Path(record["extra"]["pixel_file"]).name for record in records] == [
        "run_000001_chip_0_pixels_00000.parquet"
    ]


@pytest.mark.parametrize("conflict_index", [0, 1])
def test_restart_timing_conflict_preserves_all_previous_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, conflict_index: int,
) -> None:
    analysis = _analysis(
        tmp_path, "run_000000_chip_0_pixels_00000.parquet",
        "run_000001_chip_0_pixels_00000.parquet",
    )
    analysis.unpacking = None
    analysis_root = tmp_path / "analysis"
    inputs = resolve_pixel_files(analysis, analysis_root)
    timing = load_photon_timing(analysis)
    for index, input_file in enumerate(inputs):
        _write_summary(
            analysis_root, input_file,
            timing.model_copy(update={"estimator": "leading_edge"})
            if index == conflict_index else timing,
        )
    analysis.photon_reconstruction.results = [
        HermesTpx3PhotonReconstructionResult(
            input_file=file, output_file=derive_output_path(analysis_root, file),
            status="completed",
        ) for file in inputs
    ]
    # A new input queued before a conflict must not be executed or marked failed.
    new_input = analysis_root / "pixel_hits/aaa_chip_0_pixels_00000.parquet"
    new_input.touch()
    manager = StateManager(
        HermesRecord(
            measurement_info=_measurement_info(),
            environment=RuntimeEnvironment(
                working_directory=tmp_path, analysis_directory=analysis_root,
            ),
            acquisition=None, analysis=analysis,
        ),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )
    before = manager.get_state().analysis.photon_reconstruction.results
    summary_bytes = {
        derive_summary_path(analysis_root, file):
            derive_summary_path(analysis_root, file).read_bytes()
        for file in inputs
    }
    def unexpected_execution(*args: object, **kwargs: object) -> None:
        pytest.fail("reconstruction started before all restart checks completed")
    monkeypatch.setattr(
        "hermes.runner.analysis.hermes.run.execute_reconstruction",
        unexpected_execution,
    )
    with pytest.raises(HermesPhotonReconstructionPreflightError, match="overwrite"):
        run_hermes_analysis(manager)
    assert manager.get_state().analysis.photon_reconstruction.results == before
    assert all(path.read_bytes() == contents for path, contents in summary_bytes.items())


def test_restart_rejects_boolean_slope_even_when_it_equals_saved_number(
    tmp_path: Path,
) -> None:
    calibration = tmp_path / "curve.json"
    curve = {
        "model": "linear", "parameters": {"m": 1.0},
        "high_tot_anchor": 30, "time_unit": "canonical_ticks",
    }
    calibration.write_text(json.dumps(curve), encoding="utf-8")
    analysis = _analysis(
        tmp_path, "run_chip_0_pixels_00000.parquet",
        settings=_settings(timewalk={
            "method": "calibration", "calibration_file": calibration,
        }),
    )
    analysis.unpacking = None
    analysis_root = tmp_path / "analysis"
    input_file = resolve_pixel_files(analysis, analysis_root)[0]
    _write_summary(analysis_root, input_file, load_photon_timing(analysis))
    assert check_previous_reconstructed_file(analysis_root, input_file, analysis)
    curve["parameters"] = {"m": True}
    calibration.write_text(json.dumps(curve), encoding="utf-8")
    with pytest.raises(HermesPhotonReconstructionPreflightError, match="numeric"):
        check_previous_reconstructed_file(analysis_root, input_file, analysis)
    analysis.photon_reconstruction.results = [
        HermesTpx3PhotonReconstructionResult(
            input_file=input_file,
            output_file=derive_output_path(analysis_root, input_file),
            status="completed",
        ),
    ]
    manager = StateManager(
        HermesRecord(
            measurement_info=_measurement_info(),
            environment=RuntimeEnvironment(
                working_directory=tmp_path, analysis_directory=analysis_root,
            ),
            acquisition=None, analysis=analysis,
        ),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )
    before = manager.get_state().analysis.photon_reconstruction.results
    with pytest.raises(HermesPhotonReconstructionPreflightError, match="numeric"):
        run_hermes_analysis(manager)
    assert manager.get_state().analysis.photon_reconstruction.results == before
