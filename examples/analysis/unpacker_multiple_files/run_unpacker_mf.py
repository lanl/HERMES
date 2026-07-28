from __future__ import annotations

import shutil
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

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_TPX3_FILE = REPOSITORY_ROOT / "tests/data/Example_1kHz_5frames.tpx3"
EXAMPLE_INPUT_DIRECTORY = REPOSITORY_ROOT / "data/multiFileExample"
NUMBER_OF_COPIES = 5

DEFAULT_INPUT_YAML_PATH = Path(__file__).with_name("unpacker_mf_config.yaml")


def prepare_example_input_files() -> None:
    if not SOURCE_TPX3_FILE.is_file():
        raise FileNotFoundError(f"Source TPX3 file not found: {SOURCE_TPX3_FILE}")

    EXAMPLE_INPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for index in range(NUMBER_OF_COPIES):
        destination = (
            EXAMPLE_INPUT_DIRECTORY / f"Example_1kHz_5frames_{index:04d}.tpx3"
        )
        shutil.copyfile(SOURCE_TPX3_FILE, destination)


def main(input_yaml_path: Path = DEFAULT_INPUT_YAML_PATH) -> None:
    prepare_example_input_files()

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

    print(f"Raw TPX3 files: {len(hermes_analysis.tpx3_files)}")
    for raw_tpx3_file in hermes_analysis.tpx3_files:
        print(f"  - {raw_tpx3_file.path}")
    print(f"Unpacked this run: {len(unpacked_raw_files)}")
    print(
        "Skipped existing valid outputs: "
        f"{len(hermes_analysis.tpx3_files) - len(unpacked_raw_files)}"
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
