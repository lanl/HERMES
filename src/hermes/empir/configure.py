
import os, glob
import zipfile
import configparser
import json
from typing import Optional

# using pydantic models for configuration of empir runs
from pydantic import BaseModel, Field, field_validator, model_validator
from hermes.empir.models import ProcessingParameters, DirectoryStructure, PixelToPhotonParams, PhotonToEventParams, EventToImageParams
from hermes.empir.logger import empir_logger as logger
from hermes.empir.logger import configure_logger


######################################################################################
# Class for configuring the processing of tpx3 files using EMPIR binaries
#-------------------------------------------------------------------------------------
class Configuration(BaseModel):
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
    
    empir_parameters: ProcessingParameters = Field(default_factory=ProcessingParameters, description="Parameters for the EMPIR processing")
    empir_log_file_name: Optional[str] = Field(default=None, description="Name of the log file for EMPIR processing with HERMES")

    model_config = {
        # Allow arbitrary types for compatibility with existing code
        "arbitrary_types_allowed": True,
        # Validate assignment to catch issues early
        "validate_assignment": True,
    }
    
    @model_validator(mode='after')
    def setup_logger(self):
        """Initialize logger after model creation with file logging in current directory."""
        # Set up logging with hermes_empir.log in current working directory
        if self.empir_log_file_name is None:
            log_file_path = os.path.join(os.getcwd(), "hermes_empir.log")
        else:
            log_file_path = self.empir_log_file_name
            
        configure_logger(log_file_path=log_file_path, verbose_level=0)  # File logging from start

        # Add separator for new Configuration instance
        logger.info("-" * 80)
        logger.debug("Configuration instance initialized")
        logger.info("-" * 80)
        return self
        

    def configure_from_destination(self, dest: str, create_sub_dirs: bool = False, verbose_level: int = 0):
        """
        Update this Configuration instance's empir_parameters from a destination directory.
        
        Args:
            dest (str): Destination directory path
            verbose_level (int): Verbosity level
        """
        
        # Update console verbosity level while keeping file logging in current directory
        # Set up logging with hermes_empir.log in current working directory
        if self.empir_log_file_name is None:
            log_file_path = os.path.join(os.getcwd(), "hermes_empir.log")
        else:
            log_file_path = self.empir_log_file_name 
            
        configure_logger(log_file_path=log_file_path, verbose_level=verbose_level)
        
        # Check if destination directory is provided
        if dest is None:
            logger.error("No destination directory provided. Please provide a destination directory.")
            raise ValueError("No destination directory provided. Please provide a destination directory.")
        
        # If a destination directory is provided, check if it exists
        if not os.path.exists(dest):
            logger.error(f"Destination directory does not exist: {dest}")
            raise FileNotFoundError(f"Destination directory does not exist: {dest}")
        
        # Sanitize the dest input
        dest = os.path.abspath(os.path.normpath(dest))
        
        if verbose_level >= 1: 
            logger.info(f"Using provided destination directory: {dest}")
            logger.info(f"Logging to file: {log_file_path}")
        
        # Initialize directory structure
        directories = DirectoryStructure(
            destination_dir=f"{dest}",
            create_subdirs=create_sub_dirs,
            log_file_dir=f"{dest}/logFiles/",
            tpx3_file_dir=f"{dest}/tpx3Files/",
            list_file_dir=f"{dest}/listFiles/",
            event_file_dir=f"{dest}/eventFiles/",
            final_file_dir=f"{dest}/final/",
            export_file_dir=f"{dest}/exportFiles/"
        )
        
        # Log the initialization of the directory structure
        if verbose_level >= 1: 
            logger.debug(f"Initialized DirectoryStructure: {directories.model_dump()}")

        # Update the existing empir_parameters
        self.empir_parameters.verbose_level = verbose_level
        self.empir_parameters.directories = directories
        
        # Check or create subdirectories if requested
        if directories and directories.create_subdirs:
            self.check_or_create_sub_dirs(create_sub_dirs=True, verbose_level=verbose_level)
        
        if verbose_level >= 1: 
            logger.info("Updated Configuration empir_parameters from destination directory")

    @classmethod
    def new_config_from_destination(cls, dest: str, verbose_level: int = 0):
        """
        Create a new Configuration instance from a destination directory.
        
        Args:
            dest (str): Destination directory path
            verbose_level (int): Verbosity level
            
        Returns:
            Configuration: A new Configuration instance
        """
        # Create a new Configuration instance
        config = cls()
        
        # Configure it from the destination
        config.configure_from_destination(dest, verbose_level)
        
        return config

    def configure_from_init_file(self, config_file_path: str, verbose_level: int = 0):
        """
        Configure this Configuration instance from a configuration file using ConfigParser.
        
        Args:
            config_file_path (str): Path to the configuration file
            verbose_level (int): Verbosity level
        """
        
        # Update console verbosity level while keeping file logging in current directory
        log_file_path = os.path.join(os.getcwd(), "hermes.log")
        configure_logger(log_file_path=log_file_path, verbose_level=verbose_level)
        
        # Check if config file exists
        if not os.path.exists(config_file_path):
            logger.error(f"Configuration file does not exist: {config_file_path}")
            raise FileNotFoundError(f"Configuration file does not exist: {config_file_path}")
        
        config = configparser.ConfigParser()
        config.read(config_file_path)
        
        logger.info(f"Reading configuration from: {config_file_path}")
        
        # Parse directory structure if present
        directories = None
        if config.has_section('directory_structure'):
            if verbose_level >= 1:
                logger.info(f"Found directory_structure section in: {config_file_path}")

            dest_dir = config.get('directory_structure', 'destination_dir', fallback=None)
            
            if dest_dir:
                dest_dir = os.path.abspath(os.path.normpath(dest_dir))
                
                # Build directory paths
                log_dir = config.get('directory_structure', 'log_file_dir', fallback='logFiles')
                tpx3_dir = config.get('directory_structure', 'tpx3_file_dir', fallback='tpx3Files')
                list_dir = config.get('directory_structure', 'list_file_dir', fallback='listFiles')
                event_dir = config.get('directory_structure', 'event_file_dir', fallback='eventFiles')
                final_dir = config.get('directory_structure', 'final_file_dir', fallback='final')
                export_dir = config.get('directory_structure', 'export_file_dir', fallback='exportFiles')
                create_subdirs = config.getboolean('directory_structure', 'create_subdirs', fallback=False)
                
                # Create DirectoryStructure
                directories = DirectoryStructure(
                    destination_dir=dest_dir,
                    create_subdirs=create_subdirs,
                    log_file_dir=os.path.join(dest_dir, log_dir),
                    tpx3_file_dir=os.path.join(dest_dir, tpx3_dir),
                    list_file_dir=os.path.join(dest_dir, list_dir),
                    event_file_dir=os.path.join(dest_dir, event_dir),
                    final_file_dir=os.path.join(dest_dir, final_dir),
                    export_file_dir=os.path.join(dest_dir, export_dir)
                )

                if verbose_level >= 1:
                    logger.info(f"Configured DirectoryStructure from config file: {config_file_path}")
                    
            else:
                logger.warning(f"Directory structure section is incomplete in: {config_file_path}. Please ensure 'destination_dir' is set.")

        # Parse pixel_to_photon parameters if present
        pixel_to_photon_params = None
        if config.has_section('pixel_to_photon'):
            if verbose_level >= 1:
                logger.info(f"Found pixel_to_photon section in: {config_file_path}")
            
            pixel_to_photon_params = PixelToPhotonParams()
            
            if config.has_option('pixel_to_photon', 'input_file'):
                pixel_to_photon_params.input_file_name = config.get('pixel_to_photon', 'input_file')
            if config.has_option('pixel_to_photon', 'output_file'):
                pixel_to_photon_params.output_file_name = config.get('pixel_to_photon', 'output_file')
            if config.has_option('pixel_to_photon', 'log_file'):
                pixel_to_photon_params.log_file_name = config.get('pixel_to_photon', 'log_file')
            if config.has_option('pixel_to_photon', 'd_space'):
                pixel_to_photon_params.d_space = config.getfloat('pixel_to_photon', 'd_space')
            if config.has_option('pixel_to_photon', 'd_time'):
                pixel_to_photon_params.d_time = config.getfloat('pixel_to_photon', 'd_time')
            if config.has_option('pixel_to_photon', 'min_number'):
                pixel_to_photon_params.min_number = config.getint('pixel_to_photon', 'min_number')
            if config.has_option('pixel_to_photon', 'use_tdc1'):
                pixel_to_photon_params.use_tdc1 = config.getboolean('pixel_to_photon', 'use_tdc1')
            if config.has_option('pixel_to_photon', 'parameter_file'):
                pixel_to_photon_params.parameter_file = config.get('pixel_to_photon', 'parameter_file')

            # Log the configuration of pixel_to_photon_params
            # TODO: Add a logging funtion in logger.py to record (and update) a passed .json file
            
            # Log configuration is complete
            if verbose_level >= 1:
                logger.info(f"Configured PixelToPhotonParams from config file: {config_file_path}")

        # Parse photon_to_event parameters if present
        photon_to_event_params = None
        if config.has_section('photon_to_event'):
            if verbose_level >= 1:
                logger.info(f"Found photon_to_event section in: {config_file_path}")

            photon_to_event_params = PhotonToEventParams()
            
            if config.has_option('photon_to_event', 'input_file'):
                photon_to_event_params.input_file = config.get('photon_to_event', 'input_file')
            if config.has_option('photon_to_event', 'output_file'):
                photon_to_event_params.output_file = config.get('photon_to_event', 'output_file')
            if config.has_option('photon_to_event', 'd_space'):
                photon_to_event_params.d_space = config.getfloat('photon_to_event', 'd_space')
            if config.has_option('photon_to_event', 'd_time'):
                photon_to_event_params.d_time = config.getfloat('photon_to_event', 'd_time')
            if config.has_option('photon_to_event', 'max_duration'):
                photon_to_event_params.max_duration = config.getfloat('photon_to_event', 'max_duration')
            if config.has_option('photon_to_event', 'd_time_extF'):
                photon_to_event_params.d_time_extF = config.getfloat('photon_to_event', 'd_time_extF')
            if config.has_option('photon_to_event', 'parameter_file'):
                photon_to_event_params.parameter_file = config.get('photon_to_event', 'parameter_file')
                
            # Log the configuration of photon_to_event_params
            # TODO: Add a logging function in logger.py to record (and update) a passed .json file

            # Log configuration is complete
            if verbose_level >= 1:
                logger.info(f"Configured PhotonToEventParams from config file: {config_file_path}")

        # Parse event_to_image parameters if present (optional)
        event_to_image_params = None
        if config.has_section('event_to_image'):
            if verbose_level >= 1:
                logger.info(f"Found event_to_image section in: {config_file_path}")
            
            event_to_image_params = EventToImageParams()
            
            if config.has_option('event_to_image', 'size_x'):
                event_to_image_params.size_x = config.getint('event_to_image', 'size_x')
            if config.has_option('event_to_image', 'size_y'):
                event_to_image_params.size_y = config.getint('event_to_image', 'size_y')
            if config.has_option('event_to_image', 'nPhotons_min'):
                event_to_image_params.nPhotons_min = config.getint('event_to_image', 'nPhotons_min')
            if config.has_option('event_to_image', 'nPhotons_max'):
                event_to_image_params.nPhotons_max = config.getint('event_to_image', 'nPhotons_max')
            if config.has_option('event_to_image', 'time_extTrigger'):
                event_to_image_params.time_extTrigger = config.getfloat('event_to_image', 'time_extTrigger')
            if config.has_option('event_to_image', 'time_res_s'):
                event_to_image_params.time_res_s = config.getfloat('event_to_image', 'time_res_s')
            if config.has_option('event_to_image', 'time_limit'):
                event_to_image_params.time_limit = config.getfloat('event_to_image', 'time_limit')
            if config.has_option('event_to_image', 'psd_min'):
                event_to_image_params.psd_min = config.getfloat('event_to_image', 'psd_min')
            if config.has_option('event_to_image', 'psd_max'):
                event_to_image_params.psd_max = config.getfloat('event_to_image', 'psd_max')
            if config.has_option('event_to_image', 'parameter_file'):
                event_to_image_params.parameter_file = config.get('event_to_image', 'parameter_file')

            # Log the configuration of event_to_image_params
            # TODO: Add a logging function in logger.py to record (and update) a passed .json file

            # Log configuration is complete
            if verbose_level >= 1:
                logger.info(f"Configured EventToImageParams from config file: {config_file_path}")
        else:
            if verbose_level >= 1:
                logger.info("No [event_to_image] section found in config file, leaving as None")
        
        # Update the existing empir_parameters
        self.empir_parameters.verbose_level = verbose_level
        if directories:
            self.empir_parameters.directories = directories
        if pixel_to_photon_params:
            self.empir_parameters.pixel_to_photon_params = pixel_to_photon_params
        if photon_to_event_params:
            self.empir_parameters.photon_to_event_params = photon_to_event_params
        if event_to_image_params:
            self.empir_parameters.event_to_image_params = event_to_image_params
        
        # Log the initialization of the directory structure
        if verbose_level >= 1: 
            logger.debug(f"Initialized DirectoryStructure: {directories.model_dump()}")
        
        # Check or create subdirectories if requested
        if directories and directories.create_subdirs:
            self.check_or_create_sub_dirs(create_sub_dirs=True, verbose_level=verbose_level)
        
        # Log the completion of configuration
        if verbose_level >= 1:
            logger.info("Updated Configuration empir_parameters from config file")

    @classmethod  
    def new_config_from_config_file(cls, config_file_path: str, verbose_level: int = 0):
        """
        Create a new Configuration instance from a configuration file using ConfigParser.
        
        Args:
            config_file_path (str): Path to the configuration file
            verbose_level (int): Verbosity level
            
        Returns:
            Configuration: A new Configuration instance
        """
        # Create a new Configuration instance
        config = cls()
        
        # Configure it from the config file
        config.configure_from_config_file(config_file_path, verbose_level)
        
        return config
    
    @classmethod
    def set_pixel_to_photon_params(cls, instance, d_space=None, d_time=None, min_number=None, use_tdc1=None):
        """Update pixel to photon parameters on an instance"""
        if instance.empir_parameters.pixel_to_photon_params is None:
            instance.empir_parameters.pixel_to_photon_params = PixelToPhotonParams()
            
        if d_space is not None: 
            instance.empir_parameters.pixel_to_photon_params.d_space = d_space
        if d_time is not None: 
            instance.empir_parameters.pixel_to_photon_params.d_time = d_time
        if min_number is not None: 
            instance.empir_parameters.pixel_to_photon_params.min_number = min_number
        if use_tdc1 is not None: 
            instance.empir_parameters.pixel_to_photon_params.use_tdc1 = use_tdc1

        # log the setting of the pixel to photon parameters
        logger.info(f"Set PixelToPhotonParams: {instance.empir_parameters.pixel_to_photon_params.model_dump()}")

    @classmethod
    def set_photon_to_event_params(cls, instance, d_space=None, d_time=None, max_duration=None, d_time_extF=None):
        """Update photon to event parameters on an instance"""
        if instance.empir_parameters.photon_to_event_params is None:
            instance.empir_parameters.photon_to_event_params = PhotonToEventParams()
            
        if d_space is not None: 
            instance.empir_parameters.photon_to_event_params.d_space = d_space
        if d_time is not None: 
            instance.empir_parameters.photon_to_event_params.d_time = d_time
        if max_duration is not None: 
            instance.empir_parameters.photon_to_event_params.max_duration = max_duration
        if d_time_extF is not None: 
            instance.empir_parameters.photon_to_event_params.d_time_extF = d_time_extF

        # log the setting of the photon to event parameters
        logger.info(f"Set PhotonToEventParams: {instance.empir_parameters.photon_to_event_params.model_dump()}")

    @classmethod
    def set_event_to_image_params(cls, instance, size_x=None, size_y=None, nPhotons_min=None, nPhotons_max=None, time_extTrigger=None, time_res_s=None, time_limit=None, psd_min=None, psd_max=None):
        """Update event to image parameters on an instance"""
        if instance.empir_parameters.event_to_image_params is None:
            instance.empir_parameters.event_to_image_params = EventToImageParams()
            
        if size_x is not None: 
            instance.empir_parameters.event_to_image_params.size_x = size_x
        if size_y is not None: 
            instance.empir_parameters.event_to_image_params.size_y = size_y
        if nPhotons_min is not None: 
            instance.empir_parameters.event_to_image_params.nPhotons_min = nPhotons_min
        if nPhotons_max is not None: 
            instance.empir_parameters.event_to_image_params.nPhotons_max = nPhotons_max
        if time_extTrigger is not None: 
            instance.empir_parameters.event_to_image_params.time_extTrigger = time_extTrigger
        if time_res_s is not None: 
            instance.empir_parameters.event_to_image_params.time_res_s = time_res_s
        if time_limit is not None: 
            instance.empir_parameters.event_to_image_params.time_limit = time_limit
        if psd_min is not None: 
            instance.empir_parameters.event_to_image_params.psd_min = psd_min
        if psd_max is not None: 
            instance.empir_parameters.event_to_image_params.psd_max = psd_max

        # log the setting of the event to image parameters
        logger.info(f"Set EventToImageParams: {instance.empir_parameters.event_to_image_params.model_dump()}")

    def check_or_create_sub_dirs(self, create_sub_dirs=False, verbose_level=None):
        """
        Check if the subdirectories exist, and create them if they don't.
        """
        if verbose_level is None:
            verbose_level = self.empir_parameters.verbose_level

        for dir_name in [self.empir_parameters.directories.log_file_dir, self.empir_parameters.directories.tpx3_file_dir,
                         self.empir_parameters.directories.list_file_dir, self.empir_parameters.directories.event_file_dir,
                         self.empir_parameters.directories.final_file_dir, self.empir_parameters.directories.export_file_dir]:
            if verbose_level >= 1:
                logger.info(f"Checking directory: {dir_name}")
            if not os.path.exists(dir_name) and create_sub_dirs:
                logger.warning(f"Could not find {dir_name}... now creating {dir_name}")
                os.makedirs(dir_name)
            elif not os.path.exists(dir_name) and not create_sub_dirs:
                logger.error(f"Could not find {dir_name}. Please create this directory or set create_sub_dirs=True.")
                raise FileNotFoundError(f"Could not find {dir_name}. Please create this directory or set create_sub_dirs=True.")
            else:
                if verbose_level >= 1:
                    logger.info(f"Found {dir_name}")

    def model_dump_json(self, indent=4):
        """Return the configuration as a JSON string."""
        return json.dumps(self.model_dump(), indent=indent)


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
