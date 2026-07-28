from __future__ import annotations

import sys
from pathlib import Path

from hermes.analysis.hermes.run import run_hermes_analysis
from hermes.state.models.analysis.hermes_tpx3_spidr import HermesTpx3AnalysisState
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)
from hermes.state_service.state_manager import StateManager

DEFAULT_CONFIG_PATH = Path(__file__).with_name("unpacker_config.yaml")


def main(config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    record = load_hermes_record_from_yaml(config_path)
    analysis = record.analysis
    if not isinstance(analysis, HermesTpx3AnalysisState):
        raise ValueError("the YAML file must contain a HERMES analysis section")

    for raw_file in analysis.tpx3_files:
        if not raw_file.path.is_file():
            raise FileNotFoundError(f"TPX3 input file not found: {raw_file.path}")

    executable_path = analysis.unpacker_program.executable_path
    if not executable_path.is_file():
        raise FileNotFoundError(
            "C++ unpacker not found. Run `pixi run build-cpp-unpacker` first: "
            f"{executable_path}"
        )

    working_dir = record.environment.working_dir.resolved_path
    if working_dir is None:
        raise ValueError("the HERMES working directory must be resolved")
    state_path = working_dir / "hermes-record.yaml"
    if config_path.resolve() == state_path.resolve():
        raise ValueError(
            "the input YAML and final HERMES record must be separate files"
        )

    state_manager = StateManager(
        record,
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )

    unpacked_files = run_hermes_analysis(state_manager)
    save_hermes_record_to_yaml(state_manager.get_state(), state_path)

    if unpacked_files:
        print(f"Unpacked: {analysis.tpx3_files[0].path}")
    else:
        print(f"Skipped existing valid output for: {analysis.tpx3_files[0].path}")
    print(f"Analysis directory: {analysis.analysis_directory}")
    print(f"HERMES state file: {state_path}")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} [YAML_PATH]")
    main(Path(sys.argv[1]) if len(sys.argv) == 2 else DEFAULT_CONFIG_PATH)
