from hermes.acquisition import tpx3serval
import sys
import json

# Setting levels of verbosness in what gets printed to terminal
initial_verbos_level_loading = 1 # 0 - 2
running_verbos_level_loading = 0 # 0 - 2
running_verbos_level_logging = 0 # 0 - 2

# Grab working dir from command line args.
if len(sys.argv) > 1:
    run_name = sys.argv[1]
else:
    print("Error: Please provide a run name as a command line argument.")
    sys.exit(1)

# Grab run settings from config file. 
run_settings_json = tpx3serval.config_run("./acquireTpx3.ini",run_name)   # load run settings
run_configs = json.loads(run_settings_json)                             # Parse the JSON to a Python dictionary for further use


# Check working dir and dir structure
tpx3serval.verify_working_dir(run_configs)

# Save configuration and server destination to init folder
tpx3serval.save_to_init(run_configs,http_string='/server/destination',verbose_level=running_verbos_level_logging)   # Log the server destinations for data output
tpx3serval.save_to_init(run_configs,http_string='/detector/config',verbose_level=running_verbos_level_logging)      # Logging the detector config info

# check the camera connection 
tpx3serval.check_camera_connection(run_configs['ServerConfig']['serverurl'],verbose=False)

# Loaded the needed parameters for the TPX3Cam
tpx3serval.load_dacs(run_configs,verbose_level=initial_verbos_level_loading)                        # Load the dacs config based on dacs file in run_config
tpx3serval.load_pixelconfig(run_configs,verbose_level=initial_verbos_level_loading)                 # Load pixelconfig based on file designated in run_config
tpx3serval.set_and_load_server_destination(run_configs,verbose_level=initial_verbos_level_loading)  # Load the server destinations for data output
tpx3serval.set_and_load_detector_config(run_configs,verbose_level=initial_verbos_level_loading)     # Set and load detector configuration data using run_config


run_start = 0
number_of_runs = int(run_configs["RunSettings"]["number_of_runs"]) # Gets the number of runs from run_configs
run_stop = run_start + number_of_runs
for i in range(run_start,run_stop):
          
    #set your run name and run_number in run_configs
    # run_configs["RunSettings"]["run_name"] = f"testing"
    run_configs["RunSettings"]["run_number"] = f"{i:04}"

    # update server_destination with new file names
    tpx3serval.set_and_load_server_destination(run_configs,verbose_level=running_verbos_level_loading)  # Load the server destinations for data output
    
    # make sure to log all the corresponding configuration info of TPX3Cam
    print(f"Logging configuration for run {run_configs['RunSettings']['run_number']} (dashboard, health, layout, DACs, pixelconfig)...")
    tpx3serval.log_info(run_configs,http_string='/dashboard',verbose_level=running_verbos_level_logging)
    tpx3serval.log_info(run_configs,http_string='/detector/health',verbose_level=running_verbos_level_logging)
    tpx3serval.log_info(run_configs,http_string='/detector/layout',verbose_level=running_verbos_level_logging)
    tpx3serval.log_info(run_configs,http_string='/detector/chips/0/dacs', verbose_level=running_verbos_level_logging)
    tpx3serval.log_info(run_configs,http_string='/detector/chips/0/pixelconfig', verbose_level=running_verbos_level_logging)

    # Start measurements
    tpx3serval.take_exposure(run_configs,verbose_level=1)