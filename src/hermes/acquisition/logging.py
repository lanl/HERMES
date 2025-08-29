import os
import json
import requests
from HERMES.src.hermes.acquisition.utils import _normalize_run_config, _safe_join, check_request_status, save_json_to_file

# --------------------------------------------------------------------------
# Logging Utilities for TPX3
# --------------------------------------------------------------------------

def log(message: str, verbose: int, level: int = 1):
    """Log a message if the verbosity level is sufficient."""
    if verbose >= level:
        print(message)

def print_header_line_block():
    """Print a header line block for logging."""
    print("=============================")

def print_closing_line_block():
    """Print a closing line block for logging."""
    print("-----------------------------\n")


def log_info(run_config, http_string, verbose_level=0):
    # normalize
    run_config = _normalize_run_config(run_config)

    output_json_name = http_string.replace("/", "_") + ".json"

    working_dir = run_config["WorkingDir"]['path_to_working_dir']
    run_dir     = _safe_join(working_dir, run_config["WorkingDir"]['run_dir_name'])
    logs_dir    = _safe_join(run_dir, run_config["WorkingDir"]['path_to_log_files'])

    os.makedirs(logs_dir, exist_ok=True)

    output_json_file = _safe_join(
        logs_dir,
        f"{run_config['RunSettings']['run_name']}_{run_config['RunSettings']['run_number']}{output_json_name}"
    )

    if verbose_level >= 1:
        print_header_line_block()
        print(f"Logging {http_string} info at: ")
        print(output_json_file)

    server_get_response = requests.get(url=run_config['ServerConfig']['serverurl'] + http_string)

    if verbose_level >= 2:
        print(server_get_response)

    if not check_request_status(server_get_response.status_code, verbose=True):
        print(f"Failed to get response from endpoint: {http_string}")
        return

    if not server_get_response.text.strip():
        print(f"Warning: Empty response from server for endpoint: {http_string}")
        return

    try:
        server_get_data = json.loads(server_get_response.text)
        save_json_to_file(server_get_data, output_json_file)
        if verbose_level >= 1:
            print(f"Successfully logged data from endpoint: {http_string}")
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse JSON response for endpoint: {http_string}")
        print(f"JSON decode error: {e}")
        print(f"Response text: {server_get_response.text}")
        raw_output_file = output_json_file.replace('.json', '_raw.txt')
        _ensure_parent_dir(raw_output_file)
        with open(raw_output_file, 'w') as f:
            f.write(server_get_response.text)
        print(f"Raw response saved to: {raw_output_file}")
        return

    if verbose_level >= 1:
        print_closing_line_block()
