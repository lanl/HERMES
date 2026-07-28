from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from hermes.state.models.analysis.hermes_tpx3_spidr import HermesTpx3AnalysisState
from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)
from hermes.workflows.workflow import Workflow

DEFAULT_INPUT_YAML_PATH = Path(__file__).with_name("two_stage_config.yaml")


def main(input_yaml_path: Path = DEFAULT_INPUT_YAML_PATH) -> None:
    # Step 1: Load the initial HERMES record from the configuration YAML file
    initial_record = load_hermes_record_from_yaml(input_yaml_path)
    initial_analysis = initial_record.analysis
    if not isinstance(initial_analysis, HermesTpx3AnalysisState):
        raise ValueError("the two-stage example requires HERMES analysis")
    if initial_analysis.photon_reconstruction is None:
        raise ValueError(
            "the two-stage example requires photon reconstruction settings"
        )

    # Step 2: Choose a separate path for the completed HERMES record
    working_directory = cast(
        Path,
        initial_record.environment.working_dir.resolved_path,
    )
    final_record_path = working_directory / "hermes-record_final.yaml"

    # Step 3: Run unpacking followed by photon reconstruction
    workflow = Workflow(initial_record)
    unpacked_raw_files = workflow.run_analysis()

    # Step 4: Read and save the final HERMES record
    final_record = workflow.record
    final_analysis = cast(HermesTpx3AnalysisState, final_record.analysis)
    final_reconstruction = final_analysis.photon_reconstruction
    if final_reconstruction is None:
        raise RuntimeError("photon reconstruction configuration is missing")
    reconstruction = final_analysis.results.reconstruction
    if reconstruction is None:
        raise RuntimeError("photon reconstruction did not produce a result")
    save_hermes_record_to_yaml(final_record, final_record_path)

    # Step 5: Display the unpacking and photon reconstruction results
    print(f"Raw TPX3 files: {len(final_analysis.tpx3_files)}")
    for raw_tpx3_file in final_analysis.tpx3_files:
        print(f"  - {raw_tpx3_file.path}")
    print(f"Unpacked this run: {len(unpacked_raw_files)}")
    print(
        "Skipped existing valid unpacking output: "
        f"{len(final_analysis.tpx3_files) - len(unpacked_raw_files)}"
    )
    print(f"Photon reconstruction status: {reconstruction.status}")
    print(f"Photons: {reconstruction.photon_count}")
    print(f"Rejected clusters: {reconstruction.rejected_count}")
    print(f"Analysis directory: {final_analysis.analysis_directory}")
    print(
        "Photon output directory: "
        f"{final_reconstruction.photon_output_directory}"
    )
    print(f"HERMES state file: {final_record_path}")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} [YAML_PATH]")
    input_yaml_path = (
        Path(sys.argv[1]) if len(sys.argv) == 2 else DEFAULT_INPUT_YAML_PATH
    )
    main(input_yaml_path)
