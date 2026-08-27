from __future__ import annotations

import sys
from pathlib import Path

from hermes.state.models.acquisition.serval import ServalAcquisitionState
from hermes.state.state import HermesRecord
from hermes.state_service.state_io import load_hermes_record_from_yaml
from hermes.workflows.workflow import Workflow

DEFAULT_YAML_PATH = Path(__file__).with_name("measurement_config.yaml")


def print_summary(record: HermesRecord) -> None:
    acquisition = record.acquisition
    if not isinstance(acquisition, ServalAcquisitionState):
        return

    result = acquisition.result
    if result is not None:
        print("Measurement:")
        print(f"  started:  {result.started_at}")
        print(f"  finished: {result.completed_at}")
        print(f"  reason:   {result.stop_reason}")
        print(f"  frames:   {result.frames} ({result.dropped_frames} dropped)")
        print(f"  raw files: {len(result.output_files)}")
        for file in result.output_files:
            print(f"    {file.path}")
        for warning in result.warnings:
            print(f"  warning: {warning}")
        for error in result.errors:
            print(f"  error:   {error}")

    print(f"\nAcquisition status: {acquisition.status}")


def main(config_path: Path = DEFAULT_YAML_PATH) -> None:
    record = load_hermes_record_from_yaml(config_path)
    workflow = Workflow(record)
    updated_record = workflow.run()

    print_summary(updated_record)


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_YAML_PATH
    main(config_path)
