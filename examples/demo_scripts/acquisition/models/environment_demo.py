"""Simple CLI demonstration of the acquisition environment models.

This script shows how to:
- build an ``AcquisitionEnvironment`` definition
- derive run directory layouts using ``WorkspaceLayout``
- list which filesystem paths a controller should create before starting a run

Run with: ``python examples/demo_scripts/acquisition/models/environment_demo.py``
"""

from __future__ import annotations

import json
from pathlib import Path

from hermes.acquisition.models.environment import (
    AcquisitionEnvironment,
    NetworkEndpoint,
    ServalDeployment,
    WorkspaceLayout,
)


def build_environment() -> AcquisitionEnvironment:
    """Construct an example acquisition environment configuration."""

    workspace = WorkspaceLayout(name="demo_workspace", base_dir=Path("/tmp"))

    camera = NetworkEndpoint(name="TPX3 Camera", host="192.168.0.10", reachable=True, latency_ms=1.8)
    servers = [
        NetworkEndpoint(name="DAQ Server", host="192.168.0.11", reachable=True),
        NetworkEndpoint(name="Storage", host="192.168.0.12", reachable=False),
    ]

    serval = ServalDeployment(
        host="192.168.0.11",
        install_dir=Path("/opt/serval"),
        config_dir=Path("/opt/serval/config"),
    )

    return AcquisitionEnvironment(
        name="lab-tpx3-demo",
        workspace=workspace,
        camera_endpoint=camera,
        network_checks=servers,
        serval=serval,
    )


def demonstrate_run_layout(env: AcquisitionEnvironment, run_number: int) -> None:
    """Print the run directory layout and required directories for a run."""

    layout = env.workspace.make_run_layout(run_number)

    print(f"Run {layout.run_id} directories:")
    for label, path in (
        ("Workspace", layout.workspace_dir.path),
        ("Run", layout.run_dir.path),
        ("TPX3 data", layout.tpx3_data_dir.path),
        ("Config files", layout.config_files_dir.path),
        ("Logs", layout.logs_dir.path),
        ("Images", layout.images_dir.path if layout.images_dir else None),
    ):
        if path is not None:
            print(f"  - {label}: {path}")

    print("Required directories to create:")
    for required in layout.required_directories:
        print(f"  * {required}")
    print()


def main() -> None:
    env = build_environment()

    print("Acquisition environment (JSON):")
    print(json.dumps(env.model_dump(by_alias=True), indent=2))
    print()

    for run_num in range(3):
        demonstrate_run_layout(env, run_num)

    print("All endpoints to ping:")
    for endpoint in env.all_endpoints:
        status = "reachable" if endpoint.reachable else "unreachable"
        print(f"  - {endpoint.name} ({endpoint.host}) -> {status}")


if __name__ == "__main__":
    main()
