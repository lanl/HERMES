from __future__ import annotations

from pathlib import Path

import pytest

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
        Path("first.tpx3"),
        Path("second.tpx3"),
    ]
    assert record.analysis.photon_reconstruction is None
    assert record.analysis.event_reconstruction is None


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
    # still keep the full record.
    assert record.environment.log_level == "ERROR"
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
