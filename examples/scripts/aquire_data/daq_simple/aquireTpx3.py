from hermes.acquisition import tpx3serval
import sys, time
import json
import epics

# Setting levels of verbosness in what gets printed to terminal
initial_verbos_level_loading = 1
running_verbos_level_loading = 0
running_verbos_level_logging = 0

# Grab working dir from command line args.
if len(sys.argv) > 1:
    run_name = sys.argv[1]
else:
    print("Error: Please provide the working directory as a command line argument.")
    sys.exit(1)

# Grab run settings from config file. 
run_settings_json = tpx3serval.config_run("./aquireTpx3.ini",run_name)   # load run settings
run_configs = json.loads(run_settings_json)                             # Parse the JSON to a Python dictionary for further use

# Check working dir and dir structure
tpx3serval.verify_working_dir(run_configs)

# check the camera connection 
tpx3serval.check_camera_connection(run_configs['ServerConfig']['serverurl'],verbose=False)

# Loaded the needed parameters for the TPX3Cam
tpx3serval.load_dacs(run_configs,verbose_level=initial_verbos_level_loading)                        # Load the dacs config based on dacs file in run_config
tpx3serval.load_pixelconfig(run_configs,verbose_level=initial_verbos_level_loading)                 # Load pixelconfig based on file designated in run_config
tpx3serval.set_and_load_server_destination(run_configs,verbose_level=initial_verbos_level_loading)  # Load the server destinations for data output
tpx3serval.set_and_load_detector_config(run_configs,verbose_level=initial_verbos_level_loading)     # Set and load detector configuration data using run_config

run_start = 10
number_of_runs = 30
run_stop = run_start + number_of_runs
for i in range(run_start,run_stop):
    
    beam_current = float(epics.caget('1LCM000D01',as_string=True))
    
    # using while loop to stall if beam is down.
    beam_current_limit = 60
    while beam_current <= beam_current_limit:
        print(f"beam current of {beam_current} is less than {beam_current_limit}")
        print("waiting 60 seconds.")
        time.sleep(60)
        beam_current = float(epics.caget('1LCM000D01',as_string=True))
        print("Checking beam: {}".format(beam_current))
    
    #set your run name and run_number in run_configs
    run_configs["RunSettings"]["run_name"] = f"openbeam"
    run_configs["RunSettings"]["run_number"] = f"{i:04}"

    # update server_destination with new file names
    tpx3serval.set_and_load_server_destination(run_configs,verbose_level=running_verbos_level_loading)  # Load the server destinations for data output
    
    # make sure to log all the corresponding configuration info of TPX3Cam
    tpx3serval.log_info(run_configs,http_string='/dashboard',verbose_level=running_verbos_level_logging)
    tpx3serval.log_info(run_configs,http_string='/server/destination',verbose_level=running_verbos_level_logging)   # Log the server destinations for data output
    tpx3serval.log_info(run_configs,http_string='/detector/health',verbose_level=running_verbos_level_logging)      # Logging the detector health info
    tpx3serval.log_info(run_configs,http_string='/detector/layout',verbose_level=running_verbos_level_logging)      # Logging the detector layout info
    tpx3serval.log_info(run_configs,http_string='/detector/config',verbose_level=running_verbos_level_logging)      # Logging the detector config info
    tpx3serval.log_info(run_configs,http_string='/detector/chips/0/dacs', verbose_level=running_verbos_level_logging)
    tpx3serval.log_info(run_configs,http_string='/detector/chips/0/pixelconfig', verbose_level=running_verbos_level_logging)

    # Start measurements
    tpx3serval.take_exposure(run_configs,verbose_level=1)

