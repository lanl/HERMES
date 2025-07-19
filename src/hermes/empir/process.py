import os
import numpy as np
import pandas as pd

from hermes.empir.models import ProcessingParameters
from hermes.empir.runner import EmpirRunner
from hermes.empir.logger import empir_logger as logger

class EmpirProcessor:
    
    """
    Class used to represent the EMPIR processing functionality.
    
    This class provides methods to process pixel data and export results.
    It requires the EMPIR binaries to be installed and available in the system PATH.
    """
    
    # Create an instance of Runner to check for EMPIR binaries
    runner = EmpirRunner()
    
    @staticmethod
    def process_pixels_to_photons(params: ProcessingParameters, batch_mode=False, verbose_level=0):
        """ Process pixel data using EMPIR binaries based on the provided parameters. """
        
        # Check if input and output directories exist
        if not os.path.exists(params.directories.tpx3_file_dir):
            logger.error(f"Input directory does not exist: {params.directories.tpx3_file_dir}")
            return
        if not os.path.exists(params.directories.output_file_dir):
            logger.error(f"Output directory does not exist: {params.directories.output_file_dir}")
            return
        
        # Example processing logic (to be implemented)
        logger.info("Processing pixel data with EMPIR binaries...")

        # if batch_mode is False, run single file from config
        if not batch_mode:
            EmpirRunner.pixels_to_photons(params.pixel_to_photon_params, params.directories)

