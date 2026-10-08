from __future__ import annotations

from pathlib import Path

import pytest

from hermes.mcp.server import (
    AcquisitionConfigRequest,
    ConfigValidationRequest,
    create_acquisition_config,
    validate_config,
)
from hermes.state.models.acquisition.serval import ServalAcquisitionState
from hermes.state.models.analysis.hermes_tpx3_spidr import HermesTpx3AnalysisState
from hermes.state_service.state_io import load_hermes_record_from_yaml


def _request(directory: Path, **changes: object) -> AcquisitionConfigRequest:
    """A measurement request whose calibration files and SERVAL .jar exist."""
    for name in ("settings.bpc", "settings.bpc.dacs", "serval-3.3.0.jar"):
        (directory / name).write_bytes(b"")
    fields: dict = {
        "working_directory": directory,
        "measurement_id": "demo",
        "run": "run-1",
        "serval": {
            "url": "http://localhost:8080",
            "program_path": directory / "serval-3.3.0.jar",
            "version": "3.3.0",
            "tcp_ip": "192.168.100.10",
            "tcp_port": 50000,
        },
        "calibration_files": {
            "pixel_config_file": directory / "settings.bpc",
            "dacs_file": directory / "settings.bpc.dacs",
        },
        "run_timing": {
            "trigger_mode": "AUTOTRIGSTART_TIMERSTOP",
            "exposure_time_s": 0.1,
            "trigger_period_s": 0.2,
            "trigger_count": 5,
        },
        "furthest_stage": "acquisition",
    }
    fields.update(changes)
    return AcquisitionConfigRequest.model_validate(fields)


def test_acquisition_only_writes_a_loadable_measurement_config(
    tmp_path: Path,
) -> None:
    result = create_acquisition_config(_request(tmp_path))

    assert result.stages == ["acquisition"]
    assert result.warnings == []
    assert result.config_file == tmp_path / "hermes-config.yaml"
    assert result.run_script == tmp_path / "run_hermes.py"
    assert "Workflow(record).run()" in result.run_script.read_text()
    # The script is in the working folder, not the folder the user is in.
    assert f"pixi run python {result.run_script}" in result.message
    # Half the 0.2 s trigger period, which HERMES fills in when it is unset.
    assert "global timestamp every 0.1 s" in result.message

    record = load_hermes_record_from_yaml(result.config_file)
    assert record.analysis is None
    acquisition = record.acquisition
    assert isinstance(acquisition, ServalAcquisitionState)
    config = acquisition.config
    assert config.serval.program_path == tmp_path.resolve() / "serval-3.3.0.jar"
    assert config.serval.tcp_ip == "192.168.100.10"
    assert config.calibration_files is not None
    assert config.calibration_files.dacs_file == (
        tmp_path.resolve() / "settings.bpc.dacs"
    )
    assert config.run_timing is not None
    assert config.run_timing.trigger_count == 5
    assert config.detector_config is None
    # Each run writes into its own folder, named after the run.
    environment = record.environment
    run_directory = tmp_path.resolve() / "run-1"
    assert result.run_directory == run_directory
    assert environment.run_directory.resolved_path == run_directory
    assert environment.raw_data_directory.resolved_path == run_directory / "raw"
    assert environment.log_directory.resolved_path == run_directory / "logs"
    assert environment.analysis_directory.resolved_path is None
    # Writing the config makes no folders; the run makes them.
    assert not run_directory.exists()

    checked = validate_config(ConfigValidationRequest(config_file=result.config_file))
    assert checked.valid
    assert checked.warnings == []


def test_acquisition_with_unpacking_analyzes_the_raw_folder(tmp_path: Path) -> None:
    result = create_acquisition_config(
        _request(tmp_path, furthest_stage="unpacking")
    )

    assert result.stages == ["acquisition", "unpacking"]
    record = load_hermes_record_from_yaml(result.config_file)
    assert isinstance(record.analysis, HermesTpx3AnalysisState)
    unpacking = record.analysis.unpacking
    assert unpacking is not None
    assert unpacking.program.name == "tpx3-spidr-cpp"
    assert unpacking.tpx3_files == "auto"
    assert record.analysis.photon_reconstruction is None
    assert record.environment.analysis_directory.resolved_path == (
        tmp_path.resolve() / "run-1" / "analysis"
    )


def test_acquisition_through_event_reconstruction_writes_every_stage(
    tmp_path: Path,
) -> None:
    result = create_acquisition_config(
        _request(tmp_path, furthest_stage="event_reconstruction")
    )

    assert result.stages == [
        "acquisition",
        "unpacking",
        "photon_reconstruction",
        "event_reconstruction",
    ]


def test_missing_calibration_files_write_nothing(tmp_path: Path) -> None:
    request = _request(tmp_path)
    (tmp_path / "settings.bpc").unlink()
    (tmp_path / "settings.bpc.dacs").unlink()

    with pytest.raises(ValueError, match="calibration file not found") as error:
        create_acquisition_config(request)

    assert "settings.bpc.dacs" in str(error.value)
    assert not (tmp_path / "hermes-config.yaml").exists()
    assert not (tmp_path / "run_hermes.py").exists()


def test_timing_that_gives_wrong_times_writes_nothing(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        run_timing={
            "trigger_mode": "AUTOTRIGSTART_TIMERSTOP",
            "exposure_time_s": 0.01,
            "trigger_period_s": 0.05,
        },
    )

    with pytest.raises(ValueError, match="shortest frame HERMES accepts"):
        create_acquisition_config(request)

    assert not (tmp_path / "hermes-config.yaml").exists()


def test_a_used_run_folder_writes_nothing(tmp_path: Path) -> None:
    raw = tmp_path / "run-1" / "raw"
    raw.mkdir(parents=True)
    (raw / "old.tpx3").write_bytes(b"raw")

    with pytest.raises(ValueError, match="already holds 1 .tpx3 file"):
        create_acquisition_config(_request(tmp_path))

    assert not (tmp_path / "hermes-config.yaml").exists()


def test_a_missing_serval_jar_is_a_warning(tmp_path: Path) -> None:
    request = _request(tmp_path)
    (tmp_path / "serval-3.3.0.jar").unlink()

    result = create_acquisition_config(request)

    assert result.config_file.is_file()
    assert len(result.warnings) == 1
    assert "SERVAL program_path not found" in result.warnings[0]


@pytest.mark.parametrize("run", ["..", "../other", "/tmp/elsewhere", "a/b", "."])
def test_a_run_label_that_is_not_one_folder_name_is_refused(
    tmp_path: Path, run: str
) -> None:
    with pytest.raises(ValueError, match="must be a single folder name"):
        create_acquisition_config(_request(tmp_path, run=run))

    assert not (tmp_path / "hermes-config.yaml").exists()


def test_a_trigger_mode_is_required(tmp_path: Path) -> None:
    request = _request(tmp_path, run_timing={"exposure_time_s": 0.1})

    with pytest.raises(ValueError, match="trigger_mode is required"):
        create_acquisition_config(request)


def test_a_missing_working_directory_is_refused(tmp_path: Path) -> None:
    request = _request(tmp_path, working_directory=tmp_path / "nope")

    with pytest.raises(ValueError, match="working directory does not exist"):
        create_acquisition_config(request)
