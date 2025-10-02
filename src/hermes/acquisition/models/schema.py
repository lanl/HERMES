'''
Master schema for HERMES acquisition system configuration.
'''

from pydantic import BaseModel, Field
from typing import Optional

from hermes.acquisition.models.software.environment import WorkingDir
from hermes.acquisition.models.software.serval import ServalConfig
from hermes.acquisition.models.software.parameters import RunSettings
from hermes.acquisition.models.software.epics import EPICSConfig
from hermes.acquisition.models.hardware.tpx3Cam import HardwareConfig
from hermes.acquisition.models.hardware.zabers import ZaberConfig

class Default(BaseModel):  
    """
    Default acquisition schema combining all software and hardware configurations.
    """
    
    # Software configuration
    environment: WorkingDir = Field(default_factory=WorkingDir)
    serval: ServalConfig = Field(default_factory=ServalConfig)
    run_settings: RunSettings = Field(default_factory=RunSettings)
    
    # Hardware configuration (optional)
    hardware: Optional[HardwareConfig] = Field(default=None, description="Hardware configuration (optional)")
    zabers: Optional[ZaberConfig] = Field(default=None, description="Zaber motor configuration (optional)")
    epics_control: Optional[EPICSConfig] = Field(default=None, description="EPICS control settings (optional)")
    
    # Global settings
    log_level: str = Field(default="INFO")

class JustServal(BaseModel):  
    """
    Only serval acquisition schema combining minimum software configurations for testing serval setup without hardware.
    """
    
    # Software configuration
    environment: WorkingDir = Field(default_factory=WorkingDir)
    serval: ServalConfig = Field(default_factory=ServalConfig)
    run_settings: RunSettings = Field(default_factory=RunSettings)

    # Global settings
    log_level: str = Field(default="INFO")
    
class JustCamera(BaseModel):  
    """
    Only camera acquisition schema combining minimum software configurations for testing camera setup without serval or hardware.
    """
    
    # Software configuration
    environment: WorkingDir = Field(default_factory=WorkingDir)
    run_settings: RunSettings = Field(default_factory=RunSettings)
    
    # Hardware configuration (optional)
    hardware: Optional[HardwareConfig] = Field(default=None, description="Hardware configuration (optional)")
    
    # Global settings
    log_level: str = Field(default="INFO")
    
class NoEpics(BaseModel):  
    """
    Acquisition schema combining all software and hardware configurations except EPICS.
    """
    
    # Software configuration
    environment: WorkingDir = Field(default_factory=WorkingDir)
    serval: ServalConfig = Field(default_factory=ServalConfig)
    run_settings: RunSettings = Field(default_factory=RunSettings)
    
    # Hardware configuration (optional)
    hardware: Optional[HardwareConfig] = Field(default=None, description="Hardware configuration (optional)")
    zabers: Optional[ZaberConfig] = Field(default=None, description="Zaber motor configuration (optional)")
    
    # Global settings
    log_level: str = Field(default="INFO")