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
    
    # Set the global pool for concurrent jobs    
    global_pool = Pool(max_concurrent_jobs)
    
    # Shared counters and locks for processed files
    tpx3_file_counter = Value('i', 0)
    tpx3_file_counter_lock = Lock()
    
    # Check for existing .tpx3 files
    existing_tpx3_files = empir.check_for_files(config_empir.tpx3_file_dir, '.tpx3', verbose_level)
    
    # Set the parameters for pixel_to_photon conversion
    config_empir.set_pixel_to_photon_params(d_space=5,d_time=5E-8,min_number=2,use_tdc1=True)
    
    
    # Thread for exporting tpx3 files
    if existing_tpx3_files:
        process_existing_thread = threading.Thread(target=empir.process_existing_tpx3_files, args=(config_empir, global_pool, tpx3_file_counter, tpx3_file_counter_lock))
        process_existing_thread.start()
    
    
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
        verbose_level = sys.argv[2]
    
    main(dest, max_concurrent_jobs=5, verbose_level=verbose_level)
