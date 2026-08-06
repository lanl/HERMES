from __future__ import annotations

import shutil
import sys
from pathlib import Path

from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)
from hermes.workflows.workflow import Workflow

DEFAULT_INPUT_YAML_PATH = Path(__file__).with_name("raw-to-events.yaml")
SOURCE_TPX3_FILE = Path("tests/data/tpx3/Tantalum_IronPowder.tpx3")


def main(input_yaml_path: Path = DEFAULT_INPUT_YAML_PATH) -> None:
    # Step 1: Load the initial HERMES record from the configuration YAML file
    initial_record = load_hermes_record_from_yaml(input_yaml_path)

    # Step 2: Choose a separate path for the completed HERMES record
    working_directory = initial_record.environment.working_dir.resolved_path
    final_record_path = working_directory / "hermes-record_final.yaml"

    # Step 3: Copy the starting raw TPX3 file into the rawTpx3 sub-directory the
    # unpacking stage reads from
    raw_directory = working_directory / "rawTpx3"
    raw_directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_TPX3_FILE, raw_directory / SOURCE_TPX3_FILE.name)

    # Step 4: Run the full chain: unpacking -> photon -> event reconstruction
    workflow = Workflow(initial_record)
    unpacked_raw_files = workflow.run_analysis()

    # Step 5: Read and save the final HERMES record
    final_record = workflow.record
    final_analysis = final_record.analysis
    save_hermes_record_to_yaml(final_record, final_record_path)

    # Step 6: Display the tallies for each stage of the chain
    pixel_hit_directory = final_analysis.analysis_directory / "pixelHits"
    pixel_hit_files = sorted(pixel_hit_directory.glob("*.parquet"))
    photon_results = final_analysis.photon_reconstruction.results
    event_results = final_analysis.event_reconstruction.results
    photon_count = sum(
        result.counts.photon_count
        for result in photon_results
        if result.counts is not None
    )
    event_count = sum(
        result.counts.event_count
        for result in event_results
        if result.counts is not None
    )

    raw_tpx3_files = final_analysis.unpacking.tpx3_files
    print(f"Raw TPX3 files: {len(raw_tpx3_files)}")
    for raw_tpx3_file in raw_tpx3_files:
        print(f"  - {raw_tpx3_file.path}")
    print(f"Unpacked this run: {len(unpacked_raw_files)}")
    print(f"Pixel-hit files: {len(pixel_hit_files)}")
    print(f"Photons: {photon_count}")
    print(f"Events: {event_count}")
    print(f"Pixel-hit output directory: {pixel_hit_directory}")
    print(
        "Photon output directory: "
        f"{final_analysis.photon_reconstruction.output_directory}"
    )
    print(
        "Event output directory: "
        f"{final_analysis.event_reconstruction.output_directory}"
    )
    print(f"HERMES state file: {final_record_path}")


if __name__ == "__main__":
    input_yaml_path = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT_YAML_PATH
    )
    main(input_yaml_path)
