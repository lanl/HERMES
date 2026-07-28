from __future__ import annotations

import argparse
import shutil
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
    """Prepare example input files by copying the source TPX3 file multiple times.
    
    Creates NUMBER_OF_COPIES copies of the source TPX3 file in the example
    input directory with sequential naming.
    
    Raises:
        FileNotFoundError: If the source TPX3 file does not exist.
    """
    # Verify that the source file exists before attempting to copy
    if not SOURCE_TPX3_FILE.is_file():
        raise FileNotFoundError(f"Source TPX3 file not found: {SOURCE_TPX3_FILE}")

    # Create the example input directory if it doesn't exist
    EXAMPLE_INPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    
    # Create multiple copies of the source file with sequential indices
    for index in range(NUMBER_OF_COPIES):
        destination = (
            EXAMPLE_INPUT_DIRECTORY / f"Example_1kHz_5frames_{index:04d}.tpx3"
        )
        shutil.copyfile(SOURCE_TPX3_FILE, destination)


def main(
    input_yaml_path: Path = DEFAULT_INPUT_YAML_PATH,
    *,
    overwrite: bool = False,
) -> None:
    
    # Step 1: Prepare example input files by copying the source TPX3 file multiple times
    prepare_example_input_files()

    # Step 2: Load the initial HERMES record from the configuration YAML file
    initial_record = load_hermes_record_from_yaml(input_yaml_path)
    
    # Step 3: Extract the working directory path where outputs will be stored
    working_directory = cast(
        Path,
        initial_record.environment.working_dir.resolved_path,
    )
    final_record_path = working_directory / "hermes-record_final.yaml"

    # Step 4: Initialize the state manager with the initial record
    # This manages the state throughout the analysis workflow
    state_manager = StateManager(
        initial_record,
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )

    # Step 5: Run the HERMES analysis on all TPX3 files
    # Returns a list of files that were actually unpacked (not skipped)
    unpacked_raw_files = run_hermes_analysis(state_manager, overwrite=overwrite)
    
    # Step 6: Get the final state after analysis completes
    final_record = state_manager.get_state()
    hermes_analysis = cast(HermesTpx3AnalysisState, final_record.analysis)
    
    # Step 7: Save the final HERMES record to a YAML file for future reference
    save_hermes_record_to_yaml(final_record, final_record_path)

    # Step 8: Display analysis summary and results
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "yaml_path",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT_YAML_PATH,
        help="HERMES record YAML config (defaults to unpacker_mf_config.yaml)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="re-unpack every file, overwriting previously unpacked outputs",
    )
    args = parser.parse_args()
    main(args.yaml_path, overwrite=args.overwrite)
