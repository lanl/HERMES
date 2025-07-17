import os, subprocess
from hermes.empir.models import PixelToPhotonParams, PhotonToEventParams, EventToImageParams, DirectoryStructure

from loguru import logger


#-------------------------------------------------------------------------------------
def run_pixels_to_photons(params: PixelToPhotonParams, directories: DirectoryStructure, tpx3_file_name=""):
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
def run_photons_to_events(params: PhotonToEventParams, directories: DirectoryStructure, list_file_name=""):
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
def run_event_files_to_image_stack(params: EventToImageParams, directories: DirectoryStructure):
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
            
            
#-------------------------------------------------------------------------------------
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