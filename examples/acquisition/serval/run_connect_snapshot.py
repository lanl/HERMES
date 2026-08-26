from __future__ import annotations

import sys
from pathlib import Path

from hermes.state.models.acquisition.serval import ServalAcquisitionState
from hermes.state.models.detector import DetectorSnapshot
from hermes.state.state import HermesRecord
from hermes.state_service.state_io import load_hermes_record_from_yaml
from hermes.workflows.workflow import Workflow

DEFAULT_YAML_PATH = Path(__file__).with_name("connect_snapshot_config.yaml")


def print_snapshot(snapshot: DetectorSnapshot) -> None:
    info = snapshot.info
    health = snapshot.health
    layout = snapshot.layout

    print(f"\nDetector snapshot captured at {snapshot.captured_at.isoformat()}")

    if info is not None:
        print(f"  Interface: {info.iface_name}")
        print(f"  Chips: {info.number_of_chips}")
        for board in info.boards:
            print(f"  Board {board.chipboard_id} at {board.ip_address}")
            for chip in board.chips:
                print(f"    Chip {chip.index}: {chip.name} (id {chip.id})")

    if health is not None:
        print(f"  Local temperature: {health.local_temperature_c} C")
        print(f"  FPGA temperature: {health.fpga_temperature_c} C")
        print(f"  Chip temperatures: {health.chip_temperatures_c} C")
        print(f"  Bias voltage: {health.bias_voltage_v} V")
        print(f"  Humidity: {health.humidity_percent} %")

    if layout is not None and layout.original is not None:
        print(f"  Layout: {layout.original.width} x {layout.original.height} pixels")


def print_summary(record: HermesRecord) -> None:
    acquisition = record.acquisition
    if not isinstance(acquisition, ServalAcquisitionState):
        return

    dashboard = acquisition.dashboard
    if dashboard is not None:
        print(f"SERVAL software version: {dashboard.server.software_version}")

    snapshot = acquisition.initial_detector_snapshot
    if snapshot is not None:
        print_snapshot(snapshot)

    print(f"\nAcquisition status: {acquisition.status}")


def main(config_path: Path = DEFAULT_YAML_PATH) -> None:
    record = load_hermes_record_from_yaml(config_path)
    workflow = Workflow(record)
    updated_record = workflow.run()

    print_summary(updated_record)


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_YAML_PATH
    main(config_path)
