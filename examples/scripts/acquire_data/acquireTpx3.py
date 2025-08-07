#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
acquire_tpx3.py

This script requires a configuration file (-c/--config) and allows only minimal CLI overrides:
- path_to_working_dir (WorkingDir)
- RunSettings parameters
"""

import argparse
import json
import sys
import subprocess
import os
import signal
import time
from typing import Any, Dict, Optional
from hermes.acquisition import tpx3serval

# --------------------------------------------------------------------------
# Minimal base config structure (no defaults)
# --------------------------------------------------------------------------
EMPTY_CONFIG: Dict[str, Dict[str, Any]] = {
    "WorkingDir": {},
    "ServerConfig": {},
    "RunSettings": {},
}

# --------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------

def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = json.loads(json.dumps(base))  # deep copy
    for section, values in override.items():
        merged.setdefault(section, {}).update(values)
    return merged


def load_config_file(path: str) -> Dict[str, Any]:
    """Load INI config using tpx3serval's parser."""
    run_settings_json = tpx3serval.config_run(path, "")
    return json.loads(run_settings_json)


def set_if_provided(cfg: Dict[str, Any], section: str, key: str, value: Optional[Any]):
    if value is not None:
        cfg[section][key] = value


def apply_overrides(cfg: Dict[str, Any], args: argparse.Namespace):
    """Override config with CLI flags (only WorkingDir.path_to_working_dir and RunSettings)."""
    set_if_provided(cfg, "WorkingDir", "path_to_working_dir", args.working_dir)

    set_if_provided(cfg, "RunSettings", "run_name", args.run_name)
    if args.run_number is not None:
        cfg["RunSettings"]["run_number"] = f"{args.run_number:04d}"
    set_if_provided(cfg, "RunSettings", "number_of_runs", args.num_runs)
    set_if_provided(cfg, "RunSettings", "trigger_period_in_seconds", args.trigger_period)
    set_if_provided(cfg, "RunSettings", "exposure_time_in_seconds", args.exposure)
    set_if_provided(cfg, "RunSettings", "number_of_triggers", args.num_triggers)

    # Always enforce localhost server
    cfg["ServerConfig"]["serverurl"] = "http://localhost:8080"


def normalize_types(cfg: Dict[str, Any]):
    run = cfg["RunSettings"]

    run["exposure_time_in_seconds"] = float(run["exposure_time_in_seconds"])
    run["trigger_period_in_seconds"] = float(run["trigger_period_in_seconds"])
    run["trigger_delay_in_seconds"] = float(run.get("trigger_delay_in_seconds", 0))
    run["global_timestamp_interval_in_seconds"] = float(run.get("global_timestamp_interval_in_seconds", 1))

    run["number_of_triggers"] = int(run["number_of_triggers"])
    run["number_of_runs"] = int(run["number_of_runs"])

    if isinstance(run.get("run_number"), int):
        run["run_number"] = f"{run['run_number']:04d}"


def validate(cfg: Dict[str, Any]):
    """Check that required fields are present and valid."""
    try:
        run = cfg["RunSettings"]
        exposure = float(run["exposure_time_in_seconds"])
        trigger = float(run["trigger_period_in_seconds"])
        runs = int(run["number_of_runs"])
    except KeyError as e:
        raise ValueError(f"Missing required RunSettings key: {e}")

    if exposure > trigger:
        raise ValueError("Exposure time must be <= trigger period")
    if runs < 1:
        raise ValueError("Must run at least once")


def start_serval_server(path_to_server: str) -> subprocess.Popen:
    """
    Start the Serval server as a background process.
    Returns the process handle so it can be terminated later.
    """
    jar_path = os.path.join(path_to_server, "serv-2.1.6.jar")
    if not os.path.isfile(jar_path):
        raise FileNotFoundError(f"Could not find serval JAR at '{jar_path}'")

    proc = subprocess.Popen(
        ["java", "-jar", jar_path],
        cwd=path_to_server,
        stdout=subprocess.PIPE, # Standard output is stored here to not clog up terminal
        stderr=subprocess.PIPE, # Standard error is stored here to not clog up terminal
        preexec_fn=os.setsid  # So we can terminate the whole process group later
    )
    return proc



# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(description="TPX3 Data Acquisition (requires config file)")
    p.add_argument("-c", "--config", required=True, help="Path to required config file")

    # Allowed CLI overrides
    p.add_argument("-W", "--working-dir", help="Working directory path")
    p.add_argument("-r", "--run-name", help="Run name")

    p.add_argument("-N", "--run-number", type=int, help="Initial run number (int)")
    p.add_argument("-n", "--num-runs", type=int, help="Number of runs")
    p.add_argument("-t", "--trigger-period", type=int, help="Trigger period [s]")
    p.add_argument("-e", "--exposure", type=int, help="Exposure time [s]")
    p.add_argument("-T", "--num-triggers", type=int, help="Number of triggers per run")

    # Optional flags
    p.add_argument("--dry-run", action="store_true", help="Show effective config and exit")
    p.add_argument("-v", "--verbose", type=int, choices=range(0, 3), default=1,
                   help="Verbosity level (0=quiet, 2=very verbose)")
    return p

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    args = build_parser().parse_args()

    try:
        file_config = load_config_file(args.config)
        effective_config = merge_dicts(EMPTY_CONFIG, file_config)
        if args.verbose > 1:
            print(f"[DEBUG] Loaded config from '{args.config}'")
    except Exception as e:
        print(f"[ERROR] Failed to load config file '{args.config}': {e}")
        sys.exit(1)

    apply_overrides(effective_config, args)
    normalize_types(effective_config)

    if args.verbose > 1:
        print("[DEBUG] Effective configuration:")
        print(json.dumps(effective_config, indent=2))

    try:
        validate(effective_config)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    if args.dry_run:
        print("=== Effective Configuration (dry run) ===")
        print(json.dumps(effective_config, indent=2))
        print("=========================================")
        sys.exit(0)

    path_to_server = effective_config["ServerConfig"]["path_to_server"]
    server_proc = None

    try:
        if args.verbose > 0:
            print("[INFO] Starting Serval server...")

        server_proc = start_serval_server(path_to_server)

        time.sleep(5)  # Quick time delay just to ensure that serval has time to load up.

        if args.verbose > 0:
            print("[INFO] Serval server started.")

        tpx3serval.verify_working_dir(effective_config)

        if args.verbose > 0:
            print("[INFO] Checking camera connection...")

        tpx3serval.check_camera_connection(
            effective_config["ServerConfig"]["serverurl"],
            verbose=(args.verbose > 1)
        )

        tpx3serval.load_dacs(effective_config, verbose_level=args.verbose)
        tpx3serval.load_pixelconfig(effective_config, verbose_level=args.verbose)
        tpx3serval.set_and_load_server_destination(effective_config, verbose_level=args.verbose)
        tpx3serval.set_and_load_detector_config(effective_config, verbose_level=args.verbose)

        num_runs = effective_config["RunSettings"]["number_of_runs"]
        for i in range(num_runs):
            effective_config["RunSettings"]["run_number"] = f"{i:04}"

            if args.verbose > 0:
                print(f"[INFO] Starting run {i+1}/{num_runs}")

            tpx3serval.set_and_load_server_destination(effective_config, verbose_level=args.verbose)

            tpx3serval.log_info(effective_config, http_string='/dashboard', verbose_level=args.verbose)
            tpx3serval.log_info(effective_config, http_string='/detector/health', verbose_level=args.verbose)
            tpx3serval.log_info(effective_config, http_string='/detector/layout', verbose_level=args.verbose)
            tpx3serval.log_info(effective_config, http_string='/detector/chips/0/dacs', verbose_level=args.verbose)
            tpx3serval.log_info(effective_config, http_string='/detector/chips/0/pixelconfig', verbose_level=args.verbose)

            tpx3serval.take_exposure(effective_config, verbose_level=args.verbose)

            if args.verbose > 0:
                print(f"[INFO] Finished run {i+1}/{num_runs}")

    finally:
        if server_proc is not None:
            if args.verbose > 0:
                print("[INFO] Terminating Serval server...")
            # Kill the process group to make sure all child processes are stopped
            os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
            server_proc.wait()
            if args.verbose > 0:
                print("[INFO] Serval server terminated.")


if __name__ == "__main__":
    main()
