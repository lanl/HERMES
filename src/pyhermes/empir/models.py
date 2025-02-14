from pydantic import BaseModel, Field
from typing import Optional, List
import struct

class DirectoryStructure(BaseModel):
    destination_dir: str = Field(..., description="Location of run directory")
    log_file_dir: str = Field(..., description="Location of log files")
    tpx3_file_dir: str = Field(..., description="Location of TPX3 files")
    list_file_dir: str = Field(..., description="Location of list files")
    event_file_dir: str = Field(..., description="Location of event files")
    final_file_dir: str = Field(..., description="Location of final image files")
    export_file_dir: str = Field(..., description="Location of exported info files")

class PixelToPhotonParams(BaseModel):
    d_space: int = Field(default=10, description="Distance in space for pixel search [px]")
    d_time: float = Field(default=1e-6, description="Distance in time for pixel search [s]")
    min_number: int = Field(default=2, description="Minimum number of pixels in a photon event")
    use_tdc1: bool = Field(default=False, description="Use TDC1 as trigger input")

class PhotonToEventParams(BaseModel):
    d_space: Optional[int] = Field(default=None, description="Distance in space for photon search [px]")
    d_time: Optional[float] = Field(default=None, description="Distance in time for photon search [s]")
    max_duration: Optional[float] = Field(default=None, description="Maximum duration to look for photons [s]")
    d_time_extF: Optional[float] = Field(default=None, description="Extents duration by multiple of time difference to last photon")

class EventToImageParams(BaseModel):
    input_files: Optional[str] = Field(default=None, description="Comma separated list of files to process")
    input_folder: Optional[str] = Field(default=None, description="All files with the .empirevent extension directly in this folder will be processed")
    input_list_file: Optional[str] = Field(default=None, description="Path of text file containing one input file per line")
    output_file: Optional[str] = Field(default=None, description="Path (including file name) for the output")
    params_file: Optional[str] = Field(default=None, description="Path to a .json file where processing parameters are defined")
    size_x: int = Field(default=512, description="Number of pixels in x direction for the final image")
    size_y: int = Field(default=512, description="Number of pixels in y direction for the final image")
    nPhotons_min: int = Field(default=0, description="Minimum number of photons for image processing")
    nPhotons_max: int = Field(default=18446744073709551615, description="Maximum number of photons for image processing")
    time_extTrigger: str = Field(default="ignore", description='How the external trigger should be used: "ignore" (default), "reference", or "frameSync"')
    time_res_s: Optional[float] = Field(default=None, description="Timing resolution in seconds for 3D image sequence")
    time_limit: Optional[int] = Field(default=None, description="Maximum of time bins for the 3D image sequence")
    psd_min: float = Field(default=0, description="Minimum PSD value")
    psd_max: float = Field(default=100, description="Maximum PSD value")
    file_format: str = Field(default="tiff_w4", description='Format for the output file. Possibilities are: "tiff_w4" (default) or "tiff_w8"')
    parallel: bool = Field(default=True, description='Control parallel processing. Set "true" for on (default) and "false" for off')
    
class PixelActivation(BaseModel):
    """
    Class used to represent pixel activation data exported from an output binary file using empir_export_pixelActivations.

    Attributes:
        x (float): X coordinate in pixels on the imaging chip.
        y (float): Y coordinate in pixels on the imaging chip.
        absolute_time (float): Absolute time in seconds.
        time_over_threshold (float): Time over threshold in arbitrary units.
        time_relative_to_trigger (float): Time relative to the last trigger.
    """
    x: float = Field(..., description="X coordinate in pixels on the imaging chip")
    y: float = Field(..., description="Y coordinate in pixels on the imaging chip")
    absolute_time: float = Field(..., description="Absolute time in seconds")
    time_over_threshold: float = Field(..., description="Time over threshold in arbitrary units")
    time_relative_to_trigger: float = Field(..., description="Time relative to the last trigger")
    
    
class Photon(BaseModel):
    """
    Class used to represent photon data.

    Attributes:
        x (float): X coordinate in pixels on the imaging chip.
        y (float): Y coordinate in pixels on the imaging chip.
        absolute_time (float): Absolute time in seconds.
        time_relative_to_trigger (float): Time relative to the last trigger.
    """
    x: float = Field(..., description="X coordinate in pixels on the imaging chip")
    y: float = Field(..., description="Y coordinate in pixels on the imaging chip")
    absolute_time: float = Field(..., description="Absolute time in seconds")
    time_relative_to_trigger: float = Field(..., description="Time relative to the last trigger")
    
class ExportedPixels(BaseModel):
    """ 
    This class is used to store and process pixel activation data.
    It is initialized with a list of PixelActivation objects.
    
    Attributes:
        activations (List[PixelActivation]): List of pixel activation objects.
    """
    activations: List[PixelActivation] = Field(default_factory=list, description="List of pixel activations")

    @classmethod
    def from_binary_file(cls, file_path: str) -> "ExportedPixels":
        """Create an ExportedPixels instance from a binary file.

        Args:
            file_path (str): The path to the binary file containing pixel activation data.

        Returns:
            ExportedPixels: An instance of ExportedPixels populated with pixel activations.
        """
        
        # Create an empty list to store pixel activations
        activations = []
        
        # Open the binary file for reading
        with open(file_path, 'rb') as f:
            # Read the file in chunks of 5 doubles (8 bytes each)
            while True:
                data = f.read(5 * 8) 
                if not data:
                    break
                x, y, absolute_time, time_over_threshold, time_relative_to_trigger = struct.unpack('5d', data)
                
                # Create a PixelActivation object 
                activation = PixelActivation(
                    x=x,
                    y=y,
                    absolute_time=absolute_time,
                    time_over_threshold=time_over_threshold,
                    time_relative_to_trigger=time_relative_to_trigger
                )
                # Append the PixelActivation object to the list
                activations.append(activation)
                
        # Return an instance of ExportedPixels with the list of activations
        return cls(activations=activations)
    
class ExportedPhotons(BaseModel):
    """ 
    This class is used to store and process photon data.
    It is initialized with a list of Photon objects.
    
    Attributes:
        photons (List[Photon]): List of photon objects.
    """
    photons: List[Photon] = Field(default_factory=list, description="List of photon objects")

    @classmethod
    def from_binary_file(cls, file_path: str) -> "ExportedPhotons":
        """Create an ExportedPhotons instance from a binary file.

        Args:
            file_path (str): The path to the binary file containing photon data.

        Returns:
            ExportedPhotons: An instance of ExportedPhotons populated with photon data.
        """
        
        # Create an empty list to store photon data
        photons = []
        
        # Open the binary file for reading
        with open(file_path, 'rb') as f:
            # Read the file in chunks of 4 doubles (8 bytes each)
            while True:
                data = f.read(4 * 8) 
                if not data:
                    break
                x, y, absolute_time, time_relative_to_trigger = struct.unpack('4d', data)
                
                # Create a Photon object 
                photon = Photon(
                    x=x,
                    y=y,
                    absolute_time=absolute_time,
                    time_relative_to_trigger=time_relative_to_trigger
                )
                # Append the Photon object to the list
                photons.append(photon)
                
        # Return an instance of ExportedPhotons with the list of photons
        return cls(photons=photons)