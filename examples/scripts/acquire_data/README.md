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

This folder contains acquireTpx3.py, which is a python script to run acquisition based on user input and a configuration file. Below is the structure of the config file, each parameter that can be changed, and what they do. 

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


## CLI Functionality

The CLI is used to give users a way to adjust parameters quickly in the terminal without adjusting an external file. 

Overview:

To see all available options, run 'python acquireTpx3.py --help' or 'python acquireTpx3.py -h'.


- No config file is required by default.  
- Built-in defaults are included in the script.  
- Users can:
  1. Use defaults as-is.
  2. Load a config file with -c or --config.
  3. Override defaults and/or config file values using CLI flags.

This makes experiments easier to run and automate.

Default Behavior:

If no config file is provided, the script will use built-in defaults.
Example:
python acquireTpx3.py

Defaults include:
- trigger_period_in_seconds = 10
- exposure_time_in_seconds = 9
- number_of_runs = 1

Note: You will need to override at least the working directory path using -W or provide a config file. A config file is recommended for setting server destinations. 

The Working directory will be the directory where a folder is created with the folder name defined by '-r' or '--run-name'. 
This will be our run directory, and will contain `imageFiles`, `initFiles`, `previewFiles`, `rawSignalFiles`, `statusFiles`, `tpx3Files` and `tpx3Logs`.


You can load a config file for overrides:
python acquireTpx3.py -c acquireTpx3.ini

Values from the config file will replace defaults.
CLI flags will still take highest precedence.

CLI Flags:

You can override parameters directly with CLI flags:

- -c, --config: Load config file  
- -W, --working-dir: Set working directory path  
- -r, --run-name: Name for the run (used in output filenames)  
- -N, --run-number: Starting run number (integer, zero-padded as 0000)  
- -n, --num-runs: Total number of runs to perform  
- -t, --trigger-period: Trigger period in seconds  
- -e, --exposure: Exposure time in seconds  
- -T, --num-triggers: Number of triggers per run  
- -u, --server-url: URL for TPX3 server (default: http://localhost:8080)  
- -v, --verbose: Verbosity: 0=quiet, 1=info, 2=debug  
- --dry-run: Print the merged configuration and exit without running  

Verbosity Levels:

- v 0: Quiet mode (only errors are printed)
- v 1: Standard info (start/end messages, number of runs)
- v 2: Debug mode (prints full merged configuration and detailed debug logs)


Dry Run Mode:

Use --dry-run to print the final merged configuration (defaults + config file + CLI) without touching the hardware:
Example:
python acquireTpx3.py --dry-run -c acquireTpx3.ini -n 5 -r test_run

Example output:
=== Effective Configuration (dry run) ===
{
  "WorkingDir": { ... },
  "ServerConfig": { ... },
  "RunSettings": {
    "run_name": "test_run",
    "number_of_runs": 5,
    ...
  }
}
=========================================

Examples:

1. Use defaults and specify working directory:
python acquireTpx3.py -W /data/acquisition_test


2. Load config file and override exposure time:
python acquireTpx3.py -c acquireTpx3.ini -e 5


3. Run with custom working directory, run name, and number of runs:
python acquireTpx3.py -W /data/beam_test -r beam_2025 -n 10


4. Load config file, change exposure, trigger period, and number of triggers:
python acquireTpx3.py -c acquireTpx3.ini -e 7 -t 12 -T 25


5. Full example using almost all parameters and options:
python acquireTpx3.py -c acquireTpx3.ini -W /data/full_test -r complex_run -N 5 -n 8 -t 15 -e 12 -T 30 -v 2 \


Parameter Precedence:

1. CLI flags (highest priority)
2. Config file (-c)
3. Built-in defaults (lowest priority)

Acquisition Flow:

Once configuration is finalized, the script:
1. Verifies or creates the working directory structure.
2. Checks TPX3 camera connection.
3. For each run:
   - Increments and formats run_number.
   - Logs detector settings.
   - Starts exposure using configured parameters.

See serval manual for information on how server config works and how camera acquires data through dashboard. 
