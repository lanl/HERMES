
import os, shutil, glob
import subprocess
import zipfile
import struct
import configparser

# using pydantic models for configuration of empir runs
from .models import PixelToPhotonParams, PhotonToEventParams, EventToImageParams, DirectoryStructure

# Import logger for empir functions
#from ..utils.logger import logger

from loguru import logger


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
    def __init__(self, config_file=None, dest=None, verbose_level=0):

        # Check if a configuration file is provided
        if config_file:
            logger.info(f"Configuring empirConfig from file: {config_file}")
            
            # Check if the configuration file exists
            if not os.path.exists(config_file):
                logger.error(f"Configuration file does not exist: {config_file}")
                raise FileNotFoundError(f"Configuration file does not exist: {config_file}")
            else:
                self.configure_from_file(config_file)

        # If no config file is provided, this use default parameters and destination directory
        else:

            logger.info("No configuration file provided, using default parameters.")
            
            # check if destination directory is provided, if not exit with error
            if dest is None:
                logger.error("No destination directory provided. Please provide a destination directory.")
                raise ValueError("No destination directory provided. Please provide a destination directory.")
            
            # If a destination directory is provided, check if it exists
            else:
                if not os.path.exists(dest):
                    logger.error(f"Destination directory does not exist: {dest}")
                    raise FileNotFoundError(f"Destination directory does not exist: {dest}")
                else:
                    # If the destination directory exists, use it
                    logger.info(f"Using provided destination directory: {dest}")
                
                # Sanitize the dest input
                dest = os.path.abspath(os.path.normpath(dest))
        
        
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
        
        # Check or create subdirectories
        #self.check_or_create_sub_dirs()
        
    def configure_from_file(self, config_file_path):
        """
        Configure the empirConfig instance from a configuration file using ConfigParser.
        
        Args:
            config_file_path (str): Path to the configuration file
        """
        if not os.path.exists(config_file_path):
            logger.error(f"Configuration file does not exist: {config_file_path}")
            raise FileNotFoundError(f"Configuration file does not exist: {config_file_path}")
        
        config = configparser.ConfigParser()
        config.read(config_file_path)
        
        logger.info(f"Reading configuration from: {config_file_path}")
    
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
