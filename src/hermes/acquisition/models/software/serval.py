'''
Module for defining the Serval configuration pydantic models needed for setting up a Serval server.
'''

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from pathlib import Path

class ServalConfig(BaseModel):
    host : str = Field(default="localhost", description="Hostname or IP address for the Serval server.")
    port: int = Field(default=8080, description="Port number for the Serval server.")
    path_to_serval: str = Field(default="./serval/", description="Path to the serval directory.")
    version : str = Field(default="2.1.6", description="Version of the serval software.")
    path_to_serval_config_files: str = Field(default="servalConfigFiles/", description="Path to the serval config files.")
    destinations_file_name: str = Field(default="initial_serval_destinations.json", description="Initial destinations file.")
    detector_config_file_name: str = Field(default="initial_serval_detector_config.json", description="Initial detector config file.")
    bpc_file_name: str = Field(default="settings.bpc", description="Name of the BPC file.")
    dac_file_name: str = Field(default="settings.bpc.dac", description="Name of the DAC file.")
    
    @field_validator('path_to_serval')
    @classmethod
    def validate_serval_path(cls, v: str) -> str:
        """Validate that the serval directory exists."""
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Serval directory does not exist: {v}")
        if not path.is_dir():
            raise ValueError(f"Serval path is not a directory: {v}")
        return v

    @field_validator('path_to_serval_config_files')
    @classmethod
    def validate_config_files_path(cls, v: str) -> str:
        """Validate that the serval config files directory exists."""
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Serval config files directory does not exist: {v}")
        if not path.is_dir():
            raise ValueError(f"Serval config files path is not a directory: {v}")
        return v

    @model_validator(mode='after')
    def validate_config_files_exist(self):
        """Validate that the required config files exist in the config directory."""
        config_dir = Path(self.path_to_serval_config_files)
        
        # Check for destinations file
        destinations_file = config_dir / self.destinations_file_name
        if not destinations_file.exists():
            raise ValueError(f"Destinations file does not exist: {destinations_file}")
        
        # Check for detector config file
        detector_config_file = config_dir / self.detector_config_file_name
        if not detector_config_file.exists():
            raise ValueError(f"Detector config file does not exist: {detector_config_file}")
        
        # Check for BPC file
        bpc_file = config_dir / self.bpc_file_name
        if not bpc_file.exists():
            raise ValueError(f"BPC file does not exist: {bpc_file}")
        
        # Check for DAC file
        dac_file = config_dir / self.dac_file_name
        if not dac_file.exists():
            raise ValueError(f"DAC file does not exist: {dac_file}")
        
        return self

    @field_validator('port')
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate that port is in valid range."""
        if not (1 <= v <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got: {v}")
        return v