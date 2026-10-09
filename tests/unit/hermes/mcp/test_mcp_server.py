from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from hermes.mcp import server
from hermes.mcp.server import (
    AnalysisConfigRequest,
    ConfigValidationRequest,
    create_analysis_config,
    validate_config,
)
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
)
from hermes.state_service.state_io import load_hermes_record_from_yaml


def _write_raw_files(directory: Path, names: list[str]) -> None:
    for name in names:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"raw")


def test_unpacking_writes_a_loadable_unpack_only_config(tmp_path: Path) -> None:
    _write_raw_files(tmp_path, ["first.tpx3", "second.tpx3"])

    result = create_analysis_config(
        AnalysisConfigRequest(
            working_directory=tmp_path,
            measurement_id="demo",
            run="run-1",
            furthest_stage="unpacking",
        )
    )

    assert result.stages == ["unpacking"]
    assert result.tpx3_files == ["first.tpx3", "second.tpx3"]
    assert result.config_file == tmp_path / "hermes-config.yaml"
    assert result.run_script == tmp_path / "run_hermes.py"
    assert result.config_file.is_file()
    assert result.run_script.is_file()

    record = load_hermes_record_from_yaml(result.config_file)
    assert record.measurement_info.measurement_id == "demo"
    assert record.measurement_info.run == "run-1"
    assert isinstance(record.analysis, HermesTpx3AnalysisState)
    unpacking = record.analysis.unpacking
    assert unpacking is not None
    assert unpacking.program.name == "tpx3-spidr-cpp"
    assert unpacking.program.executable_path == Path("hermes-tpx3-spidr")
    assert [entry.path for entry in unpacking.tpx3_files] == [
        tmp_path.resolve() / "first.tpx3",
        tmp_path.resolve() / "second.tpx3",
    ]
    assert record.analysis.photon_reconstruction is None
    assert record.analysis.event_reconstruction is None


def test_generated_config_finds_the_tpx3_files_from_any_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    _write_raw_files(data, ["only.tpx3", "raw/nested.tpx3"])

    result = create_analysis_config(
        AnalysisConfigRequest(
            working_directory=data,
            measurement_id="demo",
            run="run-1",
            furthest_stage="unpacking",
        )
    )

    # HERMES opens each listed .tpx3 path from the folder the run script is
    # launched in, which need not be the data folder.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    record = load_hermes_record_from_yaml(result.config_file)
    assert record.environment.working_directory.path == data.resolve()
    assert isinstance(record.analysis, HermesTpx3AnalysisState)
    unpacking = record.analysis.unpacking
    assert unpacking is not None
    assert all(entry.path.is_file() for entry in unpacking.tpx3_files)


def test_generated_config_is_quiet_and_uses_the_default_timewalk(
    tmp_path: Path,
) -> None:
    _write_raw_files(tmp_path, ["only.tpx3"])

    result = create_analysis_config(
        AnalysisConfigRequest(
            working_directory=tmp_path,
            measurement_id="demo",
            run="run-1",
            furthest_stage="photon_reconstruction",
        )
    )

    record = load_hermes_record_from_yaml(result.config_file)
    # Runs print only errors and worse to the terminal; the JSON-lines log files
    # in the run's logs/ folder still keep everything.
    assert record.environment.log_level == "ERROR"
    assert record.environment.log_directory.resolved_path == tmp_path / "run-1" / "logs"
    assert isinstance(record.analysis, HermesTpx3AnalysisState)
    reconstruction = record.analysis.photon_reconstruction
    assert reconstruction is not None
    assert (
        reconstruction.clustering_algorithm.settings.timewalk_calibration_file
        == "default"
    )


def test_photon_stage_adds_default_clustering_settings(tmp_path: Path) -> None:
    _write_raw_files(tmp_path, ["only.tpx3"])

    result = create_analysis_config(
        AnalysisConfigRequest(
            working_directory=tmp_path,
            measurement_id="demo",
            run="run-1",
            furthest_stage="photon_reconstruction",
        )
    )

    assert result.stages == ["unpacking", "photon_reconstruction"]
    record = load_hermes_record_from_yaml(result.config_file)
    assert isinstance(record.analysis, HermesTpx3AnalysisState)
    reconstruction = record.analysis.photon_reconstruction
    assert reconstruction is not None
    assert reconstruction.program.executable_path == Path("hermes-photon-clusterer")
    assert reconstruction.pixel_files == "auto"
    assert reconstruction.clustering_algorithm.save_photon_pixels is True
    settings = reconstruction.clustering_algorithm.settings
    assert settings.max_time_spread_ticks == 491520
    assert settings.max_cluster_size == 64
    assert settings.timewalk_calibration_file == "default"
    assert record.analysis.event_reconstruction is None


def test_event_stage_adds_all_three_stages(tmp_path: Path) -> None:
    _write_raw_files(tmp_path, ["only.tpx3"])

    result = create_analysis_config(
        AnalysisConfigRequest(
            working_directory=tmp_path,
            measurement_id="demo",
            run="run-1",
            furthest_stage="event_reconstruction",
        )
    )

    assert result.stages == [
        "unpacking",
        "photon_reconstruction",
        "event_reconstruction",
    ]
    record = load_hermes_record_from_yaml(result.config_file)
    assert isinstance(record.analysis, HermesTpx3AnalysisState)
    assert record.analysis.unpacking is not None
    assert record.analysis.photon_reconstruction is not None
    event = record.analysis.event_reconstruction
    assert event is not None
    assert event.program.executable_path == Path("hermes-event-reconstructor")
    assert event.photon_parquet_files == "auto"
    assert event.settings.spatial_cells_per_axis == 5


def test_nested_tpx3_files_are_found_with_relative_paths(tmp_path: Path) -> None:
    _write_raw_files(tmp_path, ["top.tpx3", "raw/nested.tpx3"])

    result = create_analysis_config(
        AnalysisConfigRequest(
            working_directory=tmp_path,
            measurement_id="demo",
            run="run-1",
            furthest_stage="unpacking",
        )
    )

    assert result.tpx3_files == ["raw/nested.tpx3", "top.tpx3"]


def test_empty_directory_reports_no_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no .tpx3 files found"):
        create_analysis_config(
            AnalysisConfigRequest(
                working_directory=tmp_path,
                measurement_id="demo",
                run="run-1",
                furthest_stage="unpacking",
            )
        )


def test_missing_directory_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="working directory does not exist"):
        create_analysis_config(
            AnalysisConfigRequest(
                working_directory=tmp_path / "missing",
                measurement_id="demo",
                run="run-1",
                furthest_stage="unpacking",
            )
        )


def test_run_script_loads_the_config_and_runs_the_workflow(tmp_path: Path) -> None:
    _write_raw_files(tmp_path, ["only.tpx3"])

    result = create_analysis_config(
        AnalysisConfigRequest(
            working_directory=tmp_path,
            measurement_id="demo",
            run="run-1",
            furthest_stage="unpacking",
        )
    )

    script = result.run_script.read_text(encoding="utf-8")
    assert "load_hermes_record_from_yaml" in script
    assert "Workflow(record).run()" in script
    assert "hermes-config.yaml" in script


_VALID_MINIMAL_CONFIG = """\
measurement_info:
  measurement_id: demo
  run: run-1
environment:
  analysis_directory: analysis
"""


def test_validate_config_accepts_a_generated_config(tmp_path: Path) -> None:
    _write_raw_files(tmp_path, ["only.tpx3"])
    created = create_analysis_config(
        AnalysisConfigRequest(
            working_directory=tmp_path,
            measurement_id="demo",
            run="run-1",
            furthest_stage="photon_reconstruction",
        )
    )

    result = validate_config(ConfigValidationRequest(config_file=created.config_file))

    assert result.valid
    assert result.problems == []
    assert result.stages == ["unpacking", "photon_reconstruction"]


def test_validate_config_reports_a_schema_problem(tmp_path: Path) -> None:
    config = tmp_path / "hermes-config.yaml"
    config.write_text(
        "measurement_info:\n"
        "  measurement_id: demo\n"
        "  run: ''\n"
        "environment:\n"
        "  analysis_directory: analysis\n",
        encoding="utf-8",
    )

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert not result.valid
    assert result.stages == []
    assert any("run" in problem for problem in result.problems)


def test_validate_config_reports_an_unknown_field(tmp_path: Path) -> None:
    config = tmp_path / "hermes-config.yaml"
    config.write_text(_VALID_MINIMAL_CONFIG + "bogus_field: 1\n", encoding="utf-8")

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert not result.valid
    assert any("bogus_field" in problem for problem in result.problems)


def test_validate_config_reports_unparseable_yaml(tmp_path: Path) -> None:
    config = tmp_path / "hermes-config.yaml"
    config.write_text("foo: [1, 2", encoding="utf-8")

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert not result.valid
    assert any("parse" in problem.lower() for problem in result.problems)


def test_validate_config_reports_a_non_mapping_top_level(tmp_path: Path) -> None:
    config = tmp_path / "hermes-config.yaml"
    config.write_text("- one\n- two\n", encoding="utf-8")

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert not result.valid
    assert any("top-level mapping" in problem for problem in result.problems)


def test_validate_config_reports_a_missing_file(tmp_path: Path) -> None:
    result = validate_config(
        ConfigValidationRequest(config_file=tmp_path / "nope.yaml")
    )

    assert not result.valid
    assert "config file not found" in result.problems[0]


def _write_acquisition_config(
    directory: Path,
    *,
    detector_config: dict | None = None,
    run_timing: dict | None = None,
) -> Path:
    """Write a measurement config whose calibration files and SERVAL .jar
    exist, so each test breaks only the one thing it checks."""
    for name in ("settings.bpc", "settings.bpc.dacs", "serval-3.3.0.jar"):
        (directory / name).write_bytes(b"")
    config: dict = {
        "measurement_info": {"measurement_id": "demo", "run": "run-1"},
        "environment": {
            "working_directory": str(directory),
            "raw_data_directory": "raw",
        },
        "acquisition": {
            "mode": "serval",
            "config": {
                "serval": {
                    "url": "http://localhost:8080",
                    "program_path": str(directory / "serval-3.3.0.jar"),
                },
                "calibration_files": {
                    "pixel_config_file": str(directory / "settings.bpc"),
                    "dacs_file": str(directory / "settings.bpc.dacs"),
                },
                "run_timing": run_timing
                or {
                    "trigger_mode": "AUTOTRIGSTART_TIMERSTOP",
                    "exposure_time_s": 0.1,
                    "trigger_period_s": 0.2,
                    "trigger_count": 5,
                },
            },
        },
    }
    if detector_config is not None:
        config["acquisition"]["config"]["detector_config"] = detector_config
    path = directory / "hermes-config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_validate_config_accepts_an_acquisition_config(tmp_path: Path) -> None:
    config = _write_acquisition_config(tmp_path)

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert result.valid
    assert result.problems == []
    assert result.warnings == []
    assert result.stages == ["acquisition"]
    # Half the 0.2 s trigger period, which HERMES fills in when it is unset.
    assert "global timestamp every 0.1 s" in result.message


def test_validate_config_lists_acquisition_before_analysis(tmp_path: Path) -> None:
    config = _write_acquisition_config(tmp_path)
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    data["analysis"] = {
        "mode": "hermes",
        "unpacking": {**server._UNPACKING, "tpx3_files": "auto"},
    }
    config.write_text(yaml.safe_dump(data), encoding="utf-8")

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert result.valid
    assert result.stages == ["acquisition", "unpacking"]


def test_validate_config_reports_a_missing_calibration_file(tmp_path: Path) -> None:
    config = _write_acquisition_config(tmp_path)
    (tmp_path / "settings.bpc.dacs").unlink()

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert not result.valid
    assert result.problems == [
        f"calibration file not found: {tmp_path.resolve() / 'settings.bpc.dacs'}"
    ]


def test_validate_config_reports_global_timestamps_turned_off(
    tmp_path: Path,
) -> None:
    config = _write_acquisition_config(
        tmp_path, detector_config={"GlobalTimestampInterval": 0}
    )

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert not result.valid
    assert len(result.problems) == 1
    assert "turns global timestamps off" in result.problems[0]


def test_validate_config_reports_an_interval_over_half_the_trigger_period(
    tmp_path: Path,
) -> None:
    config = _write_acquisition_config(
        tmp_path, detector_config={"GlobalTimestampInterval": 0.15}
    )

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert not result.valid
    assert len(result.problems) == 1
    assert "longer than half the 0.2 s trigger period" in result.problems[0]


def test_validate_config_reports_a_trigger_period_under_100_ms(
    tmp_path: Path,
) -> None:
    config = _write_acquisition_config(
        tmp_path,
        run_timing={
            "trigger_mode": "AUTOTRIGSTART_TIMERSTOP",
            "exposure_time_s": 0.01,
            "trigger_period_s": 0.05,
        },
    )

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert not result.valid
    assert len(result.problems) == 1
    assert "shortest frame HERMES accepts" in result.problems[0]


def test_validate_config_reports_a_missing_detector_config_file(
    tmp_path: Path,
) -> None:
    config = _write_acquisition_config(tmp_path)
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    data["acquisition"]["config"]["detector_config_file"] = str(
        tmp_path / "missing.json"
    )
    config.write_text(yaml.safe_dump(data), encoding="utf-8")

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert not result.valid
    assert len(result.problems) == 1
    assert "cannot read detector_config_file" in result.problems[0]


def test_validate_config_reports_a_measurement_with_no_raw_folder(
    tmp_path: Path,
) -> None:
    config = _write_acquisition_config(tmp_path)
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    del data["environment"]["raw_data_directory"]
    config.write_text(yaml.safe_dump(data), encoding="utf-8")

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert not result.valid
    assert len(result.problems) == 1
    assert "nowhere to write the measurement" in result.problems[0]


def test_validate_config_reports_a_raw_folder_with_old_files(
    tmp_path: Path,
) -> None:
    config = _write_acquisition_config(tmp_path)
    raw = tmp_path / "run-1" / "raw"
    raw.mkdir(parents=True)
    (raw / "old.tpx3").write_bytes(b"raw")

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert not result.valid
    assert len(result.problems) == 1
    assert "already holds 1 .tpx3 file(s)" in result.problems[0]


def test_validate_config_warns_about_a_missing_serval_jar(tmp_path: Path) -> None:
    config = _write_acquisition_config(tmp_path)
    (tmp_path / "serval-3.3.0.jar").unlink()

    result = validate_config(ConfigValidationRequest(config_file=config))

    # SERVAL may already be running, so the run may not need the .jar.
    assert result.valid
    assert result.problems == []
    assert len(result.warnings) == 1
    assert "SERVAL program_path not found" in result.warnings[0]


def test_validate_config_warns_about_low_disk_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_acquisition_config(tmp_path)
    monkeypatch.setattr(
        server.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=0),
    )

    result = validate_config(ConfigValidationRequest(config_file=config))

    assert result.valid
    assert len(result.warnings) == 1
    # The raw folder does not exist yet, so the check looks at the folder
    # it will be made in, and does not make it.
    assert f"free at {tmp_path.resolve()}," in result.warnings[0]
    assert not (tmp_path / "run-1" / "raw").exists()


def test_validate_config_counts_gigabytes_as_serval_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_acquisition_config(tmp_path)
    # SERVAL calls 670758268928 bytes "670.8 GB", so 1 GB is 10^9 bytes.
    free = {"bytes": 1_000_000_000}
    monkeypatch.setattr(
        server.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=free["bytes"]),
    )

    assert validate_config(ConfigValidationRequest(config_file=config)).warnings == []

    free["bytes"] = 500_000_000
    warnings = validate_config(ConfigValidationRequest(config_file=config)).warnings
    assert len(warnings) == 1
    assert warnings[0].startswith("only 0.50 GB free at")
