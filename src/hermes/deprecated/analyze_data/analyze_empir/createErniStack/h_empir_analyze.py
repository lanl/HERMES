#!/usr/bin/env python3
###############################################################
# This python script is adapted from the bash scripts of empir.
# It is meant to act as a monitor and process raw tpx3 files
# as they are created. It monitors data/[runName]/tpx3Files dir and
# calls empir_pixel2photon_tpx3spidr whenever a new file shows up.
#
# Dependencies:
# - watchdog: Install it using `pip install watchdog`
#
###############################################################

import os, sys
from multiprocessing import Pool
import threading
from multiprocessing import Value, Lock
from pyhermes import empir

#-------------------------------------------------------------------------------------
def main(dest, max_concurrent_jobs=5):
    global global_pool

    config_empir = empirConfig(dest)
    # Set parameters for pixel-to-photon processing
    config_empir.set_pixel_to_photon_params(d_space=10, d_time=1e-6, min_number=2, use_tdc1=True)      
    # Set parameters for photon-to-event processing
    config_empir.set_photon_to_event_params(d_space=3, d_time=100e-6, max_duration=500e-6)  
    # Set parameters for event-to-image processing
    config_empir.set_event_to_image_params(size_x=512, size_y=512, time_extTrigger=True, time_res_s=100E-6, time_limit=2000)
    
    global_pool = Pool(max_concurrent_jobs)

    # Shared counters and locks for processed files
    tpx3_file_counter = Value('i', 0)
    tpx3_file_counter_lock = Lock()
    list_file_counter = Value('i', 0)
    list_file_counter_lock = Lock()

    # Check for existing .tpx3 files
    existing_tpx3_files = [f for f in os.listdir(config_empir.tpx3_file_dir) if f.endswith(".tpx3.zip")]

    # Thread for processing existing tpx3 files
    if existing_tpx3_files:
        print(f"Found {len(existing_tpx3_files)} .tpx3 files in {config_empir.tpx3_file_dir}")
        process_existing_thread = threading.Thread(target=process_existing_tpx3_files, args=(config_empir, global_pool, tpx3_file_counter, tpx3_file_counter_lock))
        process_existing_thread.start()

    # Threads for monitoring tpx3 and list files
    tpx3_monitor_thread = threading.Thread(target=monitor_tpx3_files, args=(config_empir, tpx3_file_counter, tpx3_file_counter_lock))
    list_monitor_thread = threading.Thread(target=monitor_list_files, args=(config_empir, list_file_counter, list_file_counter_lock))
    tpx3_monitor_thread.start()
    list_monitor_thread.start()

    # Wait for all threads to complete
    if existing_tpx3_files:
        process_existing_thread.join()
    tpx3_monitor_thread.join()
    list_monitor_thread.join()

    # Print the final count of processed files
    print(f"Processed {tpx3_file_counter.value} tpx3 files and {list_file_counter.value} list files in total.")

    global_pool.close()
    global_pool.join()
    
    # Process .event files into a final image.
    

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <dest>")
        sys.exit(1)

    dest = sys.argv[1]
    main(dest, max_concurrent_jobs=50)
