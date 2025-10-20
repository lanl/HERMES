"""Demonstration script for the Serval factory helper.

This example shows how to use :func:`create_serval_client` to obtain a
``ServalHTTPService`` instance, optionally launching the Serval JVM when the
required jar is available. Run the script with ``--auto-start`` to attempt
starting Serval locally; otherwise it assumes Serval is already running and
just exercises the HTTP wrapper.

Usage::

    python examples/demo_scripts/acquisition/services/serval_factory_demo.py [--auto-start] [--jar /path/to/serval.jar]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hermes.acquisition.factories.serval import (
    ServalClientHandle,
    ServalFactoryError,
    create_serval_client,
)
from hermes.acquisition.models.environment import ServalDeployment


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serval factory demonstration")
    parser.add_argument(
        "--auto-start",
        action="store_true",
        help="Launch Serval using the resolved jar before creating the client.",
    )
    parser.add_argument(
        "--jar",
        type=Path,
        default=None,
        help="Explicit path to the Serval jar to use when auto-starting.",
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Serval host name (defaults to localhost).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Serval HTTP port (defaults to 8080).",
    )
    return parser.parse_args(argv)


def _print_header(title: str) -> None:
    print("=" * 80)
    print(title)
    print("=" * 80)


def _resolve_install_dir(jar_arg: Path | None) -> Path:
    if jar_arg is not None:
        return jar_arg.parent
    # fall back to the default install dir used by ServalDeployment
    default_path = Path("/opt/serval")
    if default_path.exists():
        return default_path
    return Path.cwd() / "serval"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    install_dir = _resolve_install_dir(args.jar)
    deployment = ServalDeployment(host=args.host, port=args.port, install_dir=install_dir)

    _print_header("Serval Deployment")
    print(f"Host           : {deployment.host}")
    print(f"Port           : {deployment.port}")
    print(f"Install dir    : {deployment.install_dir.path}")
    print(f"Default version: {deployment.default_version}")
    print()

    try:
        handle: ServalClientHandle
        with create_serval_client(
            deployment,
            auto_start=args.auto_start,
            jar_path=args.jar,
        ) as handle:
            _print_header("Factory Result")
            print("HTTP client ready.")
            if handle.process is not None:
                print(f"Serval process PID: {handle.process.pid}")
            else:
                print("No subprocess was launched (auto_start disabled).")

            _print_header("Health Check")
            try:
                health = handle.client.health_check()
                print("is_connected :", health.is_connected)
                print("is_healthy   :", health.is_healthy)
                print("last_check   :", health.last_check)
                print("response_ms  :", health.response_time_ms)
                if health.metadata:
                    print("metadata     :", health.metadata)
                else:
                    print("metadata     : {}")
            except Exception as exc:  # pragma: no cover - defensive demo guard
                print("Health probe failed:", exc)
    except ServalFactoryError as exc:
        _print_header("Factory Error")
        print("Failed to create Serval client:", exc)
        print("Hint: Run with --auto-start only when the Serval jar is available.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
