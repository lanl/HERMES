"""
Camera control interface for HERMES acquisition system.

Defines the abstract interface for camera control that can be implemented
by both direct SERVAL HTTP clients and EPICS-mediated control services.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import asyncio
from pathlib import Path

from pydantic import BaseModel
from hermes.acquisition.models.hardware.tpx3Cam import (
    DetectorConfig, 
    TriggerModeType, 
    PolarityType,
    ChainModeType
)
from hermes.acquisition.models.software.serval import (
    ServalConfig,
    MeasurementConfig
)
from hermes.acquisition.services.base import ServiceHealthStatus


class CameraStatus(BaseModel):
    """Current status of the camera/detector system."""
    
    connected: bool
    acquiring: bool
    frame_count: int = 0
    elapsed_time: float = 0.0
    acquisition_rate: Optional[float] = None
    temperature: Optional[float] = None
    bias_voltage: Optional[float] = None
    bias_enabled: bool = False
    error_message: Optional[str] = None


class CameraHealthInfo(BaseModel):
    """Detailed health information for the camera system."""
    
    local_temperature: Optional[float] = None
    fpga_temperature: Optional[float] = None
    chip_temperatures: List[float] = []
    fan1_speed: Optional[int] = None
    fan2_speed: Optional[int] = None
    bias_voltage: Optional[float] = None
    humidity: Optional[int] = None
    power_status: Dict[str, Any] = {}


class CameraInfo(BaseModel):
    """Static information about the connected camera."""
    
    interface_name: Optional[str] = None
    software_version: Optional[str] = None
    firmware_version: Optional[str] = None
    pixel_count: Optional[int] = None
    number_of_chips: Optional[int] = None
    detector_type: Optional[str] = None
    serial_number: Optional[str] = None


class AcquisitionResult(BaseModel):
    """Result of an acquisition operation."""
    
    success: bool
    frame_count: int = 0
    total_time: float = 0.0
    average_rate: Optional[float] = None
    data_files: List[Path] = []
    error_message: Optional[str] = None


class CameraControlInterface(ABC):
    """
    Abstract interface for camera control operations.
    
    This interface can be implemented by:
    - Direct SERVAL HTTP client services
    - EPICS-mediated camera control services
    - Mock/simulation services for testing
    
    All implementations must provide the same async interface for
    transparent switching between control methods.
    """
    
    # ========================================================================
    # Connection and Service Management
    # ========================================================================
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Connect to the camera control system.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the camera control system."""
        pass
    
    @abstractmethod
    async def health_check(self) -> ServiceHealthStatus:
        """
        Check the health of the camera control service.
        
        Returns:
            ServiceHealthStatus with connection and health information
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """
        Quick check if camera control is available.
        
        Returns:
            True if camera control is available and responsive
        """
        pass
    
    # ========================================================================
    # Camera Discovery and Connection
    # ========================================================================
    
    @abstractmethod
    async def list_cameras(self) -> List[Dict[str, Any]]:
        """
        List available cameras/detectors.
        
        Returns:
            List of camera information dictionaries
        """
        pass
    
    @abstractmethod
    async def connect_camera(self, camera_id: Optional[str] = None) -> bool:
        """
        Connect to a specific camera or the first available camera.
        
        Args:
            camera_id: Optional specific camera identifier
            
        Returns:
            True if camera connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect_camera(self) -> bool:
        """
        Disconnect from the currently connected camera.
        
        Returns:
            True if disconnection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_camera_info(self) -> CameraInfo:
        """
        Get static information about the connected camera.
        
        Returns:
            CameraInfo with detector specifications and metadata
        """
        pass
    
    @abstractmethod
    async def get_camera_health(self) -> CameraHealthInfo:
        """
        Get current health/environmental information from the camera.
        
        Returns:
            CameraHealthInfo with temperatures, voltages, etc.
        """
        pass
    
    # ========================================================================
    # Camera Configuration
    # ========================================================================
    
    @abstractmethod
    async def get_camera_config(self) -> DetectorConfig:
        """
        Get current camera configuration.
        
        Returns:
            DetectorConfig with current settings
        """
        pass
    
    @abstractmethod
    async def set_camera_config(self, config: DetectorConfig) -> bool:
        """
        Apply camera configuration settings.
        
        Args:
            config: DetectorConfig with new settings
            
        Returns:
            True if configuration applied successfully, False otherwise
        """
        pass
    
    @abstractmethod
    async def load_calibration_files(self, bpc_file: Path, dacs_file: Path) -> bool:
        """
        Load calibration files (pixel configuration and DACs).
        
        Args:
            bpc_file: Path to pixel configuration (.bpc) file
            dacs_file: Path to DAC configuration (.dacs) file
            
        Returns:
            True if calibration files loaded successfully, False otherwise
        """
        pass
    
    # ========================================================================
    # Acquisition Control
    # ========================================================================
    
    @abstractmethod
    async def configure_acquisition(self, config: MeasurementConfig) -> bool:
        """
        Configure acquisition parameters (triggers, timing, etc.).
        
        Args:
            config: MeasurementConfig with acquisition settings
            
        Returns:
            True if configuration successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def configure_data_output(self, output_config: Dict[str, Any]) -> bool:
        """
        Configure data output destinations and formats.
        
        Args:
            output_config: Dictionary with destination configuration
            
        Returns:
            True if output configuration successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def start_acquisition(self) -> bool:
        """
        Start data acquisition.
        
        Returns:
            True if acquisition started successfully, False otherwise
        """
        pass
    
    @abstractmethod
    async def stop_acquisition(self) -> bool:
        """
        Stop data acquisition.
        
        Returns:
            True if acquisition stopped successfully, False otherwise
        """
        pass
    
    @abstractmethod
    async def start_preview(self) -> bool:
        """
        Start preview mode (live images without file output).
        
        Returns:
            True if preview started successfully, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_acquisition_status(self) -> CameraStatus:
        """
        Get current acquisition status.
        
        Returns:
            CameraStatus with current acquisition state
        """
        pass
    
    # ========================================================================
    # Data Access
    # ========================================================================
    
    @abstractmethod
    async def get_live_image(self) -> Optional[bytes]:
        """
        Get the latest live preview image.
        
        Returns:
            Image data as bytes, or None if no image available
        """
        pass
    
    @abstractmethod
    async def get_histogram_data(self) -> Optional[List[int]]:
        """
        Get current histogram data.
        
        Returns:
            Histogram data as list of integers, or None if not available
        """
        pass
    
    # ========================================================================
    # High-Level Workflows
    # ========================================================================
    
    async def quick_acquisition(
        self, 
        output_dir: Path,
        exposure_time: float = 0.1,
        n_triggers: int = 100,
        trigger_period: float = 0.2,
        trigger_mode: TriggerModeType = "EXTERNAL"
    ) -> AcquisitionResult:
        """
        Perform a complete quick acquisition with standard settings.
        
        Args:
            output_dir: Directory for output files
            exposure_time: Exposure time per frame in seconds
            n_triggers: Number of triggers/frames
            trigger_period: Time between triggers in seconds
            trigger_mode: Trigger mode (EXTERNAL, INTERNAL, etc.)
            
        Returns:
            AcquisitionResult with acquisition summary
        """
        try:
            # Create detector configuration
            detector_config = DetectorConfig(
                exposure_time=exposure_time,
                n_triggers=n_triggers,
                trigger_period=trigger_period,
                trigger_mode=trigger_mode
            )
            
            # Create measurement configuration
            measurement_config = MeasurementConfig()  # Use defaults
            
            # Setup data output
            output_config = {
                "Raw": [{
                    "Base": f"file://{output_dir}/raw/",
                    "FilePattern": "acquisition_%Y%m%d_%H%M%S.tpx3",
                    "SplitStrategy": "single_file"
                }],
                "Image": [{
                    "Base": f"file://{output_dir}/images/",
                    "FilePattern": "img_%05d.tiff",
                    "Format": "tiff",
                    "Mode": "tot"
                }]
            }
            
            # Execute acquisition workflow
            start_time = asyncio.get_event_loop().time()
            
            # Configure camera
            await self.set_camera_config(detector_config)
            await self.configure_acquisition(measurement_config)
            await self.configure_data_output(output_config)
            
            # Start acquisition
            success = await self.start_acquisition()
            if not success:
                return AcquisitionResult(
                    success=False,
                    error_message="Failed to start acquisition"
                )
            
            # Monitor progress
            while True:
                status = await self.get_acquisition_status()
                if not status.acquiring:
                    break
                await asyncio.sleep(0.5)
            
            end_time = asyncio.get_event_loop().time()
            total_time = end_time - start_time
            
            # Get final status
            final_status = await self.get_acquisition_status()
            
            return AcquisitionResult(
                success=True,
                frame_count=final_status.frame_count,
                total_time=total_time,
                average_rate=final_status.frame_count / total_time if total_time > 0 else None,
                data_files=[output_dir / "raw" / "acquisition.tpx3"]  # Simplified
            )
            
        except Exception as e:
            return AcquisitionResult(
                success=False,
                error_message=str(e)
            )
    
    async def calibrated_acquisition(
        self,
        output_dir: Path,
        bpc_file: Path,
        dacs_file: Path,
        exposure_time: float = 0.1,
        n_triggers: int = 100,
        bias_voltage: float = 100.0
    ) -> AcquisitionResult:
        """
        Perform acquisition with calibration files and bias settings.
        
        Args:
            output_dir: Directory for output files
            bpc_file: Pixel configuration file
            dacs_file: DAC configuration file
            exposure_time: Exposure time per frame in seconds
            n_triggers: Number of triggers/frames
            bias_voltage: Detector bias voltage
            
        Returns:
            AcquisitionResult with acquisition summary
        """
        try:
            # Load calibration files
            cal_success = await self.load_calibration_files(bpc_file, dacs_file)
            if not cal_success:
                return AcquisitionResult(
                    success=False,
                    error_message="Failed to load calibration files"
                )
            
            # Create configuration with bias settings
            detector_config = DetectorConfig(
                exposure_time=exposure_time,
                n_triggers=n_triggers,
                bias_voltage=bias_voltage,
                bias_enabled=True
            )
            
            # Use the quick acquisition workflow
            return await self.quick_acquisition(
                output_dir=output_dir,
                exposure_time=exposure_time,
                n_triggers=n_triggers
            )
            
        except Exception as e:
            return AcquisitionResult(
                success=False,
                error_message=str(e)
            )