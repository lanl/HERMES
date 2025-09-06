import json
import os
import signal
import subprocess
import time
import datetime
from typing import Any, Dict, Optional
from hermes.acquisition import serval
from hermes.acquisition.zaber import set_zaber_ao
from hermes.acquisition.serval import start_serval_server, stop_serval_server
from hermes.acquisition.logging import log_info
import configparser


# --------------------------------------------------------------------------
# Configuration Management
# --------------------------------------------------------------------------

def load_config_file(config_file='run_config.ini', run_name="dummy"):
    """ Configures the run settings based on an INI config file. """
    config = configparser.ConfigParser()
    config.read(config_file)

    # Ensure sections exist
    for section in ['WorkingDir', 'RunSettings', 'ServerConfig']:
        if section not in config.sections():
            config.add_section(section)

    # NOTE: run_dir_name is clean (no trailing slash). Subpaths can have trailing
    # slashes; they will be normalized by _normalize_run_config().
    settings_dict = {
        'WorkingDir': {
            'path_to_working_dir': config.get('WorkingDir', 'path_to_working_dir', fallback="./"),
            'run_dir_name': run_name.strip('/'),
            'path_to_status_files': config.get('WorkingDir', 'path_to_status_files', fallback="statusFiles/"),
            'path_to_log_files': config.get('WorkingDir', 'path_to_log_files', fallback="tpx3Logs/"),
            'path_to_image_files': config.get('WorkingDir', 'path_to_image_files', fallback="imageFiles/"),
            'path_to_rawSignal_files': config.get('WorkingDir', 'path_to_rawSignal_files', fallback="rawSignalFiles/"),
            'path_to_preview_files': config.get('WorkingDir', 'path_to_preview_files', fallback="previewFiles/"),
            'path_to_raw_files': config.get('WorkingDir', 'path_to_raw_files', fallback="tpx3Files/"),
            'path_to_init_files': config.get('WorkingDir', 'path_to_init_files', fallback="initFiles/"),
        },
        'ServerConfig': {
            'serverurl': config.get('ServerConfig', 'serverurl', fallback=None),
            'path_to_server': config.get('ServerConfig', 'path_to_server', fallback=None),
            'path_to_server_config_files': config.get('ServerConfig', 'path_to_server_config_files', fallback=None),
            'destinations_file_name': config.get('ServerConfig', 'destinations_file_name', fallback=None),
            'detector_config_file_name': config.get('ServerConfig', 'detector_config_file_name', fallback=None),
            'bpc_file_name': config.get('ServerConfig', 'bpc_file_name', fallback=None),
            'dac_file_name': config.get('ServerConfig', 'dac_file_name', fallback=None),
        },
        'RunSettings': {
            'run_name': config.get('RunSettings', 'run_name', fallback='you_forgot_to_name_the_runs'),
            'run_number': config.get('RunSettings', 'run_number', fallback=0),
            'trigger_period_in_seconds': config.get('RunSettings', 'trigger_period_in_seconds', fallback=1.0),
            'exposure_time_in_seconds': config.get('RunSettings', 'exposure_time_in_seconds', fallback=0.5),
            'trigger_delay_in_seconds': config.get('RunSettings', 'trigger_delay_in_seconds', fallback=0.0),
            'number_of_triggers': config.get('RunSettings', 'number_of_triggers', fallback=0),
            'number_of_runs': config.get('RunSettings', 'number_of_runs', fallback=0),
            'global_timestamp_interval_in_seconds': config.get('RunSettings', 'global_timestamp_interval_in_seconds', fallback=0.0),
        },
        'Zaber': {
            'enabled': config.getboolean('Zaber', 'enabled', fallback=True),
            'channel': config.getint('Zaber', 'channel', fallback=1),
            'start_voltage': config.getfloat('Zaber', 'start_voltage', fallback=4.0),
            'end_voltage': config.getfloat('Zaber', 'end_voltage', fallback=0.0),
        }
    }

    return json.dumps(settings_dict, indent=4)


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