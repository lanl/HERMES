from __future__ import annotations

import json
import stat
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hermes.analysis.hermes.reconstruction import (
    HermesReconstructionExecutionError,
    HermesReconstructionPreflightError,
    derive_reconstruction_command,
    derive_summary_path,
    execute_reconstruction,
    plan_reconstruction,
)
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    PhotonReconstructorProgram,
    Tpx3PhotonClusteringSettings,
    Tpx3PhotonReconstructionConfiguration,
    Tpx3SpidrUnpackerProgram,
)
from hermes.analysis.hermes.run import run_hermes_analysis
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_manager import StateManager


def _settings(**overrides: Any) -> Tpx3PhotonClusteringSettings:
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
    return Tpx3PhotonClusteringSettings(**base)


def _analysis(
    tmp_path: Path,
    *raw_names: str,
    settings: Tpx3PhotonClusteringSettings | None = None,
    clustering_algorithm: str = "connected_components",
    with_reconstruction: bool = True,
) -> HermesTpx3AnalysisState:
    unpacker_exe = tmp_path / "bin/hermes-tpx3-spidr"
    unpacker_exe.parent.mkdir(parents=True, exist_ok=True)
    unpacker_exe.touch()

    clusterer_exe = tmp_path / "bin/hermes-photon-clusterer"
    clusterer_exe.touch()

    raw_files: list[FileReference] = []
    for raw_name in raw_names:
        raw_path = tmp_path / "rawTpx3" / raw_name
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.touch()
        raw_files.append(FileReference(path=raw_path))

    analysis_directory = tmp_path / "analysis"
    reconstruction = None
    if with_reconstruction:
        reconstruction = Tpx3PhotonReconstructionConfiguration(
            program=PhotonReconstructorProgram(
                name="photon-clusterer-cpp",
                executable_path=clusterer_exe,
                version="0.1.0",
            ),
            pixel_data_directory=analysis_directory / "pixelHits",
            photon_output_directory=analysis_directory / "photons",
            settings=settings or _settings(),
            clustering_algorithm=clustering_algorithm,
        )

    return HermesTpx3AnalysisState(
        unpacker_program=Tpx3SpidrUnpackerProgram(
            name="tpx3-spidr-cpp",
            executable_path=unpacker_exe,
            version="0.1.0",
        ),
        analysis_directory=analysis_directory,
        tpx3_files=raw_files,
        photon_reconstruction=reconstruction,
    )


def _summary_dict(
    raw_stem: str,
    *,
    photon_count: int = 3,
    rejected: int = 1,
    save_photon_pixels: bool = False,
    corrected: bool = False,
) -> dict[str, Any]:
    events_files = [
        f"photons/{raw_stem}-chip-0-photon-events-part-00000.parquet"
    ]
    if save_photon_pixels:
        pixels = {
            "requested": True,
            "row_count": 7,
            "files": [
                f"photons/{raw_stem}-chip-0-photon-pixels-part-00000.parquet"
            ],
        }
    else:
        pixels = {"requested": False, "row_count": 0, "files": []}

    if corrected:
        timing = {
            "estimator": "leading_edge",
            "correction_model": "inverse",
            "calibration_file": "calibrations/tpx3/time-walk_example.json",
            "parameters": {"a": 1254855.58, "b": 10.6986},
            "high_tot_anchor": 23.0,
        }
        calibration_file: str | None = (
            "calibrations/tpx3/time-walk_example.json"
        )
    else:
        timing = {
            "estimator": "leading_edge",
            "correction_model": "none",
            "calibration_file": None,
            "parameters": {},
            "high_tot_anchor": None,
        }
        calibration_file = None

    return {
        "schema_version": 1,
        "reconstruction": {
            "pixel_rows_read": 100,
            "pixel_rows_below_min_tot": 0,
            "components_formed": photon_count + rejected,
            "photon_count": photon_count,
            "rejected_component_count": rejected,
            "rejection_counts": {
                "below_min_cluster_size": rejected,
                "above_max_cluster_size": 0,
                "below_min_cluster_tot": 0,
                "above_max_cluster_tot": 0,
                "above_max_aspect_ratio": 0,
                "below_min_filled_fraction": 0,
            },
            "quality_flag_counts": {
                "saturated_pixel": 0,
                "bridged_components": 0,
            },
            "warnings": [],
            "errors": [],
        },
        "clustering": {
            "algorithm": "connected_components",
            "settings": {
                "max_time_spread_ticks": 491520,
                "min_cluster_size": 2,
                "max_cluster_size": 64,
                "min_pixel_tot_raw": 1,
                "min_cluster_tot_raw": 2,
                "max_cluster_tot_raw": 65472,
                "max_aspect_ratio": 3.0,
                "min_filled_fraction": 0.5,
                "adjacency": 8,
                "position_averaging": "arithmetic",
                "photon_time_estimator": "leading_edge",
                "timewalk_calibration_file": calibration_file,
                "save_photon_pixels": save_photon_pixels,
            },
        },
        "photon_timing": timing,
        "parquet": {
            "input_pixel_data_files": [
                f"pixelHits/{raw_stem}-chip-0-part-00000.parquet"
            ],
            "photon_events": {
                "row_count": photon_count,
                "files": events_files,
            },
            "photon_pixels": pixels,
        },
        "processing_times_seconds": {
            "parquet_reading": 0.1,
            "clustering_and_filtering": 0.2,
            "parquet_writing": 0.1,
            "total": 0.4,
            "throughput": {
                "pixels_per_second": 250.0,
                "photons_per_second": 7.5,
            },
        },
    }


def _save_completed_files(
    analysis: HermesTpx3AnalysisState,
    raw_file: FileReference,
    *,
    photon_count: int = 3,
    save_photon_pixels: bool = False,
) -> None:
    stem = raw_file.path.stem
    summary = _summary_dict(
        stem,
        photon_count=photon_count,
        save_photon_pixels=save_photon_pixels,
    )
    photons_dir = analysis.analysis_directory / "photons"
    photons_dir.mkdir(parents=True, exist_ok=True)
    # photon_events file with a matching row count.
    pq.write_table(
        pa.table({"photon_id": list(range(photon_count))}),
        photons_dir / f"{stem}-chip-0-photon-events-part-00000.parquet",
    )
    if save_photon_pixels:
        pq.write_table(
            pa.table({"photon_id": [0]}),
            photons_dir / f"{stem}-chip-0-photon-pixels-part-00000.parquet",
        )
    summary_path = derive_summary_path(analysis, raw_file)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")


def _write_fake_clusterer(
    executable: Path,
    *,
    photon_count: int = 3,
    exit_code: int = 0,
    write_summary: bool = True,
) -> None:
    summary_literal = json.dumps(
        _summary_dict("PLACEHOLDER", photon_count=photon_count)
    )
    script = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import json
        import sys
        from pathlib import Path

        import pyarrow as pa
        import pyarrow.parquet as pq

        args = sys.argv[1:]
        values = {{}}
        i = 0
        while i < len(args):
            flag = args[i]
            if flag == "--overwrite":
                values[flag] = True
                i += 1
                continue
            values[flag] = args[i + 1]
            i += 2

        # --output is where files go; --input holds pixelHits/ (same dir here).
        analysis_dir = Path(values["--output"])
        stem = values["--base-file-name"]
        # settings arrive via --settings <file>; read to prove it is passed.
        settings = json.loads(Path(values["--settings"]).read_text())

        exit_code = {exit_code}
        write_summary = {write_summary}
        photon_count = {photon_count}

        if write_summary:
            photons = analysis_dir / "photons"
            photons.mkdir(parents=True, exist_ok=True)
            pq.write_table(
                pa.table({{"photon_id": list(range(photon_count))}}),
                photons / (stem + "-chip-0-photon-events-part-00000.parquet"),
            )
            summary = json.loads({summary_literal!r})
            summary["parquet"]["input_pixel_data_files"] = [
                "pixelHits/" + stem + "-chip-0-part-00000.parquet"
            ]
            summary["parquet"]["photon_events"]["files"] = [
                "photons/" + stem + "-chip-0-photon-events-part-00000.parquet"
            ]
            logs = analysis_dir / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            (logs / (stem + "-reconstruction-summary.json")).write_text(
                json.dumps(summary)
            )

        sys.exit(exit_code)
        """
    )
    executable.write_text(script, encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)


# ---- plan_reconstruction ------------------------------------------------


def test_plan_runs_when_no_output_exists(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    plan = plan_reconstruction(analysis)
    assert [action for _, action in plan] == ["run"]


def test_plan_skips_when_valid_summary_exists(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    _save_completed_files(analysis, analysis.tpx3_files[0])
    plan = plan_reconstruction(analysis)
    assert [action for _, action in plan] == ["skip"]


def test_plan_rejects_summary_with_mismatched_settings(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    _save_completed_files(analysis, analysis.tpx3_files[0])

    requested = _analysis(
        tmp_path,
        "run_000000.tpx3",
        settings=_settings(save_photon_pixels=True),
    )

    with pytest.raises(HermesReconstructionPreflightError, match="settings"):
        plan_reconstruction(requested)

def test_plan_rejects_orphan_photon_files(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    photons_dir = analysis.analysis_directory / "photons"
    photons_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table({"photon_id": [0]}),
        photons_dir / "run_000000-chip-0-photon-events-part-00000.parquet",
    )
    with pytest.raises(HermesReconstructionPreflightError, match="without a valid"):
        plan_reconstruction(analysis)


def test_plan_rejects_dbscan(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path, "run_000000.tpx3", clustering_algorithm="dbscan"
    )
    with pytest.raises(HermesReconstructionPreflightError, match="not implemented"):
        plan_reconstruction(analysis)


def test_plan_rejects_missing_executable(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    analysis.photon_reconstruction.program.executable_path.unlink()
    with pytest.raises(
        HermesReconstructionPreflightError, match="executable does not exist"
    ):
        plan_reconstruction(analysis)


def test_plan_requires_reconstruction_config(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path, "run_000000.tpx3", with_reconstruction=False
    )
    with pytest.raises(
        HermesReconstructionPreflightError, match="not configured"
    ):
        plan_reconstruction(analysis)


def test_plan_skips_when_pixels_requested_and_present(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000.tpx3",
        settings=_settings(save_photon_pixels=True),
    )
    _save_completed_files(
        analysis, analysis.tpx3_files[0], save_photon_pixels=True
    )
    plan = plan_reconstruction(analysis)
    assert [action for _, action in plan] == ["skip"]


def test_plan_rejects_summary_requesting_missing_pixels(tmp_path: Path) -> None:
    # The summary records photon_pixels output, but the pixels file is absent.
    analysis = _analysis(
        tmp_path,
        "run_000000.tpx3",
        settings=_settings(save_photon_pixels=True),
    )
    _save_completed_files(
        analysis, analysis.tpx3_files[0], save_photon_pixels=True
    )
    stem = analysis.tpx3_files[0].path.stem
    (
        analysis.analysis_directory
        / "photons"
        / f"{stem}-chip-0-photon-pixels-part-00000.parquet"
    ).unlink()
    with pytest.raises(HermesReconstructionPreflightError):
        plan_reconstruction(analysis)


# ---- derive_reconstruction_command --------------------------------------


def test_command_passes_named_flags_and_settings(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    reconstruction = analysis.photon_reconstruction
    command = derive_reconstruction_command(
        reconstruction,
        analysis.analysis_directory,
        "run_000000",
        tmp_path / "settings.json",
    )
    assert command[1:] == [
        "--input",
        str(analysis.analysis_directory),
        "--base-file-name",
        "run_000000",
        "--output",
        str(analysis.analysis_directory),
        "--settings",
        str(tmp_path / "settings.json"),
    ]
    assert "--overwrite" not in command


def test_command_appends_overwrite_when_requested(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    command = derive_reconstruction_command(
        analysis.photon_reconstruction,
        analysis.analysis_directory,
        "run_000000",
        tmp_path / "settings.json",
        overwrite=True,
    )
    assert command[-1] == "--overwrite"


# ---- execute_reconstruction ---------------------------------------------


def test_execute_success_returns_summary(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    _write_fake_clusterer(
        analysis.photon_reconstruction.program.executable_path,
        photon_count=5,
    )
    summary = execute_reconstruction(analysis, analysis.tpx3_files[0])
    assert summary.reconstruction.photon_count == 5


def test_execute_removes_temp_settings_file(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    _write_fake_clusterer(analysis.photon_reconstruction.program.executable_path)
    execute_reconstruction(analysis, analysis.tpx3_files[0])
    leftover = list(Path(tempfile.gettempdir()).glob(
        "run_000000-clustering-settings-*.json"
    ))
    assert leftover == []


def test_execute_raises_on_nonzero_exit(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    _write_fake_clusterer(
        analysis.photon_reconstruction.program.executable_path,
        exit_code=1,
        write_summary=False,
    )
    with pytest.raises(HermesReconstructionExecutionError, match="exited with code"):
        execute_reconstruction(analysis, analysis.tpx3_files[0])


def test_execute_raises_on_missing_summary(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    _write_fake_clusterer(
        analysis.photon_reconstruction.program.executable_path,
        write_summary=False,
    )
    with pytest.raises(HermesReconstructionPreflightError):
        execute_reconstruction(analysis, analysis.tpx3_files[0])


# ---- status flow through run_hermes_analysis ----------------------------


def _write_fake_unpacker(executable: Path) -> None:
    """A minimal unpacker that writes one pixel_data file and a valid summary."""
    script = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import json
        import sys
        from pathlib import Path

        import pyarrow as pa
        import pyarrow.parquet as pq

        args = sys.argv[1:]
        raw_file = Path(args[args.index("--input") + 1])
        analysis_dir = Path(args[args.index("--output") + 1])
        stem = raw_file.stem

        pixel_hits = analysis_dir / "pixelHits"
        pixel_hits.mkdir(parents=True, exist_ok=True)
        pq.write_table(
            pa.table({{
                "local_x": pa.array([0], pa.uint16()),
                "local_y": pa.array([0], pa.uint16()),
                "tot_raw": pa.array([10], pa.uint16()),
                "timestamp_canonical": pa.array([1], pa.uint64()),
            }}),
            pixel_hits / (stem + "-chip-0-part-00000.parquet"),
        )
        summary = {{
            "unpacking": {{
                "bytes_read": 0, "chunks_read": 0, "packets_read": 1,
                "pixel_data_packets": 1, "tdc_timestamps": 0,
                "heartbeat_packets": 0, "spidr_control_packets": 0,
                "tpx3_control_packets": 0, "unrecognized_packets": 0,
                "tdc1_rising": 0, "tdc1_falling": 0, "tdc2_rising": 0,
                "tdc2_falling": 0, "unknown_tdc_edges": 0,
                "errors": [], "warnings": [],
            }},
            "timestamp_processing": {{
                "heartbeat_pairs": {{"number_of_beats": 0}},
                "time_adjustments": {{
                    "pixel_packets": 1, "tdc_packets": 0,
                    "control_packets": 0, "failed": 0,
                }},
            }},
            "sorting": {{
                "strategy": "in_memory", "memory_budget_bytes": 0,
                "estimated_memory_bytes": 0, "temporary_runs_created": 0,
            }},
            "parquet": {{
                "pixel_data": {{
                    "row_count": 1,
                    "files": ["pixelHits/" + stem + "-chip-0-part-00000.parquet"],
                }},
                "tdc_timestamps": {{"row_count": 0, "files": []}},
                "heartbeat_packets": {{"row_count": 0, "files": []}},
                "control_packets": {{"row_count": 0, "files": []}},
                "unrecognized_packets": {{"row_count": 0, "files": []}},
                "errors": [],
            }},
            "processing_times_seconds": {{
                "canonical_time_seconds": 2.0345e-12, "unpacking": 0,
                "canonical_conversion": 0, "time_adjustments": 0,
                "sorting": 0, "parquet_writing": 0, "total": 0,
                "throughput": {{
                    "packets_per_second": 0, "megabytes_per_second": 0,
                }},
            }},
        }}
        logs = analysis_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / (stem + "-unpacker-summary.json")).write_text(json.dumps(summary))
        sys.exit(0)
        """
    )
    executable.write_text(script, encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)


def _manager(analysis: HermesTpx3AnalysisState, tmp_path: Path) -> StateManager:
    return StateManager(
        HermesRecord(
            measurement_info=MeasurementInfo(
                measurement_id="stage-5",
                run_number=1,
            ),
            environment=RuntimeEnvironment(working_dir=tmp_path),
            acquisition=None,
            analysis=analysis,
        ),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )


def test_run_hermes_analysis_completes_reconstruction(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    _write_fake_unpacker(analysis.unpacker_program.executable_path)
    _write_fake_clusterer(
        analysis.photon_reconstruction.program.executable_path,
        photon_count=4,
    )
    manager = _manager(analysis, tmp_path)

    run_hermes_analysis(manager)

    results = manager.get_state().analysis.results
    assert results.unpacking.status == "completed"
    assert results.reconstruction is not None
    assert results.reconstruction.status == "completed"
    assert results.reconstruction.started_at is not None
    assert results.reconstruction.completed_at is not None
    assert results.reconstruction.photon_count == 4


def test_run_hermes_analysis_marks_reconstruction_failed(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000.tpx3")
    _write_fake_unpacker(analysis.unpacker_program.executable_path)
    _write_fake_clusterer(
        analysis.photon_reconstruction.program.executable_path,
        exit_code=1,
        write_summary=False,
    )
    manager = _manager(analysis, tmp_path)

    with pytest.raises(HermesReconstructionExecutionError):
        run_hermes_analysis(manager)

    results = manager.get_state().analysis.results
    assert results.unpacking.status == "completed"
    assert results.reconstruction is not None
    assert results.reconstruction.status == "failed"
    assert results.reconstruction.errors


def test_run_hermes_analysis_without_reconstruction_leaves_result_none(
    tmp_path: Path,
) -> None:
    analysis = _analysis(
        tmp_path, "run_000000.tpx3", with_reconstruction=False
    )
    _write_fake_unpacker(analysis.unpacker_program.executable_path)
    manager = _manager(analysis, tmp_path)

    run_hermes_analysis(manager)

    results = manager.get_state().analysis.results
    assert results.unpacking.status == "completed"
    assert results.reconstruction is None
