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