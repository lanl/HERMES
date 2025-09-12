'''
Module for defining the Serval configuration pydantic models needed for setting up a Serval server.
'''

from pydantic import BaseModel, Field
from typing import Optional

class ServalConfig(BaseModel):
    host : str = Field(default="localhost", description="Hostname or IP address for the Serval server.")
    port: int = Field(default=8080, description="Port number for the Serval server.")
    path_to_server: str = Field(default="./server/", description="Path to the server directory.")
    path_to_server_config_files: str = Field(default="serverConfigFiles/", description="Path to the server config files.")
    destinations_file_name: str = Field(default="initial_server_destinations.json", description="Initial destinations file.")
    detector_config_file_name: str = Field(default="initial_detector_config.json", description="Initial detector config file.")
    bpc_file_name: str = Field(default="settings.bpc", description="Name of the BPC file.")
    dac_file_name: str = Field(default="settings.bpc.dac", description="Name of the DAC file.")
    
    