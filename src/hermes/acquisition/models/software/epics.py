'''
Module for defining pydantic models for EPICS process variable configuration.
'''

from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any, Union

class EPICSPVConfig(BaseModel):
    """Configuration for a single EPICS Process Variable."""
    
    name: str = Field(description="PV name (e.g., 'BEAMLINE:SHUTTER:STATUS')")
    description: str = Field(default="", description="Human-readable description of the PV")
    
    # Data type and validation
    data_type: str = Field(default="float", description="Expected data type (float, int, string, enum)")
    units: Optional[str] = Field(default=None, description="Physical units (e.g., 'mm', 'V', 'mA')")
    
    # Value constraints
    min_value: Optional[float] = Field(default=None, description="Minimum allowed value")
    max_value: Optional[float] = Field(default=None, description="Maximum allowed value")
    enum_values: Optional[List[str]] = Field(default=None, description="Valid enum values")
    
    # Connection settings
    timeout: float = Field(default=5.0, description="Connection timeout in seconds")
    monitor: bool = Field(default=False, description="Enable monitoring for value changes")
    
class EPICSBeamlineConfig(BaseModel):
    """Configuration for beamline-related EPICS PVs."""
    
    # Beam monitoring
    beam_current: Optional[EPICSPVConfig] = Field(
        default_factory=lambda: EPICSPVConfig(
            name="BEAMLINE:CURRENT",
            description="Beam current",
            units="mA",
            min_value=0.0
        ),
        description="Beam current PV"
    )
    
    beam_energy: Optional[EPICSPVConfig] = Field(
        default_factory=lambda: EPICSPVConfig(
            name="BEAMLINE:ENERGY",
            description="Beam energy", 
            units="keV",
            min_value=0.0
        ),
        description="Beam energy PV"
    )
    
    # Shutters and safety
    shutter_status: Optional[EPICSPVConfig] = Field(
        default_factory=lambda: EPICSPVConfig(
            name="BEAMLINE:SHUTTER:STATUS",
            description="Shutter status",
            data_type="enum",
            enum_values=["OPEN", "CLOSED", "MOVING"]
        ),
        description="Main shutter status PV"
    )
    
    safety_interlock: Optional[EPICSPVConfig] = Field(
        default_factory=lambda: EPICSPVConfig(
            name="BEAMLINE:SAFETY:INTERLOCK",
            description="Safety interlock status",
            data_type="enum", 
            enum_values=["OK", "FAULT"]
        ),
        description="Safety interlock PV"
    )

class EPICSDetectorConfig(BaseModel):
    """Configuration for detector-related EPICS PVs."""
    
    # Temperature monitoring
    detector_temp: Optional[EPICSPVConfig] = Field(
        default_factory=lambda: EPICSPVConfig(
            name="DETECTOR:TEMPERATURE",
            description="Detector temperature",
            units="C",
            min_value=-50.0,
            max_value=50.0,
            monitor=True
        ),
        description="Detector temperature PV"
    )
    
    # High voltage
    hv_voltage: Optional[EPICSPVConfig] = Field(
        default_factory=lambda: EPICSPVConfig(
            name="DETECTOR:HV:VOLTAGE",
            description="High voltage setting",
            units="V",
            min_value=0.0,
            max_value=200.0
        ),
        description="High voltage PV"
    )
    
    hv_current: Optional[EPICSPVConfig] = Field(
        default_factory=lambda: EPICSPVConfig(
            name="DETECTOR:HV:CURRENT",
            description="High voltage current",
            units="uA",
            min_value=0.0,
            monitor=True
        ),
        description="High voltage current PV"
    )

class EPICSConfig(BaseModel):
    """Configuration for EPICS process variables used in acquisition."""
    
    # Connection settings
    ca_server_port: int = Field(default=5064, description="Channel Access server port")
    ca_repeater_port: int = Field(default=5065, description="Channel Access repeater port")
    epics_ca_addr_list: Optional[str] = Field(default=None, description="EPICS CA address list")
    epics_ca_auto_addr_list: bool = Field(default=True, description="Enable automatic address list")
    
    # Timeout settings
    default_timeout: float = Field(default=5.0, description="Default PV connection timeout")
    search_timeout: float = Field(default=1.0, description="PV search timeout")
    
    # Monitoring settings
    enable_monitoring: bool = Field(default=True, description="Enable PV monitoring")
    monitor_mask: str = Field(default="VALUE|ALARM", description="Monitor mask for subscriptions")
    
    # PV Groups
    beamline: EPICSBeamlineConfig = Field(default_factory=EPICSBeamlineConfig, description="Beamline PV configuration")
    detector: EPICSDetectorConfig = Field(default_factory=EPICSDetectorConfig, description="Detector PV configuration")
    
    # Custom PVs
    custom_pvs: Dict[str, EPICSPVConfig] = Field(default_factory=dict, description="Custom PV configurations")
    
    # Acquisition control
    acquisition_trigger_pv: Optional[str] = Field(default=None, description="PV to trigger acquisition start")
    acquisition_status_pv: Optional[str] = Field(default=None, description="PV to report acquisition status")
    
    class Config:
        validate_assignment = True
    
    def add_custom_pv(self, key: str, pv_config: EPICSPVConfig) -> None:
        """Add a custom PV configuration."""
        self.custom_pvs[key] = pv_config
    
    def get_all_pv_names(self) -> List[str]:
        """Get list of all configured PV names."""
        pv_names = []
        
        # Beamline PVs
        if self.beamline.beam_current:
            pv_names.append(self.beamline.beam_current.name)
        if self.beamline.beam_energy:
            pv_names.append(self.beamline.beam_energy.name)
        if self.beamline.shutter_status:
            pv_names.append(self.beamline.shutter_status.name)
        if self.beamline.safety_interlock:
            pv_names.append(self.beamline.safety_interlock.name)
            
        # Detector PVs
        if self.detector.detector_temp:
            pv_names.append(self.detector.detector_temp.name)
        if self.detector.hv_voltage:
            pv_names.append(self.detector.hv_voltage.name)
        if self.detector.hv_current:
            pv_names.append(self.detector.hv_current.name)
            
        # Custom PVs
        for pv_config in self.custom_pvs.values():
            pv_names.append(pv_config.name)
            
        # Control PVs
        if self.acquisition_trigger_pv:
            pv_names.append(self.acquisition_trigger_pv)
        if self.acquisition_status_pv:
            pv_names.append(self.acquisition_status_pv)
            
        return pv_names
    
    def get_monitored_pvs(self) -> List[str]:
        """Get list of PVs configured for monitoring."""
        monitored = []
        
        # Check beamline PVs
        for pv_config in [self.beamline.beam_current, self.beamline.beam_energy, 
                         self.beamline.shutter_status, self.beamline.safety_interlock]:
            if pv_config and pv_config.monitor:
                monitored.append(pv_config.name)
                
        # Check detector PVs
        for pv_config in [self.detector.detector_temp, self.detector.hv_voltage, 
                         self.detector.hv_current]:
            if pv_config and pv_config.monitor:
                monitored.append(pv_config.name)
                
        # Check custom PVs
        for pv_config in self.custom_pvs.values():
            if pv_config.monitor:
                monitored.append(pv_config.name)
                
        return monitored