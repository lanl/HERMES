import json
import os
import signal
import subprocess
import time
import datetime
from typing import Any, Dict, Optional
from hermes.acquisition import serval
from hermes.acquisition.zaber import set_zaber_ao
from hermes.acquisition.serval import start_serval_server, stop_serval_server, load_config_file
from hermes.acquisition.logging import log_info
import configparser

# --------------------------------------------------------------------------
# Configuration Management
# --------------------------------------------------------------------------

def apply_overrides(cfg: Dict[str, Any], overrides: Dict[str, Any]):
    """Apply overrides to the configuration."""
    for section, values in overrides.items():
        cfg.setdefault(section, {}).update(values)


def validate_config(cfg: Dict[str, Any]):
    """Validate the configuration."""
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


def prepare_config(config_path: str, overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Load, apply overrides, and validate the configuration."""
    config = load_config_file(config_path)
    for section, values in overrides.items():
        config.setdefault(section, {}).update(values)

    try:
        run = config["RunSettings"]
        exposure = float(run["exposure_time_in_seconds"])
        trigger = float(run["trigger_period_in_seconds"])
        runs = int(run["number_of_runs"])
    except KeyError as e:
        raise ValueError(f"Missing required RunSettings key: {e}")

    if exposure > trigger:
        raise ValueError("Exposure time must be <= trigger period")
    if runs < 1:
        raise ValueError("Must run at least once")

    return config

def save_config(config: Dict[str, Any], base_path: str, verbose: int = 1):
    """Save the configuration to the acquisition_configs folder with a timestamp."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"config_{timestamp}.ini"
    save_path = os.path.join(base_path, "CameraConfig", "acquisition_configs", file_name)

    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    config_parser = configparser.ConfigParser()
    for section, values in config.items():
        config_parser[section] = values

    with open(save_path, "w") as config_file:
        config_parser.write(config_file)

    if verbose:
        print(f"Configuration saved to {save_path}")

# --------------------------------------------------------------------------
# TPX3 Operations
# --------------------------------------------------------------------------

def run_tpx3_operations(config: Dict[str, Any], verbose: int = 1):
    """Run TPX3 operations for multiple runs."""
    num_runs = config["RunSettings"]["number_of_runs"]
    for i in range(num_runs):
        run_number = f"{i:04}"
        log_info(f"[INFO] Starting run {i+1}/{num_runs}", verbose)

        serval.set_and_load_server_destination(config, verbose_level=verbose)
        serval.log_info(config, http_string=f'/dashboard?run={run_number}', verbose_level=verbose)
        serval.take_exposure(config, verbose_level=verbose)

        log_info(f"[INFO] Finished run {i+1}/{num_runs}", verbose)

# --------------------------------------------------------------------------
# Finalized TPX3 Acquisition Functions
# --------------------------------------------------------------------------

def configure_and_run_acquisition(config_path: str, overrides: Dict[str, Any], verbose: int = 1, save: bool = False):
    """Configure and run the TPX3 acquisition process."""
    try:
        # Prepare configuration
        config = prepare_config(config_path, overrides)
        log_info("[INFO] Configuration loaded and validated.", verbose)

        # Save configuration if requested
        if save:
            save_config(config, os.path.dirname(config_path), verbose)

        # Start Serval server
        server_proc = start_serval_server(config["ServerConfig"]["path_to_server"])
        log_info("[INFO] Serval server started.", verbose)

        # Set Zaber analog output at start
        zaber_config = overrides.get("Zaber", {})
        if zaber_config.get("enabled", True):
            set_zaber_ao(
                volts=zaber_config.get("start_voltage", 4.0),
                channel=zaber_config.get("channel", 1),
                verbose=verbose,
            )

        # Run TPX3 operations
        run_tpx3_operations(config, verbose=verbose)

    finally:
        # Stop Serval server
        if 'server_proc' in locals():
            stop_serval_server(server_proc)
            log_info("[INFO] Serval server stopped.", verbose)

        # Set Zaber analog output at end
        if zaber_config.get("enabled", True):
            set_zaber_ao(
                volts=zaber_config.get("end_voltage", 0.0),
                channel=zaber_config.get("channel", 1),
                verbose=verbose,
            )