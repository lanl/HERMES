import os, sys
from multiprocessing import Pool
import threading
from multiprocessing import Value, Lock
from pyhermes import empir


def main(dest, max_concurrent_jobs=5, verbose_level=0):
    # Check to see if the destination directory exists
    if not os.path.exists(dest):
        print(f"Destination directory does not exist: {dest}")
        sys.exit(1)
        
    else:
        print(f"Unpacking tpx3 files in directory: {dest}")

    # Create an instance of the empirConfig class
    config_empir = empir.empirConfig(dest)

    # Check to if sub directories in the destination directory exists
    config_empir.check_or_create_sub_dirs()
    
    # Shared counters and locks for processed files
    photon_file_counter = Value('i', 0)
    photon_file_counter_lock = Lock()
    
    # Create a pool of workers to process the photon files
    # using a with() statement will close the pool when the work is done
    with Pool(max_concurrent_jobs) as pool:    
        
        # Check to see if the destination directory exists
        if not os.path.exists(dest):
            print(f"Destination directory does not exist: {dest}")
            print(f"Skipping directory: {dest}")
            sys.exit(1)
            
        else:        
            # Create an instance of the empirConfig class
            config_empir = empir.empirConfig(dest)
        
            # Check to if sub directories in the destination directory exists
            config_empir.check_or_create_sub_dirs()
        
            # Check for existing .photon files
            existing_photon_files = empir.check_for_files(config_empir.list_file_dir, '.empirphot', verbose_level)
        
            # Set the parameters for pixel_to_photon conversion
            config_empir.set_photon_to_event_params(d_space=2,d_time=15E-6,max_duration=100E-6)
        
            empir.process_existing_photon_files(config_empir, pool, photon_file_counter, photon_file_counter_lock)
    
    
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <dest> <verbose_level>,")
        print("\t<dest> is the destination directory for the raw tpx3 files")
        print("\t<verbose_level> is the level of verbosity for messaging during the execution process")
        sys.exit(1)
    elif len(sys.argv) < 3:
        dest = sys.argv[1]
        verbose_level = 0 
    else:
        dest = sys.argv[1]
        verbose_level = int(sys.argv[2])
    
    main(dest, max_concurrent_jobs=5, verbose_level=verbose_level)
