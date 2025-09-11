'''
Module for defining pydantic hardware models needed for communication with the SPIDR readout system.
''''''
Module for defining pydantic hardware models needed for communication with the SPIDR readout system.
'''

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class SPIDRConfig(BaseModel):
    """Configuration for SPIDR readout system."""
    
    host: str = Field(default="localhost", description="SPIDR host address")
    port: int = Field(default=8080, description="SPIDR port number")
    timeout: float = Field(default=30.0, description="Connection timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum connection retries")
    
class DetectorConfig(BaseModel):
    """Configuration for detector hardware."""
    
    detector_id: str = Field(default="TPX3_001", description="Detector identifier")
    pixel_size: float = Field(default=55.0, description="Pixel size in micrometers")
    matrix_size: tuple[int, int] = Field(default=(256, 256), description="Detector matrix size (width, height)")
    bias_voltage: float = Field(default=40.0, description="Bias voltage in volts")
    
class HardwareConfig(BaseModel):
    """General hardware configuration model."""
    
    spidr: SPIDRConfig = Field(default_factory=SPIDRConfig, description="SPIDR readout configuration")
    detector: DetectorConfig = Field(default_factory=DetectorConfig, description="Detector configuration")
    
    # General hardware settings
    acquisition_mode: str = Field(default="TOT", description="Acquisition mode (TOT, TOA, etc.)")
    trigger_mode: str = Field(default="internal", description="Trigger mode")
    
    # Optional advanced settings
    advanced_settings: Optional[Dict[str, Any]] = Field(default=None, description="Advanced hardware settings")
    
    class Config:
        validate_assignment = True