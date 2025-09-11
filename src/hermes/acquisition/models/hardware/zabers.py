'''
Module for defining pydantic models for Zaber motor controller configuration.
'''

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ZaberMotorConfig(BaseModel):
    """Configuration for a single Zaber motor."""
    
    axis_id: int = Field(description="Motor axis identifier")
    name: str = Field(description="Motor name/description")
    
    # Physical limits
    min_position: float = Field(default=0.0, description="Minimum position in mm")
    max_position: float = Field(default=100.0, description="Maximum position in mm")
    home_position: float = Field(default=0.0, description="Home position in mm")
    
    # Motion parameters
    max_speed: float = Field(default=10.0, description="Maximum speed in mm/s")
    acceleration: float = Field(default=100.0, description="Acceleration in mm/s²")
    
class ZaberIOConfig(BaseModel):
    """Configuration for Zaber analog/digital I/O."""
    
    # Analog outputs
    analog_channels: Dict[int, str] = Field(
        default={1: "voltage_control", 2: "reference_signal"}, 
        description="Analog output channel assignments"
    )
    
    # Digital I/O
    digital_inputs: Dict[int, str] = Field(
        default={1: "trigger_input", 2: "safety_interlock"}, 
        description="Digital input channel assignments"
    )
    digital_outputs: Dict[int, str] = Field(
        default={1: "status_led", 2: "enable_signal"}, 
        description="Digital output channel assignments"
    )
    
    # Voltage ranges
    analog_voltage_range: tuple[float, float] = Field(
        default=(0.0, 5.0), 
        description="Analog output voltage range (min, max) in volts"
    )

class ZaberConfig(BaseModel):
    """Configuration for Zaber motor controller system."""
    
    # Connection settings
    port: Optional[str] = Field(default=None, description="Serial port (auto-detect if None)")
    baud_rate: int = Field(default=115200, description="Serial baud rate")
    timeout: float = Field(default=5.0, description="Communication timeout in seconds")
    
    # Device settings
    device_address: Optional[int] = Field(default=None, description="Device address (auto-select if None)")
    debug: bool = Field(default=False, description="Enable debug logging")
    
    # Motor configurations
    motors: List[ZaberMotorConfig] = Field(default_factory=list, description="Motor configurations")
    
    # I/O configuration
    io: ZaberIOConfig = Field(default_factory=ZaberIOConfig, description="Analog/Digital I/O configuration")
    
    # Connection retry settings
    max_retries: int = Field(default=3, description="Maximum connection retries")
    retry_delay: float = Field(default=1.0, description="Delay between retries in seconds")
    
    class Config:
        validate_assignment = True
        
    def add_motor(self, axis_id: int, name: str, **kwargs) -> None:
        """Add a motor configuration."""
        motor_config = ZaberMotorConfig(axis_id=axis_id, name=name, **kwargs)
        self.motors.append(motor_config)
        
    def get_motor_by_name(self, name: str) -> Optional[ZaberMotorConfig]:
        """Get motor configuration by name."""
        for motor in self.motors:
            if motor.name == name:
                return motor
        return None
        
    def get_motor_by_axis(self, axis_id: int) -> Optional[ZaberMotorConfig]:
        """Get motor configuration by axis ID."""
        for motor in self.motors:
            if motor.axis_id == axis_id:
                return motor
        return None