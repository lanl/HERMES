from __future__ import annotations

import shutil
import sys
from pathlib import Path

from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)
from hermes.workflows.workflow import Workflow

DEFAULT_INPUT_YAML_PATH = Path(__file__).with_name("photon-to-event.yaml")
SOURCE_PHOTON_FILE = Path("tests/data/photons/Tantalum_IronPowder.parquet")


def main(input_yaml_path: Path = DEFAULT_INPUT_YAML_PATH) -> None:
    # Step 1: Load the initial HERMES record from the configuration YAML file
    initial_record = load_hermes_record_from_yaml(input_yaml_path)

    # Step 2: Choose a separate path for the completed HERMES record
    working_directory = initial_record.environment.working_directory.resolved_path
    final_record_path = working_directory / "hermes-record_final.yaml"

    # Step 3: Copy the sample photon file into the photons/ folder, named the way
    # the photon stage names its files
    analysis_directory = initial_record.environment.analysis_directory.resolved_path
    photon_directory = analysis_directory / "photons"
    photon_directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        SOURCE_PHOTON_FILE,
        photon_directory / "Tantalum_IronPowder_chip_0_photon_00000.parquet",
    )

    # Step 4: Run event reconstruction only
    workflow = Workflow(initial_record)
    workflow.run_analysis()

    # Step 5: Read and save the final HERMES record
    final_record = workflow.record
    save_hermes_record_to_yaml(final_record, final_record_path)

    # Step 6: Display the event reconstruction results
    event_results = final_record.analysis.event_reconstruction.results
    for result in event_results:
        event_count = result.counts.event_count if result.counts else 0
        print(f"{result.raw_file_stem}: {result.status}, {event_count} events")
    print(f"Event output directory: {analysis_directory / 'events'}")
    print(f"HERMES state file: {final_record_path}")


if __name__ == "__main__":
    input_yaml_path = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT_YAML_PATH
    )
    main(input_yaml_path)
