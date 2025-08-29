from HERMES.src.hermes.acquisition import serval
import json
from zaber_motion import Library, Units
from zaber_motion.ascii import Connection

verbos_level_loading = 0
verbos_level_logging = 0

run_settings_json = serval.config_run("./run_config.ini")   # load run settings
run_configs = json.loads(run_settings_json)                     # Parse the JSON to a Python dictionary for further use

# check the camera connection 
serval.check_camera_connection(run_configs['ServerConfig']['serverurl'],verbose=False)


# Loaded the needed parameters for the TPX3Cam
serval.load_dacs(run_configs,verbose_level=verbos_level_loading)                        # Load the dacs config based on dacs file in run_config
serval.load_pixelconfig(run_configs,verbose_level=verbos_level_loading)                 # Load pixelconfig based on file designated in run_config
serval.set_and_load_server_destination(run_configs,verbose_level=verbos_level_loading)  # Load the server destinations for data output
serval.set_and_load_detector_config(run_configs,verbose_level=verbos_level_loading)     # Set and load detector configuration data using run_config


# Create loop for CTScan

for rotation in range(0,360,2):
    #Create loop for taking data at each rotation.

    run_start = 0
    run_stop = run_start + 1
    for i in range(run_start,run_stop):
        
        #set your run name and run_number in run_configs
        run_configs["RunSettings"]["run_name"] = f"testing_{rotation:03}"
        run_configs["RunSettings"]["run_number"] = f"{i:04}"

        print(run_configs["RunSettings"]["run_name"] +_+ run_configs["RunSettings"]["run_number"] )

        # update server_destination with new file names
        serval.set_and_load_server_destination(run_configs,verbose_level=verbos_level_loading)  # Load the server destinations for data output
        
        # make sure to log all the corresponding configuration info of TPX3Cam
        serval.log_info(run_configs,http_string='/dashboard',verbose_level=verbos_level_logging)
        serval.log_info(run_configs,http_string='/server/destination',verbose_level=verbos_level_logging)   # Log the server destinations for data output
        serval.log_info(run_configs,http_string='/detector/health',verbose_level=verbos_level_logging)      # Logging the detector health info
        serval.log_info(run_configs,http_string='/detector/layout',verbose_level=verbos_level_logging)      # Logging the detector layout info
        serval.log_info(run_configs,http_string='/detector/config',verbose_level=verbos_level_logging)      # Logging the detector config info
        serval.log_info(run_configs,http_string='/detector/chips/0/dacs', verbose_level=verbos_level_logging)
        serval.log_info(run_configs,http_string='/detector/chips/0/pixelconfig', verbose_level=verbos_level_logging)

        # Start measurements
        serval.take_exposure(run_configs,verbose_level=1)


