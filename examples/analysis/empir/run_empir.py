from __future__ import annotations

import shutil
import sys
from pathlib import Path

from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)
from hermes.workflows.workflow import Workflow

DEFAULT_INPUT_YAML_PATH = Path(__file__).with_name("empir.yaml")
SOURCE_TPX3_FILE = Path("tests/data/tpx3/Tantalum_IronPowder.tpx3")


def _describe(result: object) -> str:
    """Return the step duration, or its status when nothing timed the step."""
    if result.elapsed_seconds is None:
        return result.status
    return f"{result.elapsed_seconds:.3f} s"


def main(input_yaml_path: Path = DEFAULT_INPUT_YAML_PATH) -> None:
    # Step 1: Load the initial HERMES record from the configuration YAML file
    initial_record = load_hermes_record_from_yaml(input_yaml_path)

    # Step 2: Choose a separate path for the completed HERMES record
    working_directory = initial_record.environment.working_dir.resolved_path
    final_record_path = working_directory / "hermes-record_final.yaml"

    # Step 3: Copy the starting raw TPX3 file into the rawTpx3 sub-directory the
    # pixel-to-photon stage reads from
    raw_directory = working_directory / "rawTpx3"
    raw_directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_TPX3_FILE, raw_directory / SOURCE_TPX3_FILE.name)

    # Step 4: Run the three EMPIR programs in order:
    # pixel-to-photon -> photon-to-event -> event-to-image
    workflow = Workflow(initial_record)
    image_files = workflow.run_analysis()

    # Step 5: Read and save the final HERMES record
    final_record = workflow.record
    final_analysis = final_record.analysis
    save_hermes_record_to_yaml(final_record, final_record_path)

    # Step 6: Display the measured duration for each stage
    pixel_run = final_analysis.pixel_to_photon.runs[0]
    photon_run = final_analysis.photon_to_event.runs[0]
    image_result = final_analysis.event_to_image.result

    print(f"Pixel-to-photon: {_describe(pixel_run.result)}")
    print(f"Photon-to-event: {_describe(photon_run.result)}")
    print(f"Event-to-image:  {_describe(image_result)}")
    print(f"TIFF images written: {len(image_files)}")
    for image_file in image_files:
        print(f"  - {image_file.path}")
    log_directory = initial_record.environment.log_dir.resolved_path
    if log_directory is not None:
        print(f"Timing log: {log_directory / 'analysis.jsonl'}")
    print(f"HERMES state file: {final_record_path}")


if __name__ == "__main__":
    input_yaml_path = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT_YAML_PATH
    )
    main(input_yaml_path)
