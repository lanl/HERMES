from __future__ import annotations

import sys
from pathlib import Path

from hermes.logging import configure_logging
from hermes.runner.acquisition.serval.client import ServalClient
from hermes.runner.acquisition.serval.server import (
    start_serval,
    stop_serval,
    wait_until_detector_connected,
    wait_until_ready,
)
from hermes.state.models.acquisition.serval import ServalAcquisitionState
from hermes.state.models.detector import DetectorSnapshot
from hermes.state_service.state_io import load_hermes_record_from_yaml

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


def main(config_path: Path = DEFAULT_YAML_PATH) -> None:
    # Step 1: Load the HERMES record and read the SERVAL settings from it.
    record = load_hermes_record_from_yaml(config_path)
    acquisition = record.acquisition
    if not isinstance(acquisition, ServalAcquisitionState):
        raise SystemExit("config must set acquisition.mode: serval")
    serval = acquisition.config.serval

    # Step 2: Send this run's logs to the run's log directory.
    log_directory = (
        record.environment.log_directory.resolved_path
        or record.environment.working_directory.resolved_path
    )
    configure_logging(log_directory, level=record.environment.log_level)

    # Step 3: Launch SERVAL, wait until it answers, then wait until it has
    # connected to the camera. SERVAL answers within a second, but the camera
    # handshake takes several seconds more; only then can the detector be read.
    process = start_serval(serval, log_directory)
    client = ServalClient(serval.url)
    try:
        software_version = wait_until_ready(client, timeout_s=60.0)
        print(f"SERVAL is up. Software version: {software_version}")

        wait_until_detector_connected(client, timeout_s=30.0)
        print("SERVAL reports a connected detector.")

        snapshot = client.get_detector_snapshot()
        print_snapshot(snapshot)
    finally:
        exit_code = stop_serval(client, process)
        client.close()
        print(f"\nSERVAL stopped (exit code {exit_code}).")

    print(f"Server log and acquisition.serval.jsonl are in: {log_directory}")


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_YAML_PATH
    main(config_path)
