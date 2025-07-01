import sys, os, pathlib
import json
import requests
import matplotlib.pyplot as plt
import configparser
import time
from datetime import datetime

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
# Configuring functions
#--------------------------------------------------------------
def verify_working_dir(run_configs):
    """ Verifies the working directory and its sub-directories exist. If they do not exist, they are created.

    Args:
        run_configs (str): run configuration.
    """
    
    working_dir = run_configs["WorkingDir"]['path_to_working_dir']                      # Experiment directory 
    run_dir = working_dir + run_configs["WorkingDir"]['run_dir_name']                   # Setting the parent dir for the run
    raw_file_dir = run_dir + run_configs["WorkingDir"]['path_to_raw_files']             # Setting the path for the tpx3 files
    image_file_dir = run_dir + run_configs["WorkingDir"]['path_to_image_files']         # Setting the path for image files
    preview_file_dir = run_dir + run_configs["WorkingDir"]['path_to_preview_files']     # Setting path for preview files
    tpx3_log_files_dir = run_dir + run_configs["WorkingDir"]['path_to_log_files']       # Setting path for tpx3 log files
    status_files_dir = run_dir + run_configs["WorkingDir"]['path_to_status_files']      # Setting path for status files

    print("Verifying dir:f{run_dir} and its sub-dirs")
    # List of directories to check and create if they don't exist
    directories = [run_dir, raw_file_dir, image_file_dir, preview_file_dir, tpx3_log_files_dir, status_files_dir]

    for dir in directories:
        if not os.path.exists(dir):
            os.makedirs(dir)
            print(f"Creating directory: {dir}")
        else:
            print(f"Directory already exists: {dir}")

# Updated function to handle newer configuration options in run_config.ini
def config_run(config_file='run_config.ini',run_name="dummy"):
    """ Configures the run settings based on the run_config.ini file.

    Args:
        config_file (str, optional): Run configuration file. Defaults to 'run_config.ini'.
        run_name (str, optional): Name of the run. Defaults to "dummy".

    Returns:
        _type_: _description_
    """
    # Initialize ConfigParser
    config = configparser.ConfigParser()
    
    # Read run_config.ini file
    config.read(config_file)
    
    # Function to check and get path
    def check_and_get_path(section, key):
        path = config.get(section, key, fallback=None)
        print(path)
        while path is None or not os.path.exists(path):
            print(f"{key} is not set or does not exist.")
            path = input(f"Please enter a valid path for {key}: ")
            if os.path.exists(path):
                config.set(section, key, path)
            else:
                print("The entered path does not exist. Please try again.")
                path = None
        return path
    
    # Ensure the necessary sections exist
    for section in ['WorkingDir', 'RunSettings', 'ServerConfig']:
        if section not in config.sections():
            config.add_section(section)
        
    # Create a nested dictionary to hold the settings
    settings_dict = {

        'WorkingDir': {
            'path_to_working_dir': config.get('WorkingDir', 'path_to_working_dir', fallback="./"),
            'path_to_init_files': config.get('WorkingDir', 'path_to_init_files', fallback="initFiles/"),
            'run_dir_name': f"{run_name}/",
            'path_to_status_files': config.get('WorkingDir', 'path_to_status_files', fallback="statusFiles/"),
            'path_to_log_files': config.get('WorkingDir', 'path_to_log_files', fallback="tpx3Logs/"),
            'path_to_image_files': config.get('WorkingDir', 'path_to_image_files', fallback="imageFiles/"),
            'path_to_preview_files': config.get('WorkingDir', 'path_to_preview_files', fallback="previewFiles/"),
            'path_to_raw_files': config.get('WorkingDir', 'path_to_raw_files', fallback="tpx3Files/")
        },
        'ServerConfig': {
            'serverurl': config.get('ServerConfig', 'serverurl', fallback=None),
            'path_to_server': config.get('ServerConfig', 'path_to_server', fallback=None),
            'path_to_server_config_files': config.get('ServerConfig', 'path_to_server_config_files', fallback=None),
            'destinations_file_name': config.get('ServerConfig', 'destinations_file_name', fallback=None),
            'detector_config_file_name': config.get('ServerConfig', 'detector_config_file_name', fallback=None),
            'bpc_file_name': config.get('ServerConfig', 'bpc_file_name', fallback=None),
            'dac_file_name': config.get('ServerConfig', 'dac_file_name', fallback=None)
        },
        'RunSettings': {
            'run_name': config.get('RunSettings', 'run_name', fallback='you_forgot_to_name_the_runs'),
            'run_number': config.get('RunSettings', 'run_number', fallback=0),
            'trigger_period_in_seconds': config.get('RunSettings', 'trigger_period_in_seconds', fallback=1.0),
            'exposure_time_in_seconds': config.get('RunSettings', 'exposure_time_in_seconds', fallback=0.5),
            'trigger_delay_in_seconds': config.get('RunSettings', 'trigger_delay_in_seconds', fallback=0.0),
            'number_of_triggers': config.get('RunSettings', 'number_of_triggers', fallback=0),
            'global_timestamp_interval_in_seconds': config.get('RunSettings', 'global_timestamp_interval_in_seconds', fallback=0.0)
        }
    }

    
    # Convert the dictionary to a JSON structure
    settings_json = json.dumps(settings_dict, indent=4)
    
    return settings_json



#--------------------------------------------------------------



###############################################################
# Loading functions
#--------------------------------------------------------------

def load_json_file(file_path):
    """
    Load a JSON file into a Python dictionary.

    Parameters:
        file_path (str): The path to the JSON file.

    Returns:
        dict: A dictionary containing the JSON data.
        None: If an error occurs (e.g., file not found, invalid JSON).
    """
    try:
        with open(file_path, 'r') as f:
            json_data = json.load(f)
        return json_data
    except FileNotFoundError:
        print(f"The specified file was not found.")
        return None
    except json.JSONDecodeError:
        print(f"Failed to decode the JSON file.")
        return None


def save_json_to_file(data, filename):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)


def load_dacfile_to_json(file_path, verbose_level = 0):
    """_summary_

    Args:
        file_path (_type_): _description_

    Returns:
        _type_: _description_
    """
    dacs = {}
    try:
        with open(file_path, 'r') as f:
            for line in f.readlines():
                line = line.strip()  # Remove leading/trailing whitespace
                
                # Skip lines that don't contain key-value pairs
                if not line or line.startswith('['):
                    continue
                
                # Split the line into key and value parts
                key, value = line.split(':')
                
                # Add the key-value pair to the dictionary
                dacs[key] = int(value)  # Assuming all values are integers
                
        return dacs
    except FileNotFoundError:
        print(f"The specified file was not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def set_and_load_server_destination(run_configs, verbose_level = 0):
    
    # Setting up paths and names for initial dummy destinations config file
    working_dir = run_configs["WorkingDir"]['path_to_working_dir']
    init_dest_file_path = working_dir + run_configs["WorkingDir"]['path_to_init_files']
    init_dest_file_name = run_configs["ServerConfig"]['destinations_file_name']
    
    run_dir = working_dir + run_configs["WorkingDir"]['run_dir_name']                       # Setting the parent dir for the run
    raw_file_dir = run_dir + run_configs["WorkingDir"]['path_to_raw_files']             # Setting the path for the tpx3 files
    image_file_dir = run_dir + run_configs["WorkingDir"]['path_to_image_files']         # Setting the path for image files
    preview_file_dir = run_dir + run_configs["WorkingDir"]['path_to_preview_files']     # Setting path for preview files
    
    # Loading in json data
    path_to_json_file = init_dest_file_path + init_dest_file_name
    destination_json_data = load_json_file(path_to_json_file)
    if verbose_level >= 1:
        print_header_line_block()
        print(f"Loading destination json file from:")
        print(path_to_json_file)
        if verbose_level >=2:
            print(destination_json_data)
    
    
    # Adjusting paths to match paths in config file or new run info
    if verbose_level >= 1:
        print(f"Updating destinations in json structure based on run config file")
        if verbose_level >= 2:
            print(f"Dir for tpx3 files: {raw_file_dir}")
            print(f"Dir for image files: {image_file_dir}")
            print(f"Dir for preview files: {preview_file_dir}")
            
    destination_json_data['Raw'][0]['Base'] = "file:"+ raw_file_dir
    destination_json_data['Raw'][0]['FilePattern'] = run_configs["RunSettings"]['run_name'] + "_" + run_configs["RunSettings"]['run_number'] + "_%MdHms_"
    
    destination_json_data['Image'][0]['Base'] = "file:"+ image_file_dir
    destination_json_data['Image'][0]['FilePattern'] = "ToT_"+run_configs["RunSettings"]['run_name'] + "_" + run_configs["RunSettings"]['run_number'] + "_%MdHms_"
    
    for channel in destination_json_data['Preview']['ImageChannels']:
        channel['Base'] = "file:"+ preview_file_dir
        channel['FilePattern'] = run_configs["RunSettings"]['run_name'] + "_" + run_configs["RunSettings"]['run_number'] + "_%MdHms_"
    
    # Loading json data into camara
    destination_set_response = requests.put(url=run_configs['ServerConfig']['serverurl']+'/server/destination', data=json.dumps(destination_json_data))
    destination_set_data = destination_set_response.text.strip("\n")
    if verbose_level >= 1:
        print(f'{bcolors.OKGREEN}Response: {destination_set_data}{bcolors.ENDC}')
        print_closing_line_block()
    
    
def set_and_load_detector_config(run_configs, verbose_level = 0):
    
    # Setting up paths and names for initial dummy destinations config file
    working_dir = run_configs["WorkingDir"]['path_to_working_dir']
    init_config_file_dir = working_dir + run_configs["WorkingDir"]['path_to_init_files']
    init_config_file_name = run_configs["ServerConfig"]['detector_config_file_name']
    
    # Loading in json data
    path_to_json_file = init_config_file_dir + init_config_file_name
    detector_config_json_data = load_json_file(path_to_json_file)
    if verbose_level >=1:
        print_header_line_block()
        print(f"Loading detector config json file from:")
        print(path_to_json_file)
        if verbose_level >=2:
            print(detector_config_json_data)
    
    # Adjusting detector config parameters that are in config file
    if verbose_level >= 1:
        print(f"Updating detector config parameters in json structure based on run config file")
    detector_config_json_data['TriggerPeriod'] = run_configs['RunSettings']['trigger_period_in_seconds']
    detector_config_json_data['TriggerDelay'] = run_configs['RunSettings']['trigger_delay_in_seconds']
    detector_config_json_data['ExposureTime'] = run_configs['RunSettings']['exposure_time_in_seconds']
    detector_config_json_data['nTriggers'] = run_configs['RunSettings']['number_of_triggers']
    detector_config_json_data['GlobalTimestampInterval'] = run_configs['RunSettings']['global_timestamp_interval_in_seconds']
    
    # Loading json data into camara
    detector_config_set_response = requests.put(url=run_configs['ServerConfig']['serverurl']+'/detector/config', data=json.dumps(detector_config_json_data))
    detector_config_set_data = detector_config_set_response.text.strip("\n")
    if verbose_level >= 1:
        print(f'{bcolors.OKGREEN}Response: {detector_config_set_data}{bcolors.ENDC}')
        print_closing_line_block()


def load_dacs(run_configs, verbose_level = 0):

    # Loading in json data
    path_to_json_file = run_configs["ServerConfig"]['path_to_server']+run_configs["ServerConfig"]['path_to_server_config_files']+run_configs['ServerConfig']['dac_file_name']
    dacs_json_data = load_dacfile_to_json(path_to_json_file)
    
    if verbose_level >=1:
        print_header_line_block()
        print(f"Loading dacs file from:")
        print(path_to_json_file)
        if verbose_level >= 2:
            print(dacs_json_data)
    
    dacs_set_response = requests.put(url=run_configs['ServerConfig']['serverurl'] + '/detector/chips/0/dacs', data=json.dumps(dacs_json_data))
    dacs_set_data = dacs_set_response.text.strip("\n")
    
    if verbose_level >=1:
        print(f'{bcolors.OKGREEN}Response: {dacs_set_data}{bcolors.ENDC}')
        print_closing_line_block()


def load_pixelconfig(run_configs, verbose_level = 0):

    # Loading in bpc file into binary object
    bpc_file_location = run_configs["ServerConfig"]['path_to_server']+run_configs["ServerConfig"]['path_to_server_config_files']+run_configs['ServerConfig']['bpc_file_name']
    bpc_file = open(bpc_file_location,'rb')
    bpc_binary_data = bpc_file.read()
    if verbose_level >=1:
        print_header_line_block()
        print(f"Loading pixelconfig file from:")
        print(bpc_file_location)
    
    # Loading bpc binary into the TPX3Cam
    bpc_set_response = requests.put(url=run_configs['ServerConfig']['serverurl'] + '/detector/chips/0/pixelconfig?format=bpc', data=bpc_binary_data)
    bpc_set_data = bpc_set_response.text.strip("\n")
    if verbose_level >=1:
        print(f'{bcolors.OKGREEN}Response: {bpc_set_data}{bcolors.ENDC}')
        print_closing_line_block()

#--------------------------------------------------------------


###############################################################
# Verification functions
#--------------------------------------------------------------
 
def check_request_status(status_code,verbose=False):
    """

    Args:
        status_code (_type_): _description_
    """
    
    # Example usage
    # check_request_status(200)  # This will print "OK: The request has succeeded."
    # check_request_status(404)  # This will print "Error: Not Found: The server has not found anything matching the request." and exit the program.

    if status_code == 200:
        if verbose:
            print(f"{bcolors.OKGREEN}OK: The request has succeeded.{bcolors.ENDC}")
        status=True
    else:
        if status_code == 204:
            error_message = "No Content: The server has fulfilled the request, but there is no new information to send back."
        elif status_code == 302:
            error_message = "Moved Temporarily: The server redirects the request."
        elif status_code == 400:
            error_message = "Bad Request: The request had bad syntax or was impossible to fulfill."
        elif status_code == 401:
            error_message = "Unauthorized: The request requires user authentication, or the authorization has been refused."
        elif status_code == 404:
            error_message = "Not Found: The server has not found anything matching the request."
        elif status_code == 409:
            error_message = "Conflict: The request could not be completed due to a conflict."
        elif status_code == 500:
            error_message = "Internal Error: The server encountered an unexpected condition."
        elif status_code == 503:
            error_message = "Service Unavailable: The server is unable to handle the request due to temporary overload."
        else:
            error_message = f"Received unhandled status code: {status_code}"
        if verbose:
            print(f"{bcolors.FAIL}Error: {error_message}{bcolors.ENDC}")
        status = False
        
    return status 

    
def check_camera_connection(server_url,verbose=False):
    """ Checks connection to TPX3Cam with user defined url
        It is usually http://localhost:8080 
    Args:
        server_url (string): address for sending TCP/IP commands to the TPX3Cam 
        verbose (bool, optional): verbose level for printing and debugging. Defaults to False.
    """
    if verbose==True:
        print_header_line_block()
        print("Connecting to Camera at {}".format(server_url))
        
    request_status = requests.get(url=server_url)
    status = check_request_status(request_status.status_code,verbose)
    
    if verbose ==True:
        if status == False:
            print(f"{bcolors.FAIL}Could not connect to Camera at {bcolors.ENDC}{server_url}")
            print_closing_line_block()
            sys.exit(1)  # Exit the program with a non-zero exit code to indicate an error
        else:
            print(f"{bcolors.OKGREEN}Succesfully connected to Camera at {bcolors.ENDC}{server_url}")
            print_closing_line_block()

#--------------------------------------------------------------


###############################################################
# Logging functions
#--------------------------------------------------------------

def log_info(run_config,http_string,verbose_level=0):
    # creating output file names and paths
    output_json_name = http_string.replace("/", "_")+".json"
    working_dir = run_config["WorkingDir"]['path_to_working_dir']
    run_dir = working_dir + run_config["WorkingDir"]['run_dir_name']    
    path_to_tpx3_log_dir = run_dir + run_config['WorkingDir']['path_to_log_files']
    output_json_file = path_to_tpx3_log_dir + run_config['RunSettings']['run_name'] + "_" + run_config['RunSettings']['run_number'] + output_json_name
    
    if verbose_level >= 1:
        print_header_line_block()
        print(f"Logging {http_string} info at: ")
        print(output_json_file)
    
    server_get_response = requests.get(url=run_config['ServerConfig']['serverurl'] + http_string)
    if verbose_level >=2:
        print(server_get_response)
    server_get_data = json.loads(server_get_response.text)
    save_json_to_file(server_get_data,output_json_file)
    
    if verbose_level >= 1:
        print_closing_line_block()



###############################################################
# DAQ functions
#--------------------------------------------------------------
def print_status_bar(elapsed_time, expected_time_left, exposure_time, pixel_rate, tdc1_rate, frame_count, total_number_of_exposures):
    
    # Calculating some times and frams numbers to display
    current_frame = frame_count+1
    total_time = exposure_time*total_number_of_exposures
    if expected_time_left == 0:
        time_left = 0
    else:
        time_left = expected_time_left-elapsed_time%exposure_time
    
    # Calculate the percentage of completion
    progress = min(100, int((elapsed_time / total_time) * 100))

    # Create a status bar string
    status_bar = f"[{'#' * (progress // 2)}{' ' * (50 - progress // 2)}] {progress}%"
    status_bar += f" Elapsed Time: {elapsed_time:.2f} s, "
    status_bar += f"Expected Time Left: {time_left:.2f} s, "
    status_bar += f"Pixel Rate: {pixel_rate} hps, "
    status_bar += f"TDC1 Rate: {tdc1_rate} tps, "
    status_bar += f"Frame: {current_frame} of {total_number_of_exposures}"

    # Clear the previous line and print the updated status bar
    sys.stdout.write("\033[K")  # Clear line
    sys.stdout.write(status_bar)
    sys.stdout.flush()
    sys.stdout.write("\r")  # Move cursor to the beginning of the line

def make_user_wait(measurement_info):
    if (measurement_info["Measurement"]["Status"] != "DA_IDLE"):
        elapsed_time = measurement_info["Measurement"]["ElapsedTime"]
        time_left = measurement_info["Measurement"]["TimeLeft"]
        print(f"Waiting for previous aquisition to finish.")
        print(f"Previous measurement started {elapsed_time} ago and has {time_left} second left")
        print(f"Waiting for {time_left} seconds...")
        time.sleep(time_left)


def take_exposure(run_config_struct,verbose_level=0):
    
    # Create run handle (name and number)
    run_name_number = run_config_struct['RunSettings']['run_name']+"_"+run_config_struct['RunSettings']['run_number']
    number_of_exposures = int(run_config_struct['RunSettings']['number_of_triggers'])
    exposure_time = float(run_config_struct['RunSettings']['exposure_time_in_seconds'])
    total_expected_time = exposure_time*number_of_exposures
    
    # Check to see if data aquisition is running.    
    while True:
        dashboard_response = requests.get(url=run_config_struct['ServerConfig']['serverurl'] + '/dashboard')
        dashboard_data = json.loads(dashboard_response.text)
        if dashboard_data["Measurement"] == None:
            break
        elif dashboard_data["Measurement"]["Status"] == "DA_RECORDING":
            make_user_wait(dashboard_data)
        else:
            break
        
    # Check to see if data aquisition is running.
    dashboard_response = requests.get(url=run_config_struct['ServerConfig']['serverurl'] + '/dashboard')
    dashboard_data = json.loads(dashboard_response.text)
        
    if verbose_level >= 1:
        print_header_line_block()
        print(f"Requesting to start measurement: {run_name_number}")
        
    resp = requests.get(url=run_config_struct['ServerConfig']['serverurl'] + '/measurement/start')
    check_request_status(resp.status_code, verbose=True)
    
    while True:
        dashboard_response = requests.get(url=run_config_struct['ServerConfig']['serverurl'] + '/dashboard')
        dashboard_data = json.loads(dashboard_response.text)
        #print(dashboard_data["Measurement"])
        
        if dashboard_data["Measurement"]["Status"] == "DA_RECORDING":
            elapsed_time = dashboard_data["Measurement"]["ElapsedTime"]
            pixel_rate = dashboard_data["Measurement"]["PixelEventRate"]
            tdc1_rate = dashboard_data["Measurement"]["TdcEventRate"]
            frame_count = dashboard_data["Measurement"]["FrameCount"]
            time_left = dashboard_data["Measurement"]["TimeLeft"]
            
            print_status_bar(elapsed_time, time_left, exposure_time, pixel_rate, tdc1_rate, frame_count, number_of_exposures)
            time.sleep(.5)  # Update the status bar every second
        else:
            break

    print(f"{bcolors.OKGREEN} > Exposures completed for {run_name_number}!{bcolors.ENDC}")
    
