from __future__ import annotations

import shutil
import sys
from pathlib import Path

from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)
from hermes.workflows.workflow import Workflow

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SOURCE_TPX3_FILE = REPOSITORY_ROOT / "tests/data/Example_1kHz_5frames.tpx3"
EXAMPLE_INPUT_DIRECTORY = REPOSITORY_ROOT / "data/multiFileExample"
NUMBER_OF_COPIES = 5

DEFAULT_INPUT_YAML_PATH = Path(__file__).with_name("unpacker_mf_config.yaml")


def prepare_example_input_files() -> None:
    # Create the input directory for the bundled multi-file example
    EXAMPLE_INPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    # Copy the checked-in TPX3 file with five unique filename stems
    for index in range(NUMBER_OF_COPIES):
        destination = (
            EXAMPLE_INPUT_DIRECTORY / f"Example_1kHz_5frames_{index:04d}.tpx3"
        )
        shutil.copyfile(SOURCE_TPX3_FILE, destination)


def main(input_yaml_path: Path = DEFAULT_INPUT_YAML_PATH) -> None:
    # Step 1: Prepare the bundled multi-file input when using the default YAML
    if input_yaml_path == DEFAULT_INPUT_YAML_PATH:
        prepare_example_input_files()

    # Step 2: Load the initial HERMES record from the configuration YAML file
    initial_record = load_hermes_record_from_yaml(input_yaml_path)

    # Step 3: Choose a separate path for the completed HERMES record
    working_directory = initial_record.environment.working_dir.resolved_path
    final_record_path = working_directory / "hermes-record_final.yaml"

    # Step 4: Create the workflow and run the configured analysis
    workflow = Workflow(initial_record)
    unpacked_raw_files = workflow.run_analysis()

    # Step 5: Read and save the final HERMES record
    final_record = workflow.record
    hermes_analysis = final_record.analysis
    save_hermes_record_to_yaml(final_record, final_record_path)

    # Step 6: Display the unpacking results
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
    input_yaml_path = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT_YAML_PATH
    )
    main(input_yaml_path)
