
import os, shutil, glob
import subprocess
import zipfile
import struct

# using pydantic models for configuration of empir runs
from .models import PixelToPhotonParams, PhotonToEventParams, EventToImageParams, DirectoryStructure

# Import logger for empir functions
from ..utils.logger import logger

######################################################################################
# Class for configuring the processing of tpx3 files using EMPIR binaries
#-------------------------------------------------------------------------------------
class empirConfig:
    """ A configure class for the processing of tpx3 files using EMPIR binaries from 
        Adrian S. Losko at TUM. This analysis code has the following structures. 
        File structures: 
            {dest}/tpx3Files/   <- Where initial tpx3 files are saved
            {dest}/listFiles/   <- Photon "list" files are stored here
            {dest}/eventFiles/  <- Neutron "event" files are stored here
            {dest}/final/       <- Final tiff stack images are stored here.
            
        Additionally, there are empir_export binaries that can be used to extract pixel,
        photon, and event information from the tpx3 files. These can be stored in a
        separate export directory
            {dest}/export/      <- Exported pixel, photon, and event information is stored here.
    """
    def __init__(self, dest, create_sub_dirs=False,verbose_level=0):
        
        # Sanitize the dest input
        dest = os.path.abspath(os.path.normpath(dest))
        
        # Check if the directory exists
        if not os.path.exists(dest):
            logger.error(f"The specified destination directory does not exist: {dest}")
            raise FileNotFoundError(f"The specified destination directory does not exist: {dest}")
        
        # Initialize directory structure using Pydantic model
        self.directories = DirectoryStructure(
            destination_dir=f"{dest}",
            log_file_dir=f"{dest}/logFiles/",
            tpx3_file_dir=f"{dest}/tpx3Files/",
            list_file_dir=f"{dest}/listFiles/",
            event_file_dir=f"{dest}/eventFiles/",
            final_file_dir=f"{dest}/final/",
            export_file_dir=f"{dest}/exportFiles/"
        )
        
        # log the initialization of the directory structure
        logger.info(f"Initialized DirectoryStructure: {self.directories.model_dump()}")
        
        # Initialize parameters using Pydantic models
        self.pixel_to_photon_params = PixelToPhotonParams()
        self.photon_to_event_params = PhotonToEventParams()
        self.event_to_image_params = EventToImageParams()
        
        # log the initialization of the parameters
        logger.info("Initialized empirConfig with default parameters")
        
        # Check if subdirectories exist, and create them if they don't
        self.check_or_create_sub_dirs(create_sub_dirs,verbose_level)
        
    def set_pixel_to_photon_params(self, d_space=None, d_time=None, min_number=None, use_tdc1=None):
        if d_space is not None: self.pixel_to_photon_params.d_space = d_space
        if d_time is not None: self.pixel_to_photon_params.d_time = d_time
        if min_number is not None: self.pixel_to_photon_params.min_number = min_number
        if use_tdc1 is not None: self.pixel_to_photon_params.use_tdc1 = use_tdc1
        
        # log the setting of the pixel to photon parameters
        logger.info(f"Set PixelToPhotonParams: {self.pixel_to_photon_params.model_dump()}")

    def set_photon_to_event_params(self, d_space=None, d_time=None, max_duration=None, d_time_extF=None):
        if d_space is not None: self.photon_to_event_params.d_space = d_space
        if d_time is not None: self.photon_to_event_params.d_time = d_time
        if max_duration is not None: self.photon_to_event_params.max_duration = max_duration
        if d_time_extF is not None: self.photon_to_event_params.d_time_extF = d_time_extF
        
        # log the setting of the photon to event parameters
        logger.info(f"Set PhotonToEventParams: {self.photon_to_event_params.model_dump()}")

    def set_event_to_image_params(self, size_x=None, size_y=None, nPhotons_min=None, nPhotons_max=None, time_extTrigger=None, time_res_s=None, time_limit=None, psd_min=None, psd_max=None):
        if size_x is not None: self.event_to_image_params.size_x = size_x
        if size_y is not None: self.event_to_image_params.size_y = size_y
        if nPhotons_min is not None: self.event_to_image_params.nPhotons_min = nPhotons_min
        if nPhotons_max is not None: self.event_to_image_params.nPhotons_max = nPhotons_max
        if time_extTrigger is not None: self.event_to_image_params.time_extTrigger = time_extTrigger
        if time_res_s is not None: self.event_to_image_params.time_res_s = time_res_s
        if time_limit is not None: self.event_to_image_params.time_limit = time_limit
        if psd_min is not None: self.event_to_image_params.psd_min = psd_min
        if psd_max is not None: self.event_to_image_params.psd_max = psd_max
        
        # log the setting of the event to image parameters
        logger.info(f"Set EventToImageParams: {self.event_to_image_params.model_dump()}")

    def check_or_create_sub_dirs(self,create_sub_dirs=False,verbose_level=0):
        """
        Check if the subdirectories exist, and create them if they don't.
        """
        for dir_name in [self.directories.log_file_dir, self.directories.tpx3_file_dir, self.directories.list_file_dir, self.directories.event_file_dir, self.directories.final_file_dir, self.directories.export_file_dir]:
            if(verbose_level>=1):
                logger.info(f"Checking directory: {dir_name}")
            if (not os.path.exists(dir_name) and create_sub_dirs == True):
                logger.warning(f"Could not find {dir_name}... now creating {dir_name}")
                os.makedirs(dir_name)
            elif not os.path.exists(dir_name) and create_sub_dirs == False:
                logger.error(f"Could not find {dir_name}. Please create this directory or set create_sub_dirs=True in the empirConfig constructor.")
                raise FileNotFoundError(f"Could not find {dir_name}. Please create this directory or set create_sub_dirs=True in the empirConfig constructor.")
            else:
                if(verbose_level>=1):
                    logger.info(f"Found {dir_name}")


######################################################################################
# Functions for processing tpx3 files using EMPIR binaries
#-------------------------------------------------------------------------------------
def zip_file(directory, filename):  
    """Zip a file in a specified directory.

    Args:
        directory (str): The directory containing the file to zip.
        filename (str): The name of the file to zip.
    """
    with zipfile.ZipFile(os.path.join(directory, filename + '.zip'), 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(os.path.join(directory, filename), arcname=filename)


#-------------------------------------------------------------------------------------
def check_for_files(directory, extension,verbose_level=0):
    """Check if any file with a specific extension exists in a directory.

    Args:
        directory (str): The directory to check.
        extension (str): The file extension to look for.

    Returns:
        bool: True if any file with the specified extension exists in the directory, False otherwise.
    """
    check_for_files = any(glob.glob(os.path.join(directory, f'*{extension}')))
    if verbose_level == 1:
        print(f"Checking for files with extension {extension} in {directory}")
        if check_for_files == True:
            print(f"Found files with extension {extension} in {directory}")
        else:
            print(f"No files found with extension {extension} in {directory}")
    
    return check_for_files


#-------------------------------------------------------------------------------------
def process_pixels_to_photons(params: PixelToPhotonParams, directories: DirectoryStructure, tpx3_file_name=""):
    """ Runs empir_pixel2photon_tpx3spidr with the user-defined parameters. Input and output files are specified by the user.
    
    Note: You need to have the EMPIR binaries installed and in your PATH to use this function.

    Args:
        params (PixelToPhotonParams): Parameters for empir_pixel2photon_tpx3spidr.
        directories (DirectoryStructure): Directory structure for input, output, and log files.
        tpx3_file_name (str): Name of the .tpx3 input file. If not provided, then exit the function.
    """
    
    if tpx3_file_name == "":
        logger.error("No tpx3 file provided")
        return
    
    # Create input and output file names
    input_file = os.path.join(directories.tpx3_file_dir, tpx3_file_name)
    log_file_name = tpx3_file_name.split(".")[0] + ".pixel2photon"
    log_file = os.path.join(directories.log_file_dir, log_file_name)
    list_file_name = tpx3_file_name.replace('.tpx3', '.empirphot')
    output_file = os.path.join(directories.list_file_dir, list_file_name)
    tdc_option = "-T" if params.use_tdc1 else ""

    # Prepare the subprocess command for running "empir_pixel2photon_tpx3spidr"
    pixels_to_photons_command = [
        "empir_pixel2photon_tpx3spidr",
        "-s", str(params.d_space),
        "-t", str(params.d_time),
        "-k", str(params.min_number),
        tdc_option,
        "-i", input_file,
        "-o", output_file
    ]
    pixel_to_photon_run_msg = f"Running command: {' '.join(pixels_to_photons_command)}"

    logger.info(f"EMPIR: Processing pixels to photons for {tpx3_file_name}")

    with open(log_file, 'a') as log_output:
        log_output.write("<HERMES> " + pixel_to_photon_run_msg + "\n")
        log_output.write("--------\n")
        logger.debug(f"Writing log to {log_file}")
        try:
            subprocess.run(pixels_to_photons_command, stdout=log_output, stderr=subprocess.STDOUT)
            logger.info(f"Successfully processed pixels to photons for {tpx3_file_name}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error processing pixels to photons for {tpx3_file_name}: {e}")
    
       
#-------------------------------------------------------------------------------------
def process_photons_to_events(params: PhotonToEventParams, directories: DirectoryStructure, list_file_name=""):
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
            

#-------------------------------------------------------------------------------------
def process_event_files_to_image_stack(params: EventToImageParams, directories: DirectoryStructure):
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