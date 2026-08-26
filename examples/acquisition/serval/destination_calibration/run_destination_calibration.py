from __future__ import annotations

import sys
from pathlib import Path

from hermes.state.models.acquisition.serval import ServalAcquisitionState
from hermes.state.state import HermesRecord
from hermes.state_service.state_io import load_hermes_record_from_yaml
from hermes.workflows.workflow import Workflow

DEFAULT_YAML_PATH = Path(__file__).with_name("destination_calibration_config.yaml")


def print_summary(record: HermesRecord) -> None:
    acquisition = record.acquisition
    if not isinstance(acquisition, ServalAcquisitionState):
        return

    destination = acquisition.destination
    if destination is not None and destination.raw:
        print("Raw destination:")
        for entry in destination.raw:
            print(f"  {entry.base} (split {entry.split_strategy})")

    calibration = acquisition.calibration
    if calibration is not None:
        pixel = calibration.pixel_config_file
        dacs = calibration.dacs_file
        if pixel is not None:
            print(f"Pixel config: {pixel.path} (sha256 {pixel.file_hash[:12]}...)")
        if dacs is not None:
            print(f"DACs file:    {dacs.path} (sha256 {dacs.file_hash[:12]}...)")
        if calibration.pixel_config_load is not None:
            print(
                "Pixel config load: HTTP "
                f"{calibration.pixel_config_load.http_status_code} "
                f"({calibration.pixel_config_load.status})"
            )
        if calibration.dacs_load is not None:
            print(
                "DACs load:         HTTP "
                f"{calibration.dacs_load.http_status_code} "
                f"({calibration.dacs_load.status})"
            )

    print(f"\nAcquisition status: {acquisition.status}")


def main(config_path: Path = DEFAULT_YAML_PATH) -> None:
    record = load_hermes_record_from_yaml(config_path)
    workflow = Workflow(record)
    updated_record = workflow.run()

    print_summary(updated_record)


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_YAML_PATH
    main(config_path)
