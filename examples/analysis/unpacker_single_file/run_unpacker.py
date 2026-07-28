from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from hermes.analysis.hermes.run import run_hermes_analysis
from hermes.state.models.analysis.hermes_tpx3_spidr import HermesTpx3AnalysisState
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)
from hermes.state_service.state_manager import StateManager

DEFAULT_INPUT_YAML_PATH = Path(__file__).with_name("unpacker_config.yaml")


def main(input_yaml_path: Path = DEFAULT_INPUT_YAML_PATH) -> None:
    initial_record = load_hermes_record_from_yaml(input_yaml_path)
    working_directory = cast(
        Path,
        initial_record.environment.working_dir.resolved_path,
    )
    final_record_path = working_directory / "hermes-record_final.yaml"

    state_manager = StateManager(
        initial_record,
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )

    unpacked_raw_files = run_hermes_analysis(state_manager)
    final_record = state_manager.get_state()
    hermes_analysis = cast(HermesTpx3AnalysisState, final_record.analysis)
    save_hermes_record_to_yaml(final_record, final_record_path)

    if unpacked_raw_files:
        print(f"Unpacked: {hermes_analysis.tpx3_files[0].path}")
    else:
        print(
            "Skipped existing valid output for: "
            f"{hermes_analysis.tpx3_files[0].path}"
        )
    print(f"Analysis directory: {hermes_analysis.analysis_directory}")
    print(f"HERMES state file: {final_record_path}")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} [YAML_PATH]")
    input_yaml_path = (
        Path(sys.argv[1]) if len(sys.argv) == 2 else DEFAULT_INPUT_YAML_PATH
    )
    main(input_yaml_path)
