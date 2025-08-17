from pydantic import BaseModel, Field, validator
import tempfile
from typing import Optional




class Serval_2_1_6(BaseModel):
    log_name: str = Field(default="http.log", description="File name to store the Serval log. Defaults to: 'serval.log'")
    httpLog: str = Field(default="/tmp/http.log", description="File path to store the HTTP access log. Defaults to: '<working-directory>/http.log'")
    httpPort: int = Field(default=8080, description="HTTP port number to listen for clients log.")
    spidrNet: str = Field(default="192.168.100.10", description="Sets the ip address Serval needs to look for the spidr.")
    deviceMask: Optional[int] = Field(default=None, description="Integer representing the device mask.")
    packetBuffers: Optional[int] = Field(default=None, description="Integer representing the size of the packet ringbuffer to use.")
    deadTime: Optional[int] = Field(default=None, description="Integer representing the time to sleep between frames in us.")
    tcpDebug: Optional[str] = Field(default=None, description="File path to store the TCP debug log. Defaults to none.")
    experimental: Optional[bool] = Field(default=False, description="Whether unsupported experimental options should be unlocked.")



class ServalConfig(BaseModel):
    path_to_serval: str = Field(default="./serval/", description="Path to the serval directory.")
    path_to_serval_config_files: str = Field(default="servalConfigFiles/", description="Path to the serval config files.")
    destinations_file_name: str = Field(default="initial_serval_destinations.json", description="Initial destinations file.")
    detector_config_file_name: str = Field(default="initial_detector_config.json", description="Initial detector config file.")
    bpc_file_name: str = Field(default="settings.bpc", description="Name of the BPC file.")
    dac_file_name: str = Field(default="settings.bpc.dac", description="Name of the DAC file.")
    serval: Serval_2_1_6 = Field(default_factory=Serval_2_1_6, description="Configuration for the Serval 2.1.6.")