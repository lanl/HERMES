from __future__ import annotations

import json
import stat
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

import pytest

from hermes.runner.analysis.hermes.event_reconstruction import (
    HermesEventReconstructionExecutionError,
    HermesEventReconstructionOutputError,
    HermesEventReconstructionPreflightError,
    derive_event_reconstruction_command,
    derive_output_path,
    derive_summary_path,
    execute_event_reconstruction,
    plan_event_reconstruction,
    resolve_photon_files,
)
from hermes.runner.analysis.hermes.run import run_hermes_analysis
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3EventReconstruction,
    Tpx3EventReconstructionSettings,
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


def _settings(**overrides: Any) -> Tpx3EventReconstructionSettings:
    base: dict[str, Any] = {
        "spatial_link_radius_pixels": 10.0,
        "spatial_cells_per_axis": 5,
        "max_time_difference_ticks": 4915200.0,
        "max_event_duration_ticks": 14745600.0,
        "min_photon_count": 1,
        "save_event_photons": False,
    }
    base.update(overrides)
    return Tpx3EventReconstructionSettings(**base)


def _analysis(
    tmp_path: Path,
    *photon_names: str,
    settings: Tpx3EventReconstructionSettings | None = None,
    clustering_algorithm: str = "connected_components",
    with_event_reconstruction: bool = True,
) -> HermesTpx3AnalysisState:
    unpacker_exe = tmp_path / "bin/hermes-tpx3-spidr"
    unpacker_exe.parent.mkdir(parents=True, exist_ok=True)
    unpacker_exe.touch()

    clusterer_exe = tmp_path / "bin/hermes-photon-clusterer"
    clusterer_exe.touch()

    event_exe = tmp_path / "bin/hermes-event-reconstructor"
    event_exe.touch()

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
        event_reconstruction = Tpx3EventReconstruction(
            program=BinaryProgram(
                name="event-reconstructor-cpp",
                executable_path=event_exe,
                version="0.1.0",
            ),
            settings=settings or _settings(),
            clustering_algorithm=clustering_algorithm,
        )

    return HermesTpx3AnalysisState(
        analysis_directory=analysis_directory,
        unpacking=Tpx3Unpacking(
            program=BinaryProgram(
                name="tpx3-spidr-cpp",
                executable_path=unpacker_exe,
                version="0.1.0",
            ),
            tpx3_files=[FileReference(path=raw_path)],
        ),
        photon_reconstruction=Tpx3PhotonReconstruction(
            program=BinaryProgram(
                name="photon-clusterer-cpp",
                executable_path=clusterer_exe,
                version="0.1.0",
            ),
            settings=Tpx3PhotonClusteringSettings(
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
        event_reconstruction=event_reconstruction,
    )


def _summary_dict(*, event_count: int = 3) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "reconstruction": {
            "photons_read": event_count + 5,
            "components_formed": event_count,
            "event_count": event_count,
            "quality_flag_counts": {
                "single_photon": 1,
                "duration_exceeded": 0,
            },
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
                "derived_cell_width_pixels": 52,
            },
        },
        "event_timing": {"estimator": "earliest_photon"},
        "parquet": {
            "input_photon_events_files": [
                "photons/run_000000-chip-0-part-00000.parquet"
            ],
            "event_candidates": {
                "row_count": event_count,
                "files": ["events/run_000000-chip-0-part-00000.parquet"],
            },
        },
        "processing_times_seconds": {
            "photon_reading": 0.1,
            "clustering": 0.2,
            "parquet_writing": 0.1,
            "total": 0.4,
            "throughput": {
                "photons_per_second": 20.0,
                "events_per_second": 7.5,
            },
        },
    }


def _write_fake_reconstructor(
    executable: Path,
    *,
    event_count: int = 3,
    exit_code: int = 0,
    write_summary: bool = True,
) -> None:
    """Write a fake reconstructor that creates the event file and summary JSON."""
    summary_literal = json.dumps(_summary_dict(event_count=event_count))
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
            logs_directory = output_file.parent.parent / "logs" / "events"
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


# ---- resolve_photon_files -----------------------------------------------


def test_resolve_photon_files_auto_gathers_photons(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000-chip-0-part-00000.parquet",
        "run_000000-chip-1-part-00000.parquet",
    )
    resolved = resolve_photon_files(analysis)
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
    resolved = resolve_photon_files(analysis)
    assert [file.path.name for file in resolved] == [
        "run_000000-chip-0-part-00000.parquet"
    ]


# ---- plan_event_reconstruction ------------------------------------------


def test_plan_runs_when_no_output_exists(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    plan = plan_event_reconstruction(analysis)
    assert [action for _, action in plan] == ["run"]


def test_plan_skips_when_summary_exists(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    event_reconstruction = analysis.event_reconstruction
    input_file = FileReference(
        path=analysis.analysis_directory
        / "photons"
        / "run_000000-chip-0-part-00000.parquet"
    )
    summary_path = derive_summary_path(
        derive_output_path(event_reconstruction, input_file)
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.touch()

    plan = plan_event_reconstruction(analysis)
    assert [action for _, action in plan] == ["skip"]


def test_plan_runs_when_only_event_parquet_exists(tmp_path: Path) -> None:
    # An event parquet without a summary is an incomplete run; it must re-run so
    # the summary (the completion marker) gets written, matching the binary's
    # zero-event behavior where only the summary is produced.
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    event_reconstruction = analysis.event_reconstruction
    input_file = FileReference(
        path=analysis.analysis_directory
        / "photons"
        / "run_000000-chip-0-part-00000.parquet"
    )
    output_file = derive_output_path(event_reconstruction, input_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.touch()

    plan = plan_event_reconstruction(analysis)
    assert [action for _, action in plan] == ["run"]


def test_plan_runs_all_when_overwrite(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    event_reconstruction = analysis.event_reconstruction
    input_file = FileReference(
        path=analysis.analysis_directory
        / "photons"
        / "run_000000-chip-0-part-00000.parquet"
    )
    output_file = derive_output_path(event_reconstruction, input_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.touch()

    plan = plan_event_reconstruction(analysis, overwrite=True)
    assert [action for _, action in plan] == ["run"]


def test_plan_rejects_dbscan(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000-chip-0-part-00000.parquet",
        clustering_algorithm="dbscan",
    )
    with pytest.raises(
        HermesEventReconstructionPreflightError, match="not implemented"
    ):
        plan_event_reconstruction(analysis)


def test_plan_rejects_missing_executable(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    analysis.event_reconstruction.program.executable_path.unlink()
    with pytest.raises(
        HermesEventReconstructionPreflightError, match="executable does not exist"
    ):
        plan_event_reconstruction(analysis)


def test_plan_requires_event_reconstruction_config(tmp_path: Path) -> None:
    analysis = _analysis(
        tmp_path,
        "run_000000-chip-0-part-00000.parquet",
        with_event_reconstruction=False,
    )
    with pytest.raises(
        HermesEventReconstructionPreflightError, match="not configured"
    ):
        plan_event_reconstruction(analysis)


# ---- derive_event_reconstruction_command --------------------------------


def test_command_passes_named_flags_and_settings(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    event_reconstruction = analysis.event_reconstruction
    input_file = FileReference(
        path=analysis.analysis_directory
        / "photons"
        / "run_000000-chip-0-part-00000.parquet"
    )
    output_file = derive_output_path(event_reconstruction, input_file)
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
        path=analysis.analysis_directory
        / "photons"
        / "run_000000-chip-0-part-00000.parquet"
    )
    command = derive_event_reconstruction_command(
        event_reconstruction,
        input_file,
        derive_output_path(event_reconstruction, input_file),
        tmp_path / "settings.json",
        overwrite=True,
    )
    assert command[-1] == "--overwrite"


# ---- execute_event_reconstruction ---------------------------------------


def test_execute_success_returns_summary(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    _write_fake_reconstructor(
        analysis.event_reconstruction.program.executable_path,
        event_count=5,
    )
    input_file = FileReference(
        path=analysis.analysis_directory
        / "photons"
        / "run_000000-chip-0-part-00000.parquet"
    )
    result = execute_event_reconstruction(analysis, input_file)
    assert result.status == "completed"
    assert result.counts is not None
    assert result.counts.event_count == 5


def test_execute_removes_temp_settings_file(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    _write_fake_reconstructor(
        analysis.event_reconstruction.program.executable_path
    )
    input_file = FileReference(
        path=analysis.analysis_directory
        / "photons"
        / "run_000000-chip-0-part-00000.parquet"
    )
    execute_event_reconstruction(analysis, input_file)
    leftover = list(
        Path(tempfile.gettempdir()).glob(
            "run_000000-chip-0-part-00000-event-settings-*.json"
        )
    )
    assert leftover == []


def test_execute_raises_on_nonzero_exit(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    _write_fake_reconstructor(
        analysis.event_reconstruction.program.executable_path,
        exit_code=1,
        write_summary=False,
    )
    input_file = FileReference(
        path=analysis.analysis_directory
        / "photons"
        / "run_000000-chip-0-part-00000.parquet"
    )
    with pytest.raises(
        HermesEventReconstructionExecutionError, match="exited with code"
    ):
        execute_event_reconstruction(analysis, input_file)


def test_execute_raises_on_missing_summary(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path, "run_000000-chip-0-part-00000.parquet")
    _write_fake_reconstructor(
        analysis.event_reconstruction.program.executable_path,
        write_summary=False,
    )
    input_file = FileReference(
        path=analysis.analysis_directory
        / "photons"
        / "run_000000-chip-0-part-00000.parquet"
    )
    with pytest.raises(HermesEventReconstructionOutputError):
        execute_event_reconstruction(analysis, input_file)


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
        logs = analysis_dir / "logs" / "unpacker"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / (stem + "-unpacker-summary.json")).write_text(json.dumps(summary))
        sys.exit(0)
        """
    )
    executable.write_text(script, encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)


def _write_fake_clusterer(executable: Path) -> None:
    """A minimal clusterer that writes one photon file and a valid summary."""
    summary_literal = json.dumps(
        {
            "schema_version": 1,
            "reconstruction": {
                "pixel_rows_read": 1,
                "pixel_rows_below_min_tot": 0,
                "components_formed": 1,
                "photon_count": 1,
                "rejected_component_count": 0,
                "rejection_counts": {
                    "below_min_cluster_size": 0,
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
                    "pixels_per_second": 2.5,
                    "photons_per_second": 2.5,
                },
            },
        }
    )
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
        json.loads(Path(values["--settings"]).read_text())

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(b"")
        logs_directory = output_file.parent.parent / "logs" / "photons"
        logs_directory.mkdir(parents=True, exist_ok=True)
        summary_path = (
            logs_directory / (output_file.stem + "-reconstruction-summary.json")
        )
        summary_path.write_text({summary_literal!r})
        sys.exit(0)
        """
    )
    executable.write_text(script, encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)


def _manager(analysis: HermesTpx3AnalysisState, tmp_path: Path) -> StateManager:
    return StateManager(
        HermesRecord(
            measurement_info=MeasurementInfo(
                measurement_id="stage-9c",
                run_number=1,
            ),
            environment=RuntimeEnvironment(working_dir=tmp_path),
            acquisition=None,
            analysis=analysis,
        ),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )


def test_run_hermes_analysis_completes_event_reconstruction(
    tmp_path: Path,
) -> None:
    analysis = _analysis(tmp_path)
    _write_fake_unpacker(analysis.unpacking.program.executable_path)
    _write_fake_clusterer(analysis.photon_reconstruction.program.executable_path)
    _write_fake_reconstructor(
        analysis.event_reconstruction.program.executable_path,
        event_count=4,
    )
    manager = _manager(analysis, tmp_path)

    run_hermes_analysis(manager)

    result_analysis = manager.get_state().analysis
    assert result_analysis.unpacking.results[0].status == "completed"
    assert result_analysis.photon_reconstruction.results[0].status == "completed"
    event_results = result_analysis.event_reconstruction.results
    assert len(event_results) == 1
    assert event_results[0].status == "completed"
    assert event_results[0].counts.event_count == 4


def test_run_hermes_analysis_marks_event_reconstruction_failed(
    tmp_path: Path,
) -> None:
    analysis = _analysis(tmp_path)
    _write_fake_unpacker(analysis.unpacking.program.executable_path)
    _write_fake_clusterer(analysis.photon_reconstruction.program.executable_path)
    _write_fake_reconstructor(
        analysis.event_reconstruction.program.executable_path,
        exit_code=1,
        write_summary=False,
    )
    manager = _manager(analysis, tmp_path)

    with pytest.raises(HermesEventReconstructionExecutionError):
        run_hermes_analysis(manager)

    result_analysis = manager.get_state().analysis
    assert result_analysis.photon_reconstruction.results[0].status == "completed"
    event_results = result_analysis.event_reconstruction.results
    assert event_results
    assert event_results[0].status == "failed"


def test_run_hermes_analysis_without_event_reconstruction_leaves_none(
    tmp_path: Path,
) -> None:
    analysis = _analysis(tmp_path, with_event_reconstruction=False)
    _write_fake_unpacker(analysis.unpacking.program.executable_path)
    _write_fake_clusterer(analysis.photon_reconstruction.program.executable_path)
    manager = _manager(analysis, tmp_path)

    run_hermes_analysis(manager)

    result_analysis = manager.get_state().analysis
    assert result_analysis.photon_reconstruction.results[0].status == "completed"
    assert result_analysis.event_reconstruction is None


def test_run_hermes_analysis_event_only_without_unpacking(
    tmp_path: Path,
) -> None:
    # Unpacking is already done: the photon file is on disk and no unpacking or
    # photon-reconstruction stage is configured, so only events are built.
    analysis_directory = tmp_path / "analysis"
    photon_path = (
        analysis_directory / "photons" / "run_000000-chip-0-part-00000.parquet"
    )
    photon_path.parent.mkdir(parents=True, exist_ok=True)
    photon_path.touch()

    event_exe = tmp_path / "bin/hermes-event-reconstructor"
    event_exe.parent.mkdir(parents=True, exist_ok=True)
    event_exe.touch()

    analysis = HermesTpx3AnalysisState(
        analysis_directory=analysis_directory,
        event_reconstruction=Tpx3EventReconstruction(
            program=BinaryProgram(
                name="event-reconstructor-cpp",
                executable_path=event_exe,
                version="0.1.0",
            ),
            settings=_settings(),
        ),
    )
    _write_fake_reconstructor(event_exe, event_count=4)
    manager = _manager(analysis, tmp_path)

    unpacked_files = run_hermes_analysis(manager)

    assert unpacked_files == []
    result_analysis = manager.get_state().analysis
    assert result_analysis.unpacking is None
    assert result_analysis.photon_reconstruction is None
    event_results = result_analysis.event_reconstruction.results
    assert len(event_results) == 1
    assert event_results[0].status == "completed"
    assert event_results[0].counts.event_count == 4
