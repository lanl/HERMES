#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
acquire_tpx3.py

Defaults are built into the script. 
- User can provide a config file (-c/--config) to override defaults.
- CLI flags override both defaults and config file.
- `--dry-run` will print the final configuration and exit.
"""

import argparse
import json
import sys
from typing import Any, Dict, Optional
from hermes.acquisition import tpx3serval


# --------------------------------------------------------------------------
# Built-in default configuration (based on your INI)
# --------------------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Dict[str, Any]] = {
    "WorkingDir": {
        "path_to_working_dir": "[PATH/TO/WORKING/DIRECTORY]",
        "path_to_init_files": "initFiles/",
        "path_to_status_files": "statusFiles/",
        "path_to_log_files": "tpx3Logs/",
        "path_to_image_files": "imageFiles/",
        "path_to_rawSignal_files": "rawSignalFiles/",
        "path_to_preview_files": "previewFiles/",
        "path_to_raw_files": "tpx3Files/",
    },
    "ServerConfig": {
        "serverurl": "http://localhost:8080",   # Always use this now
        "path_to_server": "[PATH/TO/TPX3/SERVAL]",
        "path_to_server_config_files": "[/PATH/TO/CAMERASETTINGS/FROM/SERVAL/DIR]",
        "bpc_file_name": "settings.bpc",
        "dac_file_name": "settings.bpc.dacs",
        "destinations_file_name": "initial_server_destinations.json",
        "detector_config_file_name": "initial_detector_config.json",
    },
    "RunSettings": {
        "run_name": "testing",
        "run_number": "0000",
        "trigger_period_in_seconds": 10,
        "exposure_time_in_seconds": 9,
        "trigger_delay_in_seconds": 0,
        "number_of_triggers": 0,
        "number_of_runs": 1,
        "global_timestamp_interval_in_seconds": 1,
    },
}


# --------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------

def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge override into base (shallow merge per section)."""
    merged = json.loads(json.dumps(base))  # deep copy
    for section, values in override.items():
        merged.setdefault(section, {}).update(values)
    return merged


def load_config_file(path: str) -> Dict[str, Any]:
    """Load INI config using tpx3serval's parser."""
    run_settings_json = tpx3serval.config_run(path, "")
    return json.loads(run_settings_json)


def set_if_provided(cfg: Dict[str, Any], section: str, key: str, value: Optional[Any]):
    """Update cfg only if value is not None."""
    if value is not None:
        cfg[section][key] = value


def apply_overrides(cfg: Dict[str, Any], args: argparse.Namespace):
    """Override config with CLI flags."""
    # WorkingDir
    set_if_provided(cfg, "WorkingDir", "path_to_working_dir", args.working_dir)

    set_if_provided(cfg, "RunSettings", "run_name", args.run_name)

    if args.run_number is not None:
        cfg["RunSettings"]["run_number"] = f"{args.run_number:04d}"
    set_if_provided(cfg, "RunSettings", "number_of_runs", args.num_runs)
    set_if_provided(cfg, "RunSettings", "trigger_period_in_seconds", args.trigger_period)
    set_if_provided(cfg, "RunSettings", "exposure_time_in_seconds", args.exposure)
    set_if_provided(cfg, "RunSettings", "number_of_triggers", args.num_triggers)

    # Always force the server URL back to localhost:8080
    cfg["ServerConfig"]["serverurl"] = "http://localhost:8080"


def normalize_types(cfg: Dict[str, Any]):
    """Normalize types of RunSettings to int/float and fix defaults."""
    run = cfg["RunSettings"]

    run["exposure_time_in_seconds"] = float(run.get("exposure_time_in_seconds", 9))
    run["trigger_period_in_seconds"] = float(run.get("trigger_period_in_seconds", 10))
    run["trigger_delay_in_seconds"] = float(run.get("trigger_delay_in_seconds", 0))
    run["global_timestamp_interval_in_seconds"] = float(run.get("global_timestamp_interval_in_seconds", 1))

    run["number_of_triggers"] = int(run.get("number_of_triggers", 0))
    run["number_of_runs"] = int(run.get("number_of_runs", 1))

    if isinstance(run.get("run_number"), int):
        run["run_number"] = f"{run['run_number']:04d}"


def validate(cfg: Dict[str, Any]):
    """Basic sanity checks."""
    run = cfg["RunSettings"]
    exposure = float(run["exposure_time_in_seconds"])
    trigger = float(run["trigger_period_in_seconds"])
    runs = int(run["number_of_runs"])

    if exposure > trigger:
        raise ValueError("Exposure time must be <= trigger period")
    if runs < 1:
        raise ValueError("Must run at least once")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(description="TPX3 Data Acquisition")
    p.add_argument("-c", "--config", help="Optional config file to override defaults")

    # WorkingDir
    p.add_argument("-W", "--working-dir", help="Working directory path")

    p.add_argument("-r", "--run-name", help="Override run name (used in folder names)")

    # RunSettings
    p.add_argument("-N", "--run-number", type=int, help="Initial run number (int)")
    p.add_argument("-n", "--num-runs", type=int, help="Number of runs")
    p.add_argument("-t", "--trigger-period", type=int, help="Trigger period [s]")
    p.add_argument("-e", "--exposure", type=int, help="Exposure time [s]")
    p.add_argument("-T", "--num-triggers", type=int, help="Number of triggers per run")

    # Execution controls
    p.add_argument("--dry-run", action="store_true", help="Show the effective config and exit")
    p.add_argument("-v", "--verbose", type=int, choices=range(0,3), default=1,
                   help="Verbosity level (0=quiet, 2=very verbose)")
    return p


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    args = build_parser().parse_args()

    # Start with built-in defaults
    effective_config = DEFAULT_CONFIG

    # Merge config file if provided
    if args.config:
        try:
            file_config = load_config_file(args.config)
            effective_config = merge_dicts(effective_config, file_config)
            if args.verbose > 1:
                print(f"[DEBUG] Merged config file '{args.config}' into defaults")
        except Exception as e:
            print(f"[ERROR] Failed to load config file '{args.config}': {e}")
            sys.exit(1)

    # Apply CLI overrides and force serverurl
    apply_overrides(effective_config, args)
    normalize_types(effective_config)

    # Show final merged config if verbose level is high
    if args.verbose > 1:
        print("[DEBUG] Final effective configuration:")
        print(json.dumps(effective_config, indent=2))

    # Validate
    try:
        validate(effective_config)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # Dry run mode
    if args.dry_run:
        print("=== Effective Configuration (dry run) ===")
        print(json.dumps(effective_config, indent=2))
        print("=========================================")
        sys.exit(0)

    if args.verbose > 0:
        print(f"[INFO] Starting acquisition for run '{effective_config['RunSettings']['run_name']}'")
        if args.verbose > 1:
            print(f"[DEBUG] Number of runs: {effective_config['RunSettings']['number_of_runs']}")

    tpx3serval.verify_working_dir(effective_config)

    if args.verbose > 0:
        print("[INFO] Checking camera connection...")

    tpx3serval.check_camera_connection(
        effective_config["ServerConfig"]["serverurl"], 
        verbose=(args.verbose > 1)
    )

    # Load detector and server configuration
    tpx3serval.load_dacs(effective_config, verbose_level=args.verbose)
    tpx3serval.load_pixelconfig(effective_config, verbose_level=args.verbose)
    tpx3serval.set_and_load_server_destination(effective_config, verbose_level=args.verbose)
    tpx3serval.set_and_load_detector_config(effective_config, verbose_level=args.verbose)

    # Run acquisition loop
    num_runs = effective_config["RunSettings"]["number_of_runs"]
    for i in range(num_runs):
        # Set current run number (zero-padded)
        effective_config["RunSettings"]["run_number"] = f"{i:04}"

        if args.verbose > 0:
            print(f"[INFO] Starting run {i+1}/{num_runs} (run_number={effective_config['RunSettings']['run_number']})")

        # Update server destinations for this run
        tpx3serval.set_and_load_server_destination(effective_config, verbose_level=args.verbose)

        # Log configuration info
        tpx3serval.log_info(effective_config, http_string='/dashboard', verbose_level=args.verbose)
        tpx3serval.log_info(effective_config, http_string='/detector/health', verbose_level=args.verbose)
        tpx3serval.log_info(effective_config, http_string='/detector/layout', verbose_level=args.verbose)
        tpx3serval.log_info(effective_config, http_string='/detector/chips/0/dacs', verbose_level=args.verbose)
        tpx3serval.log_info(effective_config, http_string='/detector/chips/0/pixelconfig', verbose_level=args.verbose)

        # Take exposure
        tpx3serval.take_exposure(effective_config, verbose_level=args.verbose)

        if args.verbose > 0:
            print(f"[INFO] Finished run {i+1}/{num_runs}")



if __name__ == "__main__":
    main()
