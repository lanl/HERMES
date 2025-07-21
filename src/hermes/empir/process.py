import os
import numpy as np
import pandas as pd


from hermes.empir.models import ProcessingParameters
from hermes.empir.runner import EmpirRunner
from hermes.empir.logger import empir_logger as logger

class EmpirProcessor():
    
    """
    Class used to represent the EMPIR processing functionality.
    
    This class provides methods to process pixel data and export results.
    It requires the EMPIR binaries to be installed and available in the system PATH.
    """
    # Create an instance of Runner to check for EMPIR binaries
    
    def __init__(self):
        """Initialize processor with required dependencies."""
        self.runner = EmpirRunner()
    

    def process_pixels_to_photons(self, params: ProcessingParameters, batch_mode=False, verbose_level=0):
        """Process pixel data using EMPIR binaries based on the provided parameters."""

        # Check if input and output directories exist
        if not os.path.exists(params.directories.tpx3_file_dir):
            logger.error(f"Input directory does not exist: {params.directories.tpx3_file_dir}")
            return
        if not os.path.exists(params.directories.output_file_dir):
            logger.error(f"Output directory does not exist: {params.directories.output_file_dir}")
            return

        logger.info("Processing pixel data with EMPIR binaries...")

        # Extract parameters for pixel to photon conversion
        d_space = params.pixel_to_photon_params.d_space
        d_time = params.pixel_to_photon_params.d_time
        min_number = params.pixel_to_photon_params.min_number
        use_tdc1 = params.pixel_to_photon_params.use_tdc1

        # Set up file paths
        if batch_mode:
            # If batch mode, process all files in the input directory
            pixel_files = [os.path.join(params.directories.tpx3_file_dir, f) for f in os.listdir(params.directories.tpx3_file_dir) if f.endswith('.tpx3')]
            photon_files = [os.path.join(params.directories.output_file_dir, f.replace('.tpx3', '.empirphot')) for f in os.listdir(params.directories.tpx3_file_dir) if f.endswith('.tpx3')]
            log_files = [os.path.join(params.directories.log_file_dir, f.replace('.tpx3', '_pixel2photon.log')) for f in os.listdir(params.directories.tpx3_file_dir) if f.endswith('.tpx3')]
        
            # TODO: Implement batch processing logic here
            for pixel_file, photon_file, log_file in zip(pixel_files, photon_files, log_files):
                logger.info(f"Processing {pixel_file} to {photon_file} with log file {log_file}")
                self.runner.pixels_to_photons(
                    pixel_file=pixel_file,
                    photon_file=photon_file,
                    d_space=d_space,
                    d_time=d_time,
                    min_number=min_number,
                    use_tdc1=use_tdc1,
                    log_file=log_file
                )
                logger.info(f"Processed {pixel_file} to {photon_file} successfully.")
        
        else:
            # If batch mode is False, process a single file from the config
            if not params.pixel_to_photon_params.input_file:
                logger.error("Input file name must be specified in non-batch mode.")
                return
            
            # if no output file is specified, create one based on input file name
            if not params.pixel_to_photon_params.output_file:
                params.pixel_to_photon_params.output_file = params.pixel_to_photon_params.input_file.replace('.tpx3', '.empirphot')

            if not params.pixel_to_photon_params.log_file:
                params.pixel_to_photon_params.log_file = params.pixel_to_photon_params.input_file.replace('.tpx3', '_pixel2photon.log')


            pixel_file = os.path.join(params.directories.tpx3_file_dir, params.pixel_to_photon_params.input_file)
            photon_file = os.path.join(params.directories.output_file_dir, params.pixel_to_photon_params.output_file)
            log_file = os.path.join(params.directories.log_file_dir, params.pixel_to_photon_params.log_file)

            # Log the file paths
            logger.info(f"Processing {pixel_file} to {photon_file} with log file {log_file}")

            # Process a single file
            self.runner.pixels_to_photons(
                pixel_file=pixel_file,
                photon_file=photon_file,
                d_space=d_space,
                d_time=d_time,
                min_number=min_number,
                use_tdc1=use_tdc1,
                log_file=log_file
            )

            logger.info(f"Processed {pixel_file} to {photon_file} successfully.")