import os, sys
from multiprocessing import Pool
from multiprocessing import Value, Lock
from pyhermes import empir


def main(run_folder, max_concurrent_jobs=5, verbose_level=0):
    sub_dirs = [f.path for f in os.scandir(run_folder) if f.is_dir()]
    photon_file_counter = Value('i', 0)
    photon_file_counter_lock = Lock()
    
    # Create a pool of workers to process the photon files
    # using a with() statement will close the pool when the work is done
    with Pool(max_concurrent_jobs) as pool:
        
        # Loop through the sub directories in the destination directory
        for sub_dir in sub_dirs:
            
            # Get the name of the sub directory
            sub_dir_name = os.path.basename(sub_dir)
            
            # Correct the path to the sub directory [because the dir name in the path twice!]
            #NOTE: need to get rid of this! Its only here because of the way the data is structured in the test data
            correct_path = os.path.join(sub_dir, sub_dir_name)
            
            # Check to see if the destination directory exists
            if not os.path.exists(correct_path):
                print(f"Destination directory does not exist: {correct_path}")
                print(f"Skipping directory: {correct_path}")
                continue
                
            else:        
                # Create an instance of the empirConfig class
                config_empir = empir.empirConfig(correct_path)
            
                # Check to if sub directories in the destination directory exists
                config_empir.check_or_create_sub_dirs()
            
                # Check for existing .photon files
                existing_photon_files = empir.check_for_files(config_empir.list_file_dir, '.empirphot', verbose_level)
            
                # Set the parameters for pixel_to_photon conversion
                config_empir.set_photon_to_event_params(d_space=2,d_time=15E-6,max_duration=100E-6)
            
                empir.process_existing_photon_files(config_empir, pool, photon_file_counter, photon_file_counter_lock)
    
        

        
    
if __name__ == "__main__":
    
    if len(sys.argv) < 2:
        print("Usage: python script.py <dest> <verbose_level>")
        print("\t<run_folder> is the destination directory for all sub-runs that contain raw tpx3 files")
        print("\t<verbose_level> is the level of verbosity for messaging during the execution process")
        sys.exit(1)
    elif len(sys.argv) < 3:
        run_folder = sys.argv[1]
        verbose_level = 0 
    else:
        run_folder = sys.argv[1]
        verbose_level = int(sys.argv[2])
    
    main(run_folder=run_folder, max_concurrent_jobs=5, verbose_level=verbose_level)