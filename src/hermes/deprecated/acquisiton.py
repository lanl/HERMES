import sys, os
from pathlib import Path
import pathlib
import json
import requests
import matplotlib.pyplot as plt
import configparser
import time
from datetime import datetime
import shutil

from hermes.acquisition.models import WorkingDir, RunSettings, Settings
from hermes.acquisition.serval.models import ServalConfig, Serval_2_1_6

###############################################################
# Me make code output pretty!
#--------------------------------------------------------------
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header_line_block():
    print(f"{bcolors.WARNING}============================={bcolors.ENDC}")

def print_closing_line_block():
    print(f"{bcolors.WARNING}-----------------------------{bcolors.ENDC}\n")


###############################################################
# Safe path & config normalization utilities
#--------------------------------------------------------------
# All WorkingDir keys that must be *relative* to the run_dir
_RELATIVE_WD_KEYS = {
    "path_to_raw_files",
    "path_to_image_files",
    "path_to_rawSignal_files",
    "path_to_preview_files",
    "path_to_log_files",
    "path_to_status_files",
    "path_to_init_files",
}

def _safe_join(base, *parts) -> str:
    """
    Join path segments but strip leading slashes on parts so the base isn't discarded.
    Prevents os.path.join(base, '/x') -> '/x'.
    """
    p = Path(base)
    for part in parts:
        if part is None:
            continue
        s = str(part)
        s = s.lstrip("/")  # strip leading '/' so we don't jump to root
        if s:
            p = p / s
    return str(p)

def _ensure_parent_dir(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)

def _normalize_run_config(run_configs):
    """
    Normalize dict-like config (or Settings):
      - WorkingDir.path_to_working_dir -> absolute path
      - WorkingDir.run_dir_name -> set & never starts with '/'
      - All WorkingDir subpaths (log/init/raw/etc.) -> relative (no leading '/')
    Returns the same object (mutated).
    """
    cfg = run_configs

    # Accessors for dict and pydantic Settings
    def get(section, key, default=None):
        if isinstance(cfg, dict):
            return cfg.get(section, {}).get(key, default)
        sect = getattr(cfg, section, None)
        return getattr(sect, key, default) if sect is not None else default

    def setv(section, key, value):
        if isinstance(cfg, dict):
            cfg.setdefault(section, {})
            cfg[section][key] = value
        else:
            setattr(getattr(cfg, section), key, value)

    # Working directory -> absolute
    working_dir = get("WorkingDir", "path_to_working_dir", "")
    if not working_dir:
        raise ValueError("WorkingDir.path_to_working_dir is required.")
    working_dir = str(Path(working_dir).expanduser().resolve())
    setv("WorkingDir", "path_to_working_dir", working_dir)

    # run_dir_name -> prefer explicit, else derive from run_name
    run_dir_name = get("WorkingDir", "run_dir_name", "")
    if not run_dir_name or run_dir_name == "/":
        run_dir_name = (get("RunSettings", "run_name", "") or "").strip()
    run_dir_name = run_dir_name.strip().lstrip("/")
    if not run_dir_name:
        run_dir_name = "run"  # final fallback, never empty
    setv("WorkingDir", "run_dir_name", run_dir_name)

    # Force WorkingDir subpaths to be relative (no leading ‘/’)
    for k in _RELATIVE_WD_KEYS:
        v = get("WorkingDir", k, "")
        if v is None:
            continue
        setv("WorkingDir", k, str(v).lstrip("/"))

    return cfg


###############################################################
# Configuring functions
#--------------------------------------------------------------
def verify_working_dir(run_configs):
    """Verifies the working directory and its sub-directories exist.
       If the run directory exists, it is cleaned (deleted)."""
    if not isinstance(run_configs, Settings):
        run_configs = Settings.parse_obj(run_configs)

    # Normalize config once
    run_configs = _normalize_run_config(run_configs)

    working_dir = run_configs.WorkingDir.path_to_working_dir
    run_dir_name = run_configs.WorkingDir.run_dir_name

    run_dir             = _safe_join(working_dir, run_dir_name)
    raw_file_dir        = _safe_join(run_dir, run_configs.WorkingDir.path_to_raw_files)
    image_file_dir      = _safe_join(run_dir, run_configs.WorkingDir.path_to_image_files)
    raw_signals_file_dir= _safe_join(run_dir, run_configs.WorkingDir.path_to_rawSignal_files)
    preview_file_dir    = _safe_join(run_dir, run_configs.WorkingDir.path_to_preview_files)
    tpx3_log_files_dir  = _safe_join(run_dir, run_configs.WorkingDir.path_to_log_files)
    status_files_dir    = _safe_join(run_dir, run_configs.WorkingDir.path_to_status_files)
    init_files_dir      = _safe_join(run_dir, run_configs.WorkingDir.path_to_init_files)

    # Safety
    if run_dir in ("", "/"):
        raise RuntimeError("verify_working_dir() refusing to operate on root directory")

    # Clean run dir if exists
    if os.path.exists(run_dir):
        print(f"Duplicate directory exists. Cleaning existing directory: {run_dir}")
        shutil.rmtree(run_dir)

    # Create tree
    directories = [
        run_dir,
        raw_file_dir,
        image_file_dir,
        preview_file_dir,
        raw_signals_file_dir,
        tpx3_log_files_dir,
        status_files_dir,
        init_files_dir,
    ]
    for d in directories:
        os.makedirs(d, exist_ok=True)


def config_run(config_file='run_config.ini', run_name="dummy"):
    """ Configures the run settings based on an INI config file. """
    config = configparser.ConfigParser()
    config.read(config_file)

    # Ensure sections exist
    for section in ['WorkingDir', 'RunSettings', 'ServalConfig']:
        if section not in config.sections():
            config.add_section(section)

    # Create WorkingDir model
    working_dir = WorkingDir(
        path_to_working_dir=config.get('WorkingDir', 'path_to_working_dir', fallback="./"),
        run_dir_name=run_name.strip('/'),
        path_to_status_files=config.get('WorkingDir', 'path_to_status_files', fallback="statusFiles/"),
        path_to_log_files=config.get('WorkingDir', 'path_to_log_files', fallback="tpx3Logs/"),
        path_to_image_files=config.get('WorkingDir', 'path_to_image_files', fallback="imageFiles/"),
        path_to_rawSignal_files=config.get('WorkingDir', 'path_to_rawSignal_files', fallback="rawSignalFiles/"),
        path_to_preview_files=config.get('WorkingDir', 'path_to_preview_files', fallback="previewFiles/"),
        path_to_raw_files=config.get('WorkingDir', 'path_to_raw_files', fallback="tpx3Files/"),
        path_to_init_files=config.get('WorkingDir', 'path_to_init_files', fallback="initFiles/"),
    )

    # Create ServalConfig model with default Serval_2_1_6 settings
    serval_settings = ServalConfig(
        servalurl=config.get('ServalConfig', 'servalurl', fallback="http://localhost:8080"),
        path_to_serval=config.get('ServalConfig', 'path_to_serval', fallback="./serval/"),
        path_to_serval_config_files=config.get('ServalConfig', 'path_to_serval_config_files', fallback="servalConfigFiles/"),
        destinations_file_name=config.get('ServalConfig', 'destinations_file_name', fallback="initial_serval_destinations.json"),
        detector_config_file_name=config.get('ServalConfig', 'detector_config_file_name', fallback="initial_detector_config.json"),
        bpc_file_name=config.get('ServalConfig', 'bpc_file_name', fallback="settings.bpc"),
        dac_file_name=config.get('ServalConfig', 'dac_file_name', fallback="settings.bpc.dac"),
        
        # Use default Serval_2_1_6 settings - will use model defaults
        serval=Serval_2_1_6()
    )

    # Create RunSettings model
    run_settings = RunSettings(
        run_name=config.get('RunSettings', 'run_name', fallback='you_forgot_to_name_the_runs'),
        run_number=config.getint('RunSettings', 'run_number', fallback=0),
        trigger_period_in_seconds=config.getfloat('RunSettings', 'trigger_period_in_seconds', fallback=1.0),
        exposure_time_in_seconds=config.getfloat('RunSettings', 'exposure_time_in_seconds', fallback=0.5),
        trigger_delay_in_seconds=config.getfloat('RunSettings', 'trigger_delay_in_seconds', fallback=0.0),
        number_of_triggers=config.getint('RunSettings', 'number_of_triggers', fallback=0),
        number_of_runs=config.getint('RunSettings', 'number_of_runs', fallback=0),
        global_timestamp_interval_in_seconds=config.getfloat('RunSettings', 'global_timestamp_interval_in_seconds', fallback=0.0),
    )

    # Create complete Settings model
    settings = Settings(
        WorkingDir=working_dir,
        ServalConfig=serval_settings,
        RunSettings=run_settings
    )

    return settings.json(indent=4)


###############################################################
# Loading helpers
#--------------------------------------------------------------
def load_json_file(file_path):
    """Load a JSON file into a Python dict."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("The specified file was not found.")
        return None
    except json.JSONDecodeError:
        print("Failed to decode the JSON file.")
        return None

def save_json_to_file(data, filename):
    _ensure_parent_dir(filename)
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

def load_dacfile_to_json(file_path, verbose_level=0):
    """Load key:value DAC file into dict[int]."""
    dacs = {}
    try:
        with open(file_path, 'r') as f:
            for line in f.readlines():
                line = line.strip()
                if not line or line.startswith('['):
                    continue
                key, value = line.split(':')
                dacs[key] = int(value)
        return dacs
    except FileNotFoundError:
        print("The specified file was not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


###############################################################
# Server / config upload functions
#--------------------------------------------------------------
def set_and_load_server_destination(run_configs, verbose_level=0):
    run_configs = _normalize_run_config(run_configs)

    if verbose_level >= 1:
        print_header_line_block()
        print("Setting up server destination for TPX3Cam")

    working_dir = run_configs["WorkingDir"]['path_to_working_dir']
    init_dir    = _safe_join(working_dir, run_configs["WorkingDir"]['path_to_init_files'])
    init_name   = run_configs["ServalConfig"]['destinations_file_name']

    # Check init dir & file
    if not os.path.isdir(init_dir) or not any(f.endswith('.json') for f in os.listdir(init_dir)):
        print(f"No .json files found in {init_dir}. Exiting with error.")
        sys.exit(1)
    path_to_json_file = _safe_join(init_dir, init_name)
    if not os.path.isfile(path_to_json_file):
        print(f"File {init_name} does not exist in {init_dir}. Exiting with error.")
        sys.exit(1)

    run_dir          = _safe_join(working_dir, run_configs["WorkingDir"]['run_dir_name'])
    raw_file_dir     = _safe_join(run_dir, run_configs["WorkingDir"]['path_to_raw_files'])
    image_file_dir   = _safe_join(run_dir, run_configs["WorkingDir"]['path_to_image_files'])
    preview_file_dir = _safe_join(run_dir, run_configs["WorkingDir"]['path_to_preview_files'])

    destination_json_data = load_json_file(path_to_json_file)
    if verbose_level >= 1:
        print("Loading destination json file from:")
        print(path_to_json_file)
        if verbose_level >= 2:
            print(destination_json_data)

    if verbose_level >= 1:
        print("Updating destinations in json structure based on run config file")
        if verbose_level >= 2:
            print(f"Dir for tpx3 files: {raw_file_dir}")
            print(f"Dir for image files: {image_file_dir}")
            print(f"Dir for preview files: {preview_file_dir}")

    abs_raw  = os.path.abspath(raw_file_dir)
    abs_img  = os.path.abspath(image_file_dir)
    abs_prev = os.path.abspath(preview_file_dir)

    destination_json_data['Raw'][0]['Base']        = "file:" + abs_raw
    destination_json_data['Raw'][0]['FilePattern'] = run_configs["RunSettings"]['run_name'] + "_" + run_configs["RunSettings"]['run_number'] + "_%MdHms_"

    destination_json_data['Image'][0]['Base']        = "file:" + abs_img
    destination_json_data['Image'][0]['FilePattern'] = "ToT_" + run_configs["RunSettings"]['run_name'] + "_" + run_configs["RunSettings"]['run_number'] + "_%MdHms_"

    for channel in destination_json_data['Preview']['ImageChannels']:
        channel['Base']        = "file:" + abs_prev
        channel['FilePattern'] = run_configs["RunSettings"]['run_name'] + "_" + run_configs["RunSettings"]['run_number'] + "_%MdHms_"

    destination_set_response = requests.put(
        url=run_configs['ServalConfig']['servalurl'] + '/serval/destination',
        data=json.dumps(destination_json_data)
    )
    destination_set_data = destination_set_response.text.strip("\n")
    if verbose_level >= 1:
        print(f'{bcolors.OKGREEN}Response: {destination_set_data}{bcolors.ENDC}')
        print_closing_line_block()


def set_and_load_detector_config(run_configs, verbose_level=0):
    run_configs = _normalize_run_config(run_configs)

    working_dir = run_configs["WorkingDir"]['path_to_working_dir']
    init_dir    = _safe_join(working_dir, run_configs["WorkingDir"]['path_to_init_files'])
    init_name   = run_configs["ServalConfig"]['detector_config_file_name']

    path_to_json_file = _safe_join(init_dir, init_name)
    detector_config_json_data = load_json_file(path_to_json_file)

    if verbose_level >= 1:
        print_header_line_block()
        print("Loading detector config json file from:")
        print(path_to_json_file)
        if verbose_level >= 2:
            print(detector_config_json_data)

    if verbose_level >= 1:
        print("Updating detector config parameters in json structure based on run config file")

    detector_config_json_data['TriggerPeriod']           = run_configs['RunSettings']['trigger_period_in_seconds']
    detector_config_json_data['TriggerDelay']            = run_configs['RunSettings']['trigger_delay_in_seconds']
    detector_config_json_data['ExposureTime']            = run_configs['RunSettings']['exposure_time_in_seconds']
    detector_config_json_data['nTriggers']               = run_configs['RunSettings']['number_of_triggers']
    detector_config_json_data['GlobalTimestampInterval'] = run_configs['RunSettings']['global_timestamp_interval_in_seconds']

    detector_config_set_response = requests.put(
        url=run_configs['ServalConfig']['servalurl'] + '/detector/config',
        data=json.dumps(detector_config_json_data)
    )
    detector_config_set_data = detector_config_set_response.text.strip("\n")
    if verbose_level >= 1:
        print(f'{bcolors.OKGREEN}Response: {detector_config_set_data}{bcolors.ENDC}')
        print_closing_line_block()


def load_dacs(run_configs, verbose_level=0):
    run_configs = _normalize_run_config(run_configs)

    path_to_json_file = _safe_join(
        run_configs["ServalConfig"]['path_to_serval'],
        run_configs["ServalConfig"]['path_to_serval_config_files'],
        run_configs['ServalConfig']['dac_file_name']
    )
    dacs_json_data = load_dacfile_to_json(path_to_json_file)

    if verbose_level >= 1:
        print_header_line_block()
        print("Loading dacs file from:")
        print(path_to_json_file)
        if verbose_level >= 2:
            print(dacs_json_data)

    dacs_set_response = requests.put(
        url=run_configs['ServalConfig']['servalurl'] + '/detector/chips/0/dacs',
        data=json.dumps(dacs_json_data)
    )
    dacs_set_data = dacs_set_response.text.strip("\n")

    if verbose_level >= 1:
        print(f'{bcolors.OKGREEN}Response: {dacs_set_data}{bcolors.ENDC}')
        print_closing_line_block()


def load_pixelconfig(run_configs, verbose_level=0):
    run_configs = _normalize_run_config(run_configs)

    bpc_file_location = _safe_join(
        run_configs["ServalConfig"]['path_to_serval'],
        run_configs["ServalConfig"]['path_to_serval_config_files'],
        run_configs['ServalConfig']['bpc_file_name']
    )
    with open(bpc_file_location, 'rb') as bpc_file:
        bpc_binary_data = bpc_file.read()

    if verbose_level >= 1:
        print_header_line_block()
        print("Loading pixelconfig file from:")
        print(bpc_file_location)

    bpc_set_response = requests.put(
        url=run_configs['ServalConfig']['servalurl'] + '/detector/chips/0/pixelconfig?format=bpc',
        data=bpc_binary_data
    )
    bpc_set_data = bpc_set_response.text.strip("\n")

    if verbose_level >= 1:
        print(f'{bcolors.OKGREEN}Response: {bpc_set_data}{bcolors.ENDC}')
        print_closing_line_block()


###############################################################
# Verification functions
#--------------------------------------------------------------
def check_request_status(status_code, verbose=False):
    """Check HTTP status and print helpful messages."""
    if status_code == 200:
        if verbose:
            print(f"{bcolors.OKGREEN}OK: The request has succeeded.{bcolors.ENDC}")
        return True

    if status_code == 204:
        msg = "No Content: The server fulfilled the request; no new information."
    elif status_code == 302:
        msg = "Moved Temporarily: The server redirects to the URI in Location header."
    elif status_code == 400:
        msg = "Bad Request: The request had bad syntax or was impossible to fulfill."
    elif status_code == 401:
        msg = "Unauthorized: Authentication required or refused."
    elif status_code == 404:
        msg = "Not Found: No resource matches the request."
    elif status_code == 409:
        msg = "Conflict: Request conflicts with current resource state."
    elif status_code == 500:
        msg = "Internal Error: Unexpected condition prevented fulfillment."
    elif status_code == 503:
        msg = "Service Unavailable: Temporary overload."
    else:
        msg = f"Unhandled status code: {status_code}"

    if verbose:
        print(f"{bcolors.FAIL}Error ({status_code}): {msg}{bcolors.ENDC}")
    return False

def check_camera_connection(server_url, verbose=False):
    """Check connection to TPX3Cam at server_url (usually http://localhost:8080)."""
    if verbose:
        print_header_line_block()
        print(f"Connecting to Camera at {server_url}")

    request_status = requests.get(url=server_url)
    status = check_request_status(request_status.status_code, verbose)

    if verbose:
        if not status:
            print(f"{bcolors.FAIL}Could not connect to Camera at {bcolors.ENDC}{server_url}")
            print_closing_line_block()
            sys.exit(1)
        else:
            print(f"{bcolors.OKGREEN}Succesfully connected to Camera at {bcolors.ENDC}{server_url}")
            print_closing_line_block()


###############################################################
# Logging functions
#--------------------------------------------------------------
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

    serval_get_response = requests.get(url=run_config['ServalConfig']['servalurl'] + http_string)

    if verbose_level >= 2:
        print(serval_get_response)

    if not check_request_status(serval_get_response.status_code, verbose=True):
        print(f"Failed to get response from endpoint: {http_string}")
        return

    if not serval_get_response.text.strip():
        print(f"Warning: Empty response from serval for endpoint: {http_string}")
        return

    try:
        serval_get_data = json.loads(serval_get_response.text)
        save_json_to_file(serval_get_data, output_json_file)
        if verbose_level >= 1:
            print(f"Successfully logged data from endpoint: {http_string}")
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse JSON response for endpoint: {http_string}")
        print(f"JSON decode error: {e}")
        print(f"Response text: {serval_get_response.text}")
        raw_output_file = output_json_file.replace('.json', '_raw.txt')
        _ensure_parent_dir(raw_output_file)
        with open(raw_output_file, 'w') as f:
            f.write(serval_get_response.text)
        print(f"Raw response saved to: {raw_output_file}")
        return

    if verbose_level >= 1:
        print_closing_line_block()


def save_to_init(run_config, http_string, verbose_level=0):
    run_config = _normalize_run_config(run_config)

    output_json_name = http_string.replace("/", "_") + ".json"
    working_dir = run_config["WorkingDir"]['path_to_working_dir']
    run_dir     = _safe_join(working_dir, run_config["WorkingDir"]['run_dir_name'])
    init_dir    = _safe_join(run_dir, run_config['WorkingDir']['path_to_init_files'])

    os.makedirs(init_dir, exist_ok=True)

    output_json_file = _safe_join(
        init_dir,
        f"{run_config['RunSettings']['run_name']}_{run_config['RunSettings']['run_number']}{output_json_name}"
    )

    if verbose_level >= 1:
        print_header_line_block()
        print(f"Logging {http_string} info at: ")
        print(output_json_file)

    serval_get_response = requests.get(url=run_config['ServalConfig']['servalurl'] + http_string)
    if verbose_level >= 2:
        print(serval_get_response)

    if not check_request_status(serval_get_response.status_code, verbose=True):
        print(f"Failed to get response from endpoint: {http_string}")
        return

    if not serval_get_response.text.strip():
        print(f"Warning: Empty response from serval for endpoint: {http_string}")
        return

    try:
        serval_get_data = json.loads(serval_get_response.text)
        save_json_to_file(serval_get_data, output_json_file)
        if verbose_level >= 1:
            print(f"Successfully logged data from endpoint: {http_string}")
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse JSON response for endpoint: {http_string}")
        print(f"JSON decode error: {e}")
        print(f"Response text: {serval_get_response.text}")
        raw_output_file = output_json_file.replace('.json', '_raw.txt')
        _ensure_parent_dir(raw_output_file)
        with open(raw_output_file, 'w') as f:
            f.write(serval_get_response.text)
        print(f"Raw response saved to: {raw_output_file}")
        return

    if verbose_level >= 1:
        print_closing_line_block()


###############################################################
# DAQ functions
#--------------------------------------------------------------
def print_status_bar(elapsed_time, expected_time_left, exposure_time, pixel_rate, tdc1_rate, frame_count, total_number_of_exposures):
    current_frame = frame_count + 1
    total_time = exposure_time * total_number_of_exposures
    if expected_time_left == 0:
        time_left = 0
    else:
        time_left = expected_time_left - elapsed_time % exposure_time

    progress = min(100, int((elapsed_time / total_time) * 100))

    status_bar = f"[{'#' * (progress // 2)}{' ' * (50 - progress // 2)}] {progress}%"
    status_bar += f" Elapsed Time: {elapsed_time:.2f} s, "
    status_bar += f"Expected Time Left: {time_left:.2f} s, "
    status_bar += f"Pixel Rate: {pixel_rate} hps, "
    status_bar += f"TDC1 Rate: {tdc1_rate} tps, "
    status_bar += f"Frame: {current_frame} of {total_number_of_exposures}"

    sys.stdout.write("\033[K")  # Clear line
    sys.stdout.write(status_bar)
    sys.stdout.flush()
    sys.stdout.write("\r")  # Move cursor to the beginning of the line

def make_user_wait(measurement_info, verbose_level=0):
    """
    Waits for any previous acquisition to finish before starting a new one.
    """
    if verbose_level >= 2:
        print(f"[DEBUG] make_user_wait() received dashboard data: {measurement_info}")

    # If "Measurement" key is missing or None, we can't wait on it
    if not measurement_info or "Measurement" not in measurement_info or not measurement_info["Measurement"]:
        if verbose_level >= 1:
            print("[WARN] No Measurement info in dashboard response; skipping wait.")
        return

    measurement = measurement_info["Measurement"]

    # If no Status key, bail out
    if "Status" not in measurement:
        if verbose_level >= 1:
            print("[WARN] Measurement info missing Status; skipping wait.")
        return

    # If status is active, wait out the TimeLeft
    if measurement["Status"] != "DA_IDLE":
        elapsed_time = measurement.get("ElapsedTime", "?")
        time_left = measurement.get("TimeLeft", 0)

        print(f"Waiting for previous acquisition to finish.")
        print(f"Previous measurement started {elapsed_time} ago and has {time_left} seconds left.")
        print(f"Waiting for {time_left} seconds...")

        time.sleep(time_left)


def take_exposure(run_config_struct, verbose_level=0):
    import time as _time

    # Normalize in case caller passed a plain dict
    run_config_struct = _normalize_run_config(run_config_struct)

    run_name_number = run_config_struct['RunSettings']['run_name'] + "_" + run_config_struct['RunSettings']['run_number']
    number_of_exposures = int(run_config_struct['RunSettings']['number_of_triggers'])
    exposure_time = float(run_config_struct['RunSettings']['exposure_time_in_seconds'])

    # Wait if a measurement is already running
    dashboard_response = requests.get(url=run_config_struct['ServalConfig']['servalurl'] + '/dashboard')
    dashboard_data = json.loads(dashboard_response.text)
    make_user_wait(dashboard_data)

    if verbose_level >= 1:
        print_header_line_block()

    # Start measurement
    resp = requests.get(url=run_config_struct['ServalConfig']['servalurl'] + '/measurement/start')
    check_request_status(resp.status_code, verbose=True)

    # Start time
    start_time = _time.time()

    # Poll status
    while True:
        dashboard_response = requests.get(url=run_config_struct['ServalConfig']['servalurl'] + '/dashboard')
        dashboard_data = json.loads(dashboard_response.text)
        measurement = dashboard_data.get("Measurement")

        if measurement["Status"] == "DA_IDLE":
            break

        elapsed_time = measurement.get("ElapsedTime", _time.time() - start_time)
        expected_time_left = measurement.get("TimeLeft", 0)
        pixel_rate = measurement.get("PixelEventRate", 0)
        frame_count = measurement.get("FrameCount", 0)

        print_status_bar(elapsed_time, expected_time_left, exposure_time, pixel_rate, tdc1_rate=0,
                         frame_count=frame_count, total_number_of_exposures=number_of_exposures)

        _time.sleep(0.5)  # polling interval

    print(f"{bcolors.OKGREEN} > Exposures completed for {run_name_number}!{bcolors.ENDC}")
