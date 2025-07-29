# HERMES Examples for TPX3 Data Acquisition

This repository contains examples demonstrating the use of HERMES for setting up and acquiring data using TPX3Cam and SPIDR readout boards. The primary Python library for data acquisition with HERMES is `tpx3serval.py`.

## Getting Started

To use these examples, first ensure you have the HERMES system and the necessary hardware components set up. You will need TPX3Cam and SPIDR readout boards configured and connected to your system. Please see the ASI TPX3Cam manual for hardware setup and connections. 

Additionaly we suggest using a directory structure adopted and adjusted from EMPIR. There are built-in functions in tpx3serval that will create the `[run_N]` directory and its sub-directories. Please make sure that the python scripts used to aquire data are located in the scripts folder of your working directory. 

```
Working Directory
├── README.md
├── scripts
    └── acquire_python_script.py
    └── acquire_config.ini
├── initFiles
├── [run_1]
    ├── imageFiles
    ├── previewFiles
    ├── statusFiles
    ├── tpx3Files
    ├── tpx3Logs
├── [run_2]
    ├── imageFiles
    ├── previewFiles
    ├── statusFiles
    ├── tpx3Files
    ├── tpx3Logs
├── [run_3]
├── [run_N]
```

For all of the data aquisition examples, the main python library used within hermes is `tpx3serval.py`. It can be loaded using the following:

```python
from pyhermes import tpx3serval
```

### Prerequisites

List any prerequisites or dependencies required for running the examples, such as Python versions, libraries, or other software.

### Installation

# 1. daq_simple/ #
This example illustrated a simple python script, acquireTpx.py, to first initiate and configure a TPX3Cam setup, and then take "n" exposures using functions from the tpx3serval library (located in pyhermes). Initial camera and needed DAQ configurations are stored in the config file: "acquireTpx3.ini".   

```bash
py acquireTpx.py example_folder
```

This will load acquireTpx3.ini and create a folder named `example_folder`. This will be our run directory, and will contain `imageFiles`, `initFiles`, `previewFiles`, `rawSignalFiles`, `statusFiles`, `tpx3Files` and `tpx3Logs`. 

Below is the definition for each parameter used in the acquireTpx3.ini file: 

[WorkingDir]
`path_to_working_dir`: File path to working directory. Should be changed from default.
`path_to_init_files`: File path to init files. Generally, should not be changed. 
`path_to_status_files`: File path to status files. Generally, should not be changed. 
`path_to_rawSignal_files `: File path to .rawSignals files. Generally, should not be changed. 
`path_to_log_files`: File path to log files. Generally, should not be changed. 
`path_to_image_files`: File path to image files. Generally, should not be changed. 
`path_to_preview_files`: File path to preview files. Generally, should not be changed. 
`path_to_raw_files`: File path to raw .tpx3 files. Generally, should not be changed. 


[ServerConfig]
`serverurl` = http://localhost:8080      
`path_to_server` = [PATH/TO/TPX3/SERVAL]
`path_to_server_config_files` = [/PATH/TO/CAMERASETTINGS/FROM/SERVAL/DIR]
`bpc_file_name` = settings.bpc
`dac_file_name` = settings.bpc.dacs
`destinations_file_name` = initial_server_destinations.json
`detector_config_file_name` = initial_detector_config.json


[RunSettings]
`run_name`: Name of the run. file will appear in `example_folder` as `[run_name]_[run_number]_[timestamp]_[trigger_number].tpx3`.
`run_number`: Number of first run. Generally starts at 0000 and increments `run_number` for each run.
`trigger_period_in_seconds`: Trigger period of camera. 
`exposure_time_in_seconds`: Exposure time of camera. Must be less than trigger period. 
`trigger_delay_in_seconds`: Delay between triggers. Generally set to 0. 
`number_of_triggers`: Number of triggers during a single run. Will increment `trigger_number`
`number_of_runs`: Total number of runs to perform. 
`global_timestamp_interval_in_seconds`
