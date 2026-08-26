from __future__ import annotations

import sys
from pathlib import Path

from hermes.logging import configure_logging
from hermes.runner.acquisition.serval.client import ServalClient
from hermes.runner.acquisition.serval.server import (
    start_serval,
    stop_serval,
    wait_until_ready,
)
from hermes.state.models.acquisition.serval import ServalAcquisitionState
from hermes.state_service.state_io import load_hermes_record_from_yaml

DEFAULT_YAML_PATH = Path(__file__).with_name("config.yaml")


def main(config_path: Path = DEFAULT_YAML_PATH) -> None:
    # Step 1: Load the HERMES record and read the SERVAL settings from it.
    record = load_hermes_record_from_yaml(config_path)
    acquisition = record.acquisition
    if not isinstance(acquisition, ServalAcquisitionState):
        raise SystemExit("config must set acquisition.mode: serval")
    serval = acquisition.config.serval

    # Step 2: Send this run's logs (server + acquisition.serval.jsonl) to the
    # run's log directory, falling back to the working directory.
    log_directory = (
        record.environment.log_directory.resolved_path
        or record.environment.working_directory.resolved_path
    )
    configure_logging(log_directory, level=record.environment.log_level)

    # Step 3: Launch SERVAL, wait until it answers, then shut it back down.
    process = start_serval(serval, log_directory)
    client = ServalClient(serval.url)
    try:
        software_version = wait_until_ready(client, timeout_s=60.0)
        print(f"SERVAL is up. Software version: {software_version}")
    finally:
        exit_code = stop_serval(client, process)
        client.close()
        print(f"SERVAL stopped (exit code {exit_code}).")

    print(f"Server log and acquisition.serval.jsonl are in: {log_directory}")


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_YAML_PATH
    main(config_path)
