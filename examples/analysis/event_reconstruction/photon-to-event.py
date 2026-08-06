from __future__ import annotations

import shutil
import sys
from pathlib import Path

from hermes.runner.analysis.hermes.event_reconstruction import (
    derive_output_path,
    derive_summary_path,
    execute_event_reconstruction,
    log_skipped_input,
    plan_event_reconstruction,
)
from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)

DEFAULT_INPUT_YAML_PATH = Path(__file__).with_name("photon-to-event.yaml")
SOURCE_PHOTON_FILE = Path("tests/data/photons/Tantalum_IronPowder.parquet")


def main(input_yaml_path: Path = DEFAULT_INPUT_YAML_PATH) -> None:
    # Step 1: Load the initial HERMES record from the configuration YAML file
    initial_record = load_hermes_record_from_yaml(input_yaml_path)
    analysis = initial_record.analysis

    # Step 2: Choose a separate path for the completed HERMES record
    working_directory = initial_record.environment.working_dir.resolved_path
    final_record_path = working_directory / "hermes-record_final.yaml"

    # Step 3: Copy the starting photon file into the photons sub-directory so the
    # "auto" input selection finds it (unpacking is already done for this dataset)
    photon_directory = analysis.analysis_directory / "photons"
    photon_directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_PHOTON_FILE, photon_directory / SOURCE_PHOTON_FILE.name)

    # Step 4: Run only the event stage, one file at a time, skipping finished work
    event_reconstruction = analysis.event_reconstruction
    plan = plan_event_reconstruction(analysis)
    results = []
    for input_file, action in plan:
        if action == "skip":
            log_skipped_input(
                input_file,
                derive_output_path(event_reconstruction, input_file),
            )
            continue
        results.append(execute_event_reconstruction(analysis, input_file))

    # Step 5: Record the per-file results on the state and save the final record
    event_reconstruction.results = results
    save_hermes_record_to_yaml(initial_record, final_record_path)

    # Step 6: Display the event reconstruction results
    photons_read = sum(
        result.counts.photons_read
        for result in results
        if result.counts is not None
    )
    event_count = sum(
        result.counts.event_count
        for result in results
        if result.counts is not None
    )
    single_photon = sum(
        result.counts.quality_flag_counts.single_photon
        for result in results
        if result.counts is not None
    )
    duration_exceeded = sum(
        result.counts.quality_flag_counts.duration_exceeded
        for result in results
        if result.counts is not None
    )
    print(f"Reconstructed photon files this run: {len(results)}")
    print(f"Photons read: {photons_read}")
    print(f"Events: {event_count}")
    print(f"Single-photon events: {single_photon}")
    print(f"Duration-exceeded events: {duration_exceeded}")
    print(f"Event output directory: {event_reconstruction.output_directory}")
    for result in results:
        summary_path = derive_summary_path(result.output_file)
        print(f"Summary: {summary_path}")
    print(f"HERMES state file: {final_record_path}")


if __name__ == "__main__":
    input_yaml_path = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT_YAML_PATH
    )
    main(input_yaml_path)
