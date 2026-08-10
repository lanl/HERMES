from __future__ import annotations

import shutil
import sys
from pathlib import Path

from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)
from hermes.workflows.workflow import Workflow

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_TPX3_FILE = REPOSITORY_ROOT / "tests/data/Example_1kHz_5frames.tpx3"
MULTIPLE_FILES_INPUT_DIRECTORY = (
    REPOSITORY_ROOT / "data/examples/analysis/unpacking/multiple_files/input"
)
NUMBER_OF_COPIES = 5

SINGLE_FILE_YAML_PATH = Path(__file__).with_name("single_file.yaml")
MULTIPLE_FILES_YAML_PATH = Path(__file__).with_name("multiple_files.yaml")
DEFAULT_INPUT_YAML_PATH = SINGLE_FILE_YAML_PATH


def prepare_multiple_file_input() -> None:
    # Create the input directory for the bundled multiple-file example
    MULTIPLE_FILES_INPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    # Copy the checked-in TPX3 file with five unique filename stems
    for index in range(NUMBER_OF_COPIES):
        destination = (
            MULTIPLE_FILES_INPUT_DIRECTORY
            / f"Example_1kHz_5frames_{index:04d}.tpx3"
        )
        shutil.copyfile(SOURCE_TPX3_FILE, destination)


def main(input_yaml_path: Path = DEFAULT_INPUT_YAML_PATH) -> None:
    # Step 1: Prepare the bundled inputs for the multiple-file configuration
    if input_yaml_path.resolve() == MULTIPLE_FILES_YAML_PATH.resolve():
        prepare_multiple_file_input()

    # Step 2: Load the initial HERMES record from the configuration YAML file
    initial_record = load_hermes_record_from_yaml(input_yaml_path)

    # Step 3: Choose a separate path for the completed HERMES record
    working_directory = initial_record.environment.working_directory.resolved_path
    final_record_path = working_directory / "hermes-record_final.yaml"

    # Step 4: Create the workflow and run the configured analysis
    workflow = Workflow(initial_record)
    unpacked_raw_files = workflow.run_analysis()

    # Step 5: Read and save the final HERMES record
    final_record = workflow.record
    save_hermes_record_to_yaml(final_record, final_record_path)

    # Step 6: Display the unpacking results
    raw_tpx3_files = final_record.analysis.unpacking.tpx3_files
    print(f"Raw TPX3 files: {len(raw_tpx3_files)}")
    for raw_tpx3_file in raw_tpx3_files:
        print(f"  - {raw_tpx3_file.path}")
    print(f"Unpacked this run: {len(unpacked_raw_files)}")
    print(
        "Skipped existing valid outputs: "
        f"{len(raw_tpx3_files) - len(unpacked_raw_files)}"
    )
    analysis_directory = final_record.environment.analysis_directory.resolved_path
    print(f"Analysis directory: {analysis_directory}")
    print(f"HERMES state file: {final_record_path}")



if __name__ == "__main__":
    input_yaml_path = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT_YAML_PATH
    )
    main(input_yaml_path)
