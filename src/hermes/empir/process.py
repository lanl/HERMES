import os
import numpy as np
import pandas as pd

# using pydantic models for configuration of empir runs
from hermes.empir.models import DirectoryStructure

# Import logger for empir functions
from hermes.empir.logger import empir_logger as logger

#-------------------------------------------------------------------------------------
def read_exported_pixel_activations(directories: DirectoryStructure, file_name: str):
    """ Reads a binary file from empir_export_pixelActivations and returns a pandas DataFrame of pixel activations.

    NOTE: The information of each event is contained in 5 consecutive doubles: 
        - x coordinate in pixels on the imaging chip
        - y coordinate in pixels on the imaging chip
        - absolute time in seconds
        - time over threshold in arbitrary units
        - time relative to the last trigger (nan if the event occured before the first trigger)

    Args:
        directories (DirectoryStructure): Directory structure for input, output, and log files.
        file_name (str): The name of the binary file containing pixel activation data.

    Returns:
        pd.DataFrame: A DataFrame containing the pixel activation data.
    """
    # Check if the export directory exists
    if not os.path.exists(directories.export_file_dir):
        logger.error(f"Export directory does not exist: {directories.export_file_dir}")
        return pd.DataFrame()
    
    file_path = os.path.join(directories.export_file_dir, file_name)
    
    # Check if the file exists
    if not os.path.exists(file_path):
        logger.error(f"File does not exist: {file_path}")
        return pd.DataFrame()

    # Read the binary file using numpy
    try:
        data = np.fromfile(file_path, dtype=np.float64)
        data = data.reshape(-1, 5)  # Each event is 5 doubles

        # Convert the numpy array to a pandas DataFrame
        df = pd.DataFrame(data, columns=[
            'x', 'y', 'absolute_time', 'time_over_threshold', 'time_relative_to_trigger'
        ])
        return df
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return pd.DataFrame()