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


    # NEED TO BUILD OUT EVENT RECONSTRUCTION. ONCE BUILT, THEN EXAMPLE WILL BE MODIFIED

if __name__ == "__main__":
    input_yaml_path = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT_YAML_PATH
    )
    main(input_yaml_path)
