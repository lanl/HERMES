import os, sys
from multiprocessing import Pool
import threading
from multiprocessing import Value, Lock
from pyhermes import empir

#-------------------------------------------------------------------------------------
def main(dest, max_concurrent_jobs=5):
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
    existing_tpx3_files = [f for f in os.listdir(config_empir.tpx3_file_dir) if f.endswith(".tpx3")]
    

    # Thread for exporting tpx3 files
    if existing_tpx3_files:
        #print(existing_tpx3_files)
        process_existing_thread = threading.Thread(target=empir.unpack_pixel_activations, args=(config_empir, global_pool, tpx3_file_counter, tpx3_file_counter_lock))
        process_existing_thread.start()




if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <dest>, where <dest> is the destination directory for the raw tpx3 files.")
        sys.exit(1)

    dest = sys.argv[1]
    main(dest, max_concurrent_jobs=5)
