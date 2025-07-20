import os, subprocess, shutil
from hermes.empir.models import PhotonToEventParams, EventToImageParams, DirectoryStructure
from hermes.empir.logger import empir_logger as logger


class EmpirRunner:
    """A class for running EMPIR processing steps."""
    
    def __init__(self):
        """Initialize and check for required EMPIR binaries."""
        self._check_for_empir_binaries()
    
    def _check_for_empir_binaries(self):
        """Check if the EMPIR binaries are available in the PATH."""
        required_binaries = [
            "empir_pixel2photon_tpx3spidr",
            "empir_photon2event",
            "empir_event2image",
        ]
        
        for binary in required_binaries:
            if not shutil.which(binary):
                raise EnvironmentError(f"Required EMPIR binary '{binary}' not found in PATH.")
            else:
                logger.debug(f"Found EMPIR binary: {binary} at {shutil.which(binary)}")
        
    @staticmethod
    def pixels_to_photons(pixel_file = "", photon_file = "", d_space = 0.0,d_time = 0.0, min_number = 0, use_tdc1 = False, log_file = ""):
        """ Runs empir_pixel2photon_tpx3spidr with the user-defined parameters. 
    
        Note: You need to have the EMPIR binaries installed and in your PATH to use this function.

        Args:
            pixel_file (str): Path to the input .tpx3 file.
            photon_file (str): Path to the output *.empirphot file.
            d_space (float): Spatial dispersion parameter.
            d_time (float): Temporal dispersion parameter.
            min_number (int): Minimum number of photons.
            use_tdc1 (bool): Whether to use TDC1.
        """

        if pixel_file == "":
            logger.error("No tpx3 file provided")
            return
        
        # Create input and output file names
        tdc_option = "-T" if use_tdc1 else ""

        # Prepare the subprocess command for running "empir_pixel2photon_tpx3spidr"
        pixels_to_photons_command = [
            "empir_pixel2photon_tpx3spidr",
            "-s", str(d_space),
            "-t", str(d_time),
            "-k", str(min_number),
            tdc_option,
            "-i", pixel_file,
            "-o", photon_file
        ]
        pixel_to_photon_run_msg = f"Running command: {' '.join(pixels_to_photons_command)}"

        logger.info(f"EMPIR: Processing pixels to photons for {pixel_file}")

        with open(log_file, 'a') as log_output:
            log_output.write("<HERMES> " + pixel_to_photon_run_msg + "\n")
            log_output.write("--------\n")
            logger.debug(f"Writing log to {log_file}")
            try:
                #subprocess.run(pixels_to_photons_command, stdout=log_output, stderr=subprocess.STDOUT)
                logger.info(f"Successfully processed pixels to photons for {pixel_file}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Error processing pixels to photons for {pixel_file}: {e}")
        
    @staticmethod
    def photons_to_events(params: PhotonToEventParams, directories: DirectoryStructure, list_file_name=""):
        """Runs empir_photon2event with the user-defined parameters. Input and output files are specified by the user.
        
        Note: You need to have the EMPIR binaries installed and in your PATH to use this function.
        
        Args:
            params (PhotonToEventParams): Parameters for empir_photon2event.
            directories (DirectoryStructure): Directory structure for input, output, and log files.
            list_file_name (str): Name of the .empirphot input file. If not provided, then exit the function.
        """
        
        if list_file_name == "":
            logger.error("No photon file provided")
            return
        
        # Create input and output file names
        input_file = os.path.join(directories.list_file_dir, list_file_name)
        log_file_name = os.path.splitext(list_file_name)[0] + ".photon2event"
        log_file = os.path.join(directories.log_file_dir, log_file_name)
        event_file_name = list_file_name.replace('.empirphot', '.empirevent')
        output_file = os.path.join(directories.event_file_dir, event_file_name)
        
        # Prepare the subprocess command
        photons_to_events_command = [
            "empir_photon2event",
            "-i", input_file,
            "-o", output_file,
            "-s", str(params.d_space),
            "-t", str(params.d_time),
            "-D", str(params.max_duration)
        ]
        
        photons_to_events_run_msg = f"Running command: {' '.join(photons_to_events_command)}"
        
        logger.info(f"EMPIR: Processing photons to events for {list_file_name}")
        
        with open(log_file, 'a') as log_output:
            log_output.write("<HERMES> " + photons_to_events_run_msg + "\n")
            log_output.write("--------\n")
            logger.debug(f"Writing log to {log_file}")
            try:
                subprocess.run(photons_to_events_command, stdout=log_output, stderr=subprocess.STDOUT)
                logger.info(f"Successfully processed photons to events for {list_file_name}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Error processing photons to events for {list_file_name}: {e}")
                
    @staticmethod
    def event_files_to_image_stack(params: EventToImageParams, directories: DirectoryStructure):
        """Runs empir_event2image with the user-defined parameters. Input and output files are specified by the user.
        
        Note: You need to have the EMPIR binaries installed and in your PATH to use this function.

        Args:
            params (EventToImageParams): Parameters for empir_event2image.
            directories (DirectoryStructure): Directory structure for input, output, and log files.
        """
        
        if params.input_files:
            event_file_list = params.input_files
        elif params.input_folder:
            event_file_dir = params.input_folder
        else:
            raise ValueError("No input file option provided. Please provide either 'input_files', 'input_folder', or 'input_list_file' as input_file_option.")

        # Create log file
        log_file_name = "event2image.log"                 # creating name for corresponding log file  
        log_file = os.path.join(directories.log_file_dir, log_file_name)   # creating full path+name for log file.
        
        # Create output image file and set path.
        image_file_name = f"image_m{str(params.nPhotons_min)}_M{str(params.nPhotons_max)}_x{params.size_x}_y{params.size_y}_t{params.time_res_s}_T{params.time_limit}_p{params.psd_min}_P{params.psd_max}.tiff"
        output_file = params.output_file or os.path.join(directories.final_file_dir, image_file_name)     # creating full path+name for output event file.
        logger.info(f"Creating image stack {output_file}")
        
        # Prepare the subprocess command
        photons_to_events_command = [
            "empir_event2image",
            "-m", str(params.nPhotons_min),
            "-M", str(params.nPhotons_max),
            "-E" if params.time_extTrigger != "ignore" else "", 
            "-x", str(params.size_x),
            "-y", str(params.size_y),
            "-t", str(params.time_res_s) if params.time_res_s is not None else "",
            "-T", str(params.time_limit) if params.time_limit is not None else "",
            "-p", str(params.psd_min) if params.psd_min is not None else "",
            "-P", str(params.psd_max) if params.psd_max is not None else "",
            "-I", params.input_folder,
            "-o", output_file
        ]
        
        photons_to_events_run_msg = f"Running command: {' '.join(photons_to_events_command)}"
        logger.info(photons_to_events_run_msg)
        
        with open(log_file, 'a') as log_output:
            log_output.write("<HERMES> " + photons_to_events_run_msg + "\n")
            log_output.write("--------\n")
            logger.debug(f"Writing log to {log_file}")
            try:
                subprocess.run(photons_to_events_command, stdout=log_output, stderr=subprocess.STDOUT)
                logger.info(f"Successfully created image stack for {output_file}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Error creating image stack for {output_file}: {e}")
            