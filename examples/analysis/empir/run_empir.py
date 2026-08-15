from __future__ import annotations

import shutil
import sys
from pathlib import Path

from hermes.runner.analysis.empir._errors import EmpirNotInstalledError
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

    # Step 2: Create the workflow object with the initial HERMES record
    workflow = Workflow(initial_record)

    # Step 3: Run the workflow, which executes the EMPIR stages in order
    try:
        workflow.run_analysis()
    except EmpirNotInstalledError as error:
        print(f"EMPIR is not installed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    input_yaml_path = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT_YAML_PATH
    )
    main(input_yaml_path)
