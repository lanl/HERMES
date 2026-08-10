from __future__ import annotations

import json
import stat
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

import pytest

from hermes.runner.analysis.hermes.photon_reconstruction import (
    HermesReconstructionExecutionError,
    HermesReconstructionOutputError,
    HermesReconstructionPreflightError,
    check_previous_reconstructed_file,
    derive_output_path,
    derive_reconstruction_command,
    derive_summary_path,
    execute_reconstruction,
    resolve_pixel_files,
    validate_program_and_algorithm,
)
from hermes.runner.analysis.hermes.run import run_hermes_analysis
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3PhotonClusteringSettings,
    Tpx3PhotonReconstruction,
    Tpx3Unpacking,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import BinaryProgram, FileReference
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
    *pixel_names: str,
    settings: Tpx3PhotonClusteringSettings | None = None,
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
        reconstruction = Tpx3PhotonReconstruction(
            program=BinaryProgram(
                name="photon-clusterer-cpp",
                executable_path=clusterer_exe,
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
        photon_reconstruction=reconstruction,
    )


def _summary_dict(
    *,
    photon_count: int = 3,
    rejected: int = 1,
) -> dict[str, Any]:
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


def _write_fake_clusterer(
    executable: Path,
    *,
    photon_count: int = 3,
    exit_code: int = 0,
    write_summary: bool = True,
) -> None:
    """Write a fake clusterer that creates the photon file and sidecar summary."""
    summary_literal = json.dumps(_summary_dict(photon_count=photon_count))
    script = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import json
        import sys
        from pathlib import Path

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

        output_file = Path(values["--output"])
        # Prove the settings file is passed and readable.
        json.loads(Path(values["--settings"]).read_text())

        write_summary = {write_summary}
        if write_summary:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"")
            logs_directory = output_file.parent.parent / "logs" / "photons"
            logs_directory.mkdir(parents=True, exist_ok=True)
            summary_path = (
                logs_directory
                / (output_file.stem + "-reconstruction-summary.json")
            )
            summary_path.write_text({summary_literal!r})

        sys.exit({exit_code})
        """
    )
    executable.write_text(script, encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)


# ---- skip detection -----------------------------------------------------


def test_fresh_file_is_not_previously_reconstructed(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    analysis_root = tmp_path / "analysis"
    input_file = resolve_pixel_files(analysis, analysis_root)[0]
    assert not check_previous_reconstructed_file(analysis_root, input_file)


def test_summary_marks_file_previously_reconstructed(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    analysis_root = tmp_path / "analysis"
    input_file = FileReference(
        path=analysis_root / "pixel_hits" / "run_000000-chip-0-part-00000.parquet"
    )
    summary_path = derive_summary_path(
        derive_output_path(analysis_root, input_file)
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.touch()

    assert check_previous_reconstructed_file(analysis_root, input_file)


def test_photon_parquet_without_summary_is_not_complete(tmp_path: Path) -> None:
    # A photon parquet without a summary is an incomplete run; the summary is the
    # completion marker, matching the binary's zero-photon behavior where only
    # the summary is produced.
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    analysis_root = tmp_path / "analysis"
    input_file = FileReference(
        path=analysis_root / "pixel_hits" / "run_000000-chip-0-part-00000.parquet"
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
    with pytest.raises(HermesReconstructionPreflightError, match="not implemented"):
        validate_program_and_algorithm(analysis.photon_reconstruction)


def test_validate_rejects_missing_executable(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    analysis.photon_reconstruction.program.executable_path.unlink()
    with pytest.raises(
        HermesReconstructionPreflightError, match="executable does not exist"
    ):
        validate_program_and_algorithm(analysis.photon_reconstruction)


def test_resolve_requires_reconstruction_config(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000-chip-0-part-00000.parquet",
        with_reconstruction=False,
    )
    with pytest.raises(
        HermesReconstructionPreflightError, match="not configured"
    ):
        resolve_pixel_files(analysis, tmp_path / "analysis")


# ---- derive_reconstruction_command --------------------------------------


def test_command_passes_named_flags_and_settings(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    reconstruction = analysis.photon_reconstruction
    input_file = FileReference(
        path=tmp_path / "analysis"
        / "pixel_hits"
        / "run_000000-chip-0-part-00000.parquet"
    )
    output_file = derive_output_path(tmp_path / "analysis", input_file)
    command = derive_reconstruction_command(
        reconstruction,
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
    reconstruction = analysis.photon_reconstruction
    input_file = FileReference(
        path=tmp_path / "analysis"
        / "pixel_hits"
        / "run_000000-chip-0-part-00000.parquet"
    )
    command = derive_reconstruction_command(
        reconstruction,
        input_file,
        derive_output_path(tmp_path / "analysis", input_file),
        tmp_path / "settings.json",
        overwrite=True,
    )
    assert command[-1] == "--overwrite"


# ---- execute_reconstruction ---------------------------------------------


def test_execute_success_returns_summary(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    _write_fake_clusterer(
        analysis.photon_reconstruction.program.executable_path,
        photon_count=5,
    )
    input_file = FileReference(
        path=tmp_path / "analysis"
        / "pixel_hits"
        / "run_000000-chip-0-part-00000.parquet"
    )
    result = execute_reconstruction(analysis, tmp_path / "analysis", input_file)
    assert result.status == "completed"
    assert result.counts is not None
    assert result.counts.photon_count == 5


def test_execute_removes_temp_settings_file(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    _write_fake_clusterer(analysis.photon_reconstruction.program.executable_path)
    input_file = FileReference(
        path=tmp_path / "analysis"
        / "pixel_hits"
        / "run_000000-chip-0-part-00000.parquet"
    )
    execute_reconstruction(analysis, tmp_path / "analysis", input_file)
    leftover = list(
        Path(tempfile.gettempdir()).glob(
            "run_000000-chip-0-part-00000-clustering-settings-*.json"
        )
    )
    assert leftover == []


def test_execute_raises_on_nonzero_exit(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    _write_fake_clusterer(
        analysis.photon_reconstruction.program.executable_path,
        exit_code=1,
        write_summary=False,
    )
    input_file = FileReference(
        path=tmp_path / "analysis"
        / "pixel_hits"
        / "run_000000-chip-0-part-00000.parquet"
    )
    with pytest.raises(
        HermesReconstructionExecutionError, match="exited with code"
    ):
        execute_reconstruction(analysis, tmp_path / "analysis", input_file)


def test_execute_raises_on_missing_summary(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    _write_fake_clusterer(
        analysis.photon_reconstruction.program.executable_path,
        write_summary=False,
    )
    input_file = FileReference(
        path=tmp_path / "analysis"
        / "pixel_hits"
        / "run_000000-chip-0-part-00000.parquet"
    )
    with pytest.raises(HermesReconstructionOutputError):
        execute_reconstruction(analysis, tmp_path / "analysis", input_file)


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

        pixel_hits = analysis_dir / "pixel_hits"
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
                    "files": ["pixel_hits/" + stem + "-chip-0-part-00000.parquet"],
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
        logs = analysis_dir / "logs" / "unpacker"
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
            environment=RuntimeEnvironment(
                working_directory=tmp_path,
                analysis_directory=tmp_path / "analysis",
            ),
            acquisition=None,
            analysis=analysis,
        ),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )


def test_run_hermes_analysis_completes_reconstruction(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path)
    _write_fake_unpacker(analysis.unpacking.program.executable_path)
    _write_fake_clusterer(
        analysis.photon_reconstruction.program.executable_path,
        photon_count=4,
    )
    manager = _manager(analysis, tmp_path)

    run_hermes_analysis(manager)

    result_analysis = manager.get_state().analysis
    assert result_analysis.unpacking.results[0].status == "completed"
    reconstruction_results = result_analysis.photon_reconstruction.results
    assert len(reconstruction_results) == 1
    assert reconstruction_results[0].status == "completed"
    assert reconstruction_results[0].counts.photon_count == 4


def test_run_hermes_analysis_marks_reconstruction_failed(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path)
    _write_fake_unpacker(analysis.unpacking.program.executable_path)
    _write_fake_clusterer(
        analysis.photon_reconstruction.program.executable_path,
        exit_code=1,
        write_summary=False,
    )
    manager = _manager(analysis, tmp_path)

    with pytest.raises(HermesReconstructionExecutionError):
        run_hermes_analysis(manager)

    result_analysis = manager.get_state().analysis
    assert result_analysis.unpacking.results[0].status == "completed"
    reconstruction_results = result_analysis.photon_reconstruction.results
    assert reconstruction_results
    assert reconstruction_results[0].status == "failed"


def test_run_hermes_analysis_without_reconstruction_leaves_result_none(
    tmp_path: Path,
) -> None:
    analysis = _analysis(tmp_path, with_reconstruction=False)
    _write_fake_unpacker(analysis.unpacking.program.executable_path)
    manager = _manager(analysis, tmp_path)

    run_hermes_analysis(manager)

    result_analysis = manager.get_state().analysis
    assert result_analysis.unpacking.results[0].status == "completed"
    assert result_analysis.photon_reconstruction is None
