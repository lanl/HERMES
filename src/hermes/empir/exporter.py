import os, subprocess, shutil
from pydantic import BaseModel, model_validator

from hermes.empir.models import DirectoryStructure
from hermes.empir.logger import empir_logger as logger

class Exporter(BaseModel):    
    """
    Class used to represent the EMPIR exporter functionality.
    
    This class provides methods to export pixel activations and photons from binary files.
    It requires the EMPIR "exporter" binaries to be installed and available in the system PATH.
    """
    #-------------------------------------------------------------------------------------

    @model_validator(mode='after')
    def check_for_empir_exporter_binaries(self):
        """ Check if the EMPIR exporter binaries are available in the PATH. """
        required_binaries = [
            "empir_export_pixelActivations",
            "empir_export_photons",
        ]
        
        for binary in required_binaries:
            if not shutil.which(binary):
                raise EnvironmentError(f"Required EMPIR exporter binary '{binary}' not found in PATH.")
        
        return self

    @staticmethod
    def export_pixel_activations(directories: DirectoryStructure, input_file="", output_file=""):
        """ This function exports pixel activations or hits from a tpx3 file using the binary empir_export_pixelActivations. 
        
        NOTE:   You need to have the EMPIR "exporter" binaries installed and in your PATH to use this function. These binaries are
                not available comercially, but can be obtained upon request from Adrian S. Losko and Alexander Wolfertz at TUM.

        NOTE:   The default exported format is a list of 64bit doubles in binary representation
                The information of each event is contained in 5 consecutive doubles: 
                - x coordinate in pixels on the imaging chip
                - y coordinate in pixels on the imaging chip
                - absolute time in seconds
                - time over threshold in arbitrary units
                - time relative to the last trigger (nan if the event occured before the first trigger)

        Args:
            directories (DirectoryStructure): Directory structure for input, output, and log files.
            input_file (str, optional): A specific tpx3 file. Defaults to "".
            output_file (str, optional): Specific output file name. Defaults to "".
        """
        
        # Check if input and output directories exist
        if not os.path.exists(directories.tpx3_file_dir):
            logger.error(f"Input directory does not exist: {directories.tpx3_file_dir}")
            return
        if not os.path.exists(directories.export_file_dir):
            logger.error(f"Output directory does not exist: {directories.export_file_dir}")
            return

        # Setup input and output file paths
        input_file_path = os.path.join(directories.tpx3_file_dir, input_file)
        
        # Check if the input file exists and is a .tpx3 file
        if not os.path.exists(input_file_path):
            logger.error(f"Input file does not exist: {input_file_path}")
            return
        if not input_file.endswith('.tpx3'):
            logger.error(f"Input file is not a .tpx3 file: {input_file}")
            return  
        
        # If output_file is not provided, use the input file name with a different extension
        if not output_file:
            output_file = input_file.split(".")[0] + ".pixelActivations"
        
        # Prepare the subprocess command for running "empir_export_pixelActivations"
        # NOTE there is no "-i" or "-o" flag for this command, so we need to pass the input and output file paths as arguments
        export_pixel_activations_command = [
            "empir_export_pixelActivations",
            input_file_path,
            os.path.join(directories.export_file_dir, output_file)
        ]
        
        log_file_name = input_file.split(".")[0] + ".export_pixel_activations"
        export_pixel_activations_run_msg = f"Running command: {' '.join(export_pixel_activations_command)}"
        
        logger.info(f"EMPIR: Exporting pixel activations for {input_file}")
        
        with open(os.path.join(directories.log_file_dir, log_file_name), 'a') as log_output:
            log_output.write("<HERMES> " + export_pixel_activations_run_msg + "\n")
            log_output.write("--------\n")
            logger.debug(f"Writing log to {os.path.join(directories.log_file_dir, log_file_name)}")
            try:
                subprocess.run(export_pixel_activations_command, stdout=log_output, stderr=subprocess.STDOUT)
                logger.info(f"Successfully exported pixel activations for {input_file}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Error exporting pixel activations for {input_file}: {e}")


    #-------------------------------------------------------------------------------------
    def export_photons(directories: DirectoryStructure, input_file="", output_file=""):
        """ This function exports photon from an .empirphot file using the binary empir_export_photons. 

        NOTE:   You need to have the EMPIR "exporter" binaries installed and in your PATH to use this function. These binaries are
                not available comercially, but can be obtained upon request from Adrian S. Losko and Alexander Wolfertz at TUM.

        NOTE:   The default exported format is a list of 64bit doubles in binary representation
                The information of each event is contained in 4 consecutive doubles: 
                - x coordinate in pixels on the imaging chip
                - y coordinate in pixels on the imaging chip
                - absolute time in seconds
                - time relative to the last trigger (nan if the event occured before the first trigger)

        Args:
            directories (DirectoryStructure): Directory structure for input, output, and log files.
            input_file (str, optional): A specific .empirphot file. Defaults to "".
            output_file (str, optional): Specific output file name. Defaults to "".
        """
        
        # Check if the input file exists and is a .empirphot file
        input_file_path = os.path.join(directories.list_file_dir, input_file)
        if not os.path.exists(input_file_path):
            logger.error(f"Input file does not exist: {input_file_path}")
            return
        if not input_file.endswith('.empirphot'):
            logger.error(f"Input file is not a .empirphot file: {input_file}")
            return  
        
        # Prepare the subprocess command for running "empir_export_photons"
        # NOTE there is no "-i" or "-o" flag for this command, so we need to pass the input and output file paths as arguments
        export_photons_command = [
            "empir_export_photons",
            os.path.join(directories.list_file_dir, input_file),
            os.path.join(directories.export_file_dir, output_file)
        ]
        
        log_file_name = input_file.split(".")[0] + ".export_photons"
        export_photons_run_msg = f"Running command: {' '.join(export_photons_command)}"
        
        logger.info(f"EMPIR: Exporting photons for {input_file}")
        
        with open(os.path.join(directories.log_file_dir, log_file_name), 'a') as log_output:
            log_output.write("<HERMES> " + export_photons_run_msg + "\n")
            log_output.write("--------\n")
            logger.debug(f"Writing log to {os.path.join(directories.log_file_dir, log_file_name)}")
            try:
                subprocess.run(export_photons_command, stdout=log_output, stderr=subprocess.STDOUT)
                logger.info(f"Successfully exported photons for {input_file}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Error exporting photons for {input_file}: {e}")
