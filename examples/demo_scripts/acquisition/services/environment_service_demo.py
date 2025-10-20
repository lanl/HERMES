"""Demonstration script for the acquisition environment service layer.

This script builds on the pure Pydantic models showcased in
``examples/demo_scripts/acquisition/models/environment_demo.py`` and
illustrates how the runtime service code can:

* create the run directory hierarchy on disk,
* probe network endpoints declared in the environment definition, and
* optionally collect a health snapshot from the Serval HTTP service.

Run with:

    python examples/demo_scripts/acquisition/services/environment_service_demo.py

The script intentionally avoids real network or Serval dependencies. When it
reaches the Serval probing step it prints a friendly warning explaining how to
wire in a live ``ServalHTTPService`` instance.
"""

from __future__ import annotations

import json
from pathlib import Path
from pprint import pprint

from hermes.acquisition.models.environment import (
    AcquisitionEnvironment,
    NetworkEndpoint,
    ServalDeployment,
    WorkspaceLayout,
)
from hermes.acquisition.services.environment import EnvironmentService


def build_demo_environment(base_dir: Path) -> AcquisitionEnvironment:
    """Construct a minimal acquisition environment definition for the demo."""

    workspace = WorkspaceLayout(name="demo_workspace", base_dir=base_dir, include_images=True)

    camera_endpoint = NetworkEndpoint(
        name="TPX3 Camera",
        host="192.168.100.10",
        port=50000,
    )

    auxiliary_endpoint = NetworkEndpoint(
        name="NAS",
        host="nas.local",
    )

    serval = ServalDeployment(
        host="192.168.100.1",
        port=8080,
        install_dir=base_dir / "serval",
    )

    return AcquisitionEnvironment(
        name="lab-tpx3-demo",
        workspace=workspace,
        camera_endpoint=camera_endpoint,
        network_checks=[auxiliary_endpoint],
        serval=serval,
    )


def demo_environment_service() -> None:
    """Showcase the EnvironmentService helpers."""

    service = EnvironmentService()

    base_dir = Path("/tmp/hermes-demo").resolve()
    environment = build_demo_environment(base_dir)

    print("Environment configuration (JSON):")
    print(json.dumps(environment.model_dump(by_alias=True), indent=2))
    print()

    run_number = 1
    print(f"Preparing run layout for run #{run_number:03d}…")
    layout = service.ensure_run_layout(environment, run_number)
    print("Run directories created:")
    for label, path in (
        ("workspace", layout.workspace_dir.path),
        ("run", layout.run_dir.path),
        ("tpx3 data", layout.tpx3_data_dir.path),
        ("config files", layout.config_files_dir.path),
        ("logs", layout.logs_dir.path),
        ("images", layout.images_dir.path if layout.images_dir else None),
    ):
        if path is not None:
            print(f"  - {label:>12}: {path}")
    print()

    print("Probing declared network endpoints (simulated):")
    probed_endpoints = service.probe_network(environment, timeout=0.25)
    for endpoint in probed_endpoints:
        address = endpoint.host if endpoint.port is None else f"{endpoint.host}:{endpoint.port}"
        status = "reachable" if endpoint.reachable else "unreachable"
        latency = f"{endpoint.latency_ms:.2f} ms" if endpoint.latency_ms is not None else "n/a"
        print(f"  - {endpoint.name:>12} ({address}) -> {status} [{latency}]")
    print()

    print("Collecting consolidated environment status…")
    status = service.collect_status(
        environment,
        run_number=run_number,
        timeout=0.25,
        serval_service=None,  # Replace with a real ServalHTTPService to perform live health checks.
    )
    pprint(status.model_dump())

    if status.serval_health is None:
        print(
            "\nNo Serval health information collected. "
            "Instantiate hermes.acquisition.services.serval.ServalHTTPService "
            "and pass it via the 'serval_service' argument to collect live telemetry."
        )


if __name__ == "__main__":
    demo_environment_service()
