"""
SERVAL process manager for HERMES acquisition system.

Handles the lifecycle of the SERVAL Java process, including:
- Process startup and shutdown
- Health monitoring and auto-restart
- Configuration and command-line argument building
- Integration with HERMES configuration system
"""

import asyncio
import socket
from pathlib import Path
from typing import Optional, List, Dict, Any
import aiohttp
import time

from pydantic import BaseModel, Field
from hermes.acquisition.logger import logger
from hermes.acquisition.models.software.serval import ServalConfig
from hermes.acquisition.services.base import ProcessManagedService, ServiceHealthStatus
from hermes.acquisition.services.exceptions import ServalProcessError, ServalAPIError


class ServalProcessConfig(BaseModel):
    """Configuration for SERVAL process management."""
    
    # SERVAL executable configuration
    java_executable: str = Field(default="java", description="Java executable path")
    serval_jar_path: Optional[Path] = Field(default=None, description="Path to SERVAL JAR file (auto-discovered if None)")
    
    # Process management
    startup_timeout: float = Field(default=60.0, description="Time to wait for SERVAL startup (seconds)")
    health_check_interval: float = Field(default=10.0, description="Health check interval (seconds)")
    auto_restart: bool = Field(default=True, description="Automatically restart on process failure")
    require_camera_connection: bool = Field(default=True, description="Require camera connection for successful startup")
    camera_connection_timeout: float = Field(default=30.0, description="Time to wait for camera connection before shutdown (seconds)")
    
    # SERVAL-specific options
    log_level: Optional[str] = Field(default=None, description="SERVAL log level")
    additional_jvm_args: List[str] = Field(default_factory=list, description="Additional JVM arguments")
    additional_serval_args: List[str] = Field(default_factory=list, description="Additional SERVAL arguments")
    
    @classmethod
    def from_serval_config(cls, serval_config: ServalConfig, **overrides) -> "ServalProcessConfig":
        """
        Create process config from existing ServalConfig model.
        
        Args:
            serval_config: Existing SERVAL configuration
            **overrides: Additional process-specific overrides
            
        Returns:
            ServalProcessConfig with settings from ServalConfig
        """
        # Extract process-relevant settings from ServalConfig
        config_data = {
            # Don't add host/port as additional args since SERVAL 2.1.6 doesn't support them
            "additional_serval_args": []
        }
        
        # Add SERVAL path if provided
        if serval_config.path_to_serval:
            # Find the JAR file in the provided path
            serval_path = Path(serval_config.path_to_serval)
            jar_files = list(serval_path.glob("*.jar"))
            if jar_files:
                config_data["serval_jar_path"] = jar_files[0]  # Use first JAR found
        
        # Apply any overrides
        config_data.update(overrides)
        
        return cls(**config_data)


class ServalProcessManager(ProcessManagedService):
    """
    Manages the SERVAL Java process lifecycle.
    
    Responsibilities:
    - Start and stop SERVAL process
    - Monitor process health
    - Verify SERVAL API availability  
    - Handle automatic restarts
    - Manage process configuration
    """
    
    def __init__(self, process_config: ServalProcessConfig, serval_config: ServalConfig):
        """
        Initialize SERVAL process manager.
        
        Args:
            process_config: Configuration for process management
            serval_config: SERVAL application configuration
        """
        super().__init__(process_config, "SERVAL_Process")
        self.process_config = process_config
        self.serval_config = serval_config
        
        # Set timeouts from configuration
        self._startup_timeout = process_config.startup_timeout
        self._auto_restart = process_config.auto_restart
        
        # HTTP session for health checks
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Discovery and validation state
        self._discovered_jar_path: Optional[Path] = None
        self._camera_connected: bool = False
        self._startup_output: str = ""
        self._camera_timeout_task: Optional[asyncio.Task] = None
        self._shutdown_due_to_camera_timeout: bool = False
        
        logger.info(f"SERVAL process manager initialized")
        if process_config.serval_jar_path:
            logger.info(f"Using specified JAR path: {process_config.serval_jar_path}")
        else:
            logger.info("SERVAL JAR path will be auto-discovered on startup")
        
        if process_config.require_camera_connection:
            logger.info(f"Camera connection required within {process_config.camera_connection_timeout}s")
    
    # ========================================================================
    # ProcessManagedService Implementation
    # ========================================================================
    
    async def _discover_serval_jar(self) -> Path:
        """
        Get the SERVAL JAR path, using cached result if available.
        
        Returns:
            Path to SERVAL JAR file
            
        Raises:
            ServalProcessError: If no valid SERVAL JAR found
        """
        # Use cached discovery result if available from previous validation
        if self._discovered_jar_path and self._discovered_jar_path.exists():
            logger.debug(f"Using cached SERVAL JAR path: {self._discovered_jar_path}")
            return self._discovered_jar_path
        
        logger.info("Running SERVAL discovery process...")
        
        # Step 1 & 2: Discover SERVAL installations
        jar_path = await find_serval_jar(
            user_provided_path=Path(self.serval_config.path_to_serval) if self.serval_config.path_to_serval else None
        )
        
        if jar_path is None:
            # Also check if user provided path in serval_config
            if self.serval_config.path_to_serval:
                user_path = Path(self.serval_config.path_to_serval)
                logger.info(f"Trying SERVAL path from config: {user_path}")
                jar_path = await find_serval_jar(user_provided_path=user_path)
        
        if jar_path is None:
            raise ServalProcessError(
                "No valid SERVAL JAR file found. Please ensure SERVAL is installed in "
                "/opt/serval/ or provide a valid path in the configuration."
            )
        
        self._discovered_jar_path = jar_path
        logger.info(f"SERVAL JAR discovered: {jar_path}")
        return jar_path
    
    async def _build_process_command(self) -> List[str]:
        """
        Build the command line to start SERVAL.
        
        Returns:
            List of command arguments
        """
        # Step 1-2: Discover SERVAL JAR if not provided
        if self.process_config.serval_jar_path:
            jar_path = self.process_config.serval_jar_path
        else:
            jar_path = await self._discover_serval_jar()
        
        command = [self.process_config.java_executable]
        
        # Add JVM arguments
        command.extend(self.process_config.additional_jvm_args)
        
        # Add SERVAL system properties for version 2.1.6
        # These are passed as -D properties to Java, not as --flags to SERVAL
        command.extend([f"-DhttpPort={self.serval_config.port}"])
        
        # Add JAR file
        command.extend(["-jar", str(jar_path)])
        
        # Add SERVAL-specific arguments (but avoid unsupported flags)
        # Version 2.1.6 doesn't support --host or --port flags
        # Instead, it uses system properties
        
        # Add any additional SERVAL arguments that are actually supported
        for arg in self.process_config.additional_serval_args:
            # Skip host/port args since they're not supported in 2.1.6
            if not any(skip in arg for skip in ["--host", "--port"]):
                command.append(arg)
        
        logger.debug(f"SERVAL command: {' '.join(command)}")
        return command
    
    async def _verify_process_ready(self) -> bool:
        """
        Verify that SERVAL process is ready by checking HTTP API and camera connection.
        Implements step 4: Check if camera is connected.
        
        Returns:
            True if SERVAL is ready and camera is connected (if required)
        """
        try:
            # First check if port is open
            if not await self._check_port_open():
                return False
            
            # Then check HTTP API
            api_ready = await self._check_api_responding()
            if not api_ready:
                return False
            
            # Step 4: Check camera connection if required
            if self.process_config.require_camera_connection:
                camera_connected = await self._check_camera_connection()
                if not camera_connected:
                    logger.warning("SERVAL is running but camera is not connected")
                    if self.process_config.require_camera_connection:
                        return False
                self._camera_connected = camera_connected
            else:
                self._camera_connected = True  # Not required, assume OK
            
            return True
            
        except Exception as e:
            logger.debug(f"SERVAL readiness check failed: {e}")
            return False
    
    async def _check_camera_connection(self) -> bool:
        """
        Check if camera is connected by examining SERVAL output and API status.
        Implements step 4: Check camera connection from output.
        
        Returns:
            True if camera is connected
        """
        # Method 1: Check startup output for camera connection indicators
        if self._startup_output:
            output_indicates_camera = await check_camera_connection_from_output(self._startup_output)
            if output_indicates_camera:
                logger.info("Camera connection confirmed from SERVAL startup output")
                self._camera_connected = True
                return True
        
        # Method 2: Check SERVAL API for camera status
        try:
            dashboard_info = await self._get_serval_dashboard_info()
            if dashboard_info:
                # Look for camera/detector status in dashboard
                detector_status = dashboard_info.get("detector", {})
                camera_status = dashboard_info.get("camera", {})
                
                # Check various possible status indicators
                if detector_status.get("connected") is True:
                    logger.info("Camera connection confirmed from SERVAL dashboard")
                    self._camera_connected = True
                    return True
                
                if camera_status.get("connected") is True:
                    logger.info("Camera connection confirmed from SERVAL camera status")
                    self._camera_connected = True
                    return True
                
                # Check for Timepix3 specific indicators
                if "timepix3" in str(dashboard_info).lower():
                    logger.info("Timepix3 detector detected in SERVAL dashboard")
                    self._camera_connected = True
                    return True
        
        except Exception as e:
            logger.debug(f"Failed to check camera status via API: {e}")
        
        # Method 3: Try to access camera-specific endpoints
        try:
            # Try to get detector info endpoint
            url = f"{self.get_api_base_url()}/detector/info"
            if self._session:
                async with self._session.get(url) as response:
                    if response.status == 200:
                        detector_info = await response.json()
                        if detector_info and "error" not in str(detector_info).lower():
                            logger.info("Camera connection confirmed from detector info endpoint")
                            self._camera_connected = True
                            return True
        except Exception as e:
            logger.debug(f"Failed to check detector info endpoint: {e}")
        
        # Method 4: Check for absence of connection failure messages in recent output
        # This is a negative check - if we're not seeing failure messages, camera might be connected
        recent_output = self._startup_output[-1000:] if self._startup_output else ""
        failure_patterns = [
            "failed to reconnect to detector",
            "connect timed out", 
            "connection failed",
            "timeout connecting"
        ]
        
        # Only consider this method if we have some reasonable output
        if len(recent_output) > 100:
            has_failure = any(pattern in recent_output.lower() for pattern in failure_patterns)
            if not has_failure:
                # No recent failures - might indicate connection success
                logger.debug("No recent camera connection failures detected")
                # Don't set _camera_connected = True here, as this is just absence of failure
        
        logger.debug("No clear indication of camera connection found")
        return False
    
    async def start_process_with_output_capture(self) -> bool:
        """
        Start SERVAL process with output capture for camera connection checking.
        Enhanced version of start_process that implements step 3 and 4.
        
        Returns:
            True if process started successfully and camera connected (if required)
        """
        if self.is_process_running:
            logger.info("SERVAL process is already running")
            return True
        
        logger.info("Starting SERVAL process...")
        
        try:
            # Reset timeout state
            self._shutdown_due_to_camera_timeout = False
            
            # Build command (includes step 1-2: discovery)
            command = await self._build_process_command()
            
            # Step 3: Start SERVAL process with output capture
            self._process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # Combine stderr with stdout
                cwd=None
            )
            
            logger.info(f"SERVAL process started with PID {self._process.pid}")
            
            # Start camera connection timeout monitor if required
            if self.process_config.require_camera_connection:
                self._camera_timeout_task = asyncio.create_task(
                    self._monitor_camera_connection_timeout()
                )
            
            # Capture initial output for camera connection checking
            await self._capture_startup_output()
            
            # Wait for process to be ready (includes step 4: camera check)
            if await self.wait_for_ready():
                # Cancel timeout monitor if camera connected
                if self._camera_timeout_task and not self._camera_timeout_task.done():
                    self._camera_timeout_task.cancel()
                    try:
                        await self._camera_timeout_task
                    except asyncio.CancelledError:
                        pass
                
                logger.info("SERVAL process started successfully")
                if self._camera_connected:
                    logger.info("Camera connection verified")
                elif not self.process_config.require_camera_connection:
                    logger.info("SERVAL started without camera requirement")
                
                return True
            else:
                logger.error("SERVAL process failed to become ready")
                await self.stop_process()
                return False
                
        except Exception as e:
            logger.error(f"Failed to start SERVAL process: {e}")
            if self._process:
                await self.stop_process()
            return False
    
    async def _capture_startup_output(self, timeout: float = 10.0) -> None:
        """
        Capture SERVAL startup output for camera connection analysis.
        
        Args:
            timeout: Maximum time to capture output
        """
        if not self._process or not self._process.stdout:
            return
        
        logger.debug("Capturing SERVAL startup output...")
        output_lines = []
        
        try:
            async with asyncio.timeout(timeout):
                while True:
                    line = await self._process.stdout.readline()
                    if not line:
                        break
                    
                    line_text = line.decode('utf-8', errors='ignore').strip()
                    if line_text:
                        output_lines.append(line_text)
                        logger.debug(f"SERVAL: {line_text}")
                        
                        # Stop capturing if we see server startup messages
                        if any(phrase in line_text.lower() for phrase in 
                               ["server started", "listening on", "ready to accept"]):
                            break
                            
        except asyncio.TimeoutError:
            logger.debug("Startup output capture timed out")
        except Exception as e:
            logger.debug(f"Error capturing startup output: {e}")
        
        self._startup_output = "\n".join(output_lines)
        logger.debug(f"Captured {len(output_lines)} lines of startup output")
    
    async def _monitor_camera_connection_timeout(self) -> None:
        """
        Monitor camera connection and shutdown SERVAL if timeout exceeded.
        This runs as a background task during startup.
        """
        timeout = self.process_config.camera_connection_timeout
        logger.info(f"Starting camera connection timeout monitor ({timeout}s)")
        
        start_time = time.time()
        
        try:
            while (time.time() - start_time) < timeout:
                # Check if camera connected
                if self._camera_connected:
                    logger.info("Camera connected - cancelling timeout monitor")
                    return
                
                # Check if process is still running
                if not self.is_process_running:
                    logger.warning("SERVAL process stopped - cancelling timeout monitor")
                    return
                
                # Wait a bit before checking again
                await asyncio.sleep(2.0)
            
            # Timeout exceeded - shutdown SERVAL
            elapsed = time.time() - start_time
            logger.warning(f"Camera connection timeout exceeded ({elapsed:.1f}s) - shutting down SERVAL")
            self._shutdown_due_to_camera_timeout = True
            
            # Force shutdown
            await self._shutdown_due_to_timeout()
            
        except asyncio.CancelledError:
            logger.debug("Camera connection timeout monitor cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in camera connection timeout monitor: {e}")
    
    async def _shutdown_due_to_timeout(self) -> None:
        """Shutdown SERVAL due to camera connection timeout."""
        logger.error("Shutting down SERVAL due to camera connection timeout")
        
        # Try graceful shutdown first
        try:
            if await self._check_api_responding():
                await self.shutdown_serval_gracefully()
                await asyncio.sleep(2.0)
        except Exception as e:
            logger.debug(f"Graceful shutdown failed: {e}")
        
        # Force termination
        if self.is_process_running:
            await self.stop_process()
            logger.info("SERVAL process terminated due to camera timeout")
    
    @property
    def shutdown_due_to_camera_timeout(self) -> bool:
        """Check if SERVAL was shut down due to camera connection timeout."""
        return self._shutdown_due_to_camera_timeout
    
    async def _connect_impl(self) -> bool:
        """
        Connect to SERVAL (start process if needed).
        
        Returns:
            True if connection successful
        """
        # Create HTTP session
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self._request_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        
        # Start process if not running
        if not self.is_process_running:
            success = await self.start_process()
            if not success:
                return False
        
        # Verify API is responding
        return await self._check_api_responding()
    
    async def _disconnect_impl(self) -> None:
        """Disconnect from SERVAL (stop process and cleanup)."""
        # Cancel timeout monitoring task
        if self._camera_timeout_task and not self._camera_timeout_task.done():
            self._camera_timeout_task.cancel()
            try:
                await self._camera_timeout_task
            except asyncio.CancelledError:
                pass
        
        # Close HTTP session
        if self._session:
            await self._session.close()
            self._session = None
        
        # Stop process
        await self.stop_process()
    
    async def _health_check_impl(self) -> ServiceHealthStatus:
        """
        Check SERVAL health status.
        
        Returns:
            ServiceHealthStatus with current health information
        """
        start_time = time.time()
        
        try:
            # Check if process is running
            if not self.is_process_running:
                return ServiceHealthStatus(
                    is_healthy=False,
                    is_connected=False,
                    last_check=start_time,
                    error_message="SERVAL process not running"
                )
            
            # Check API responsiveness
            if await self._check_api_responding():
                response_time = (time.time() - start_time) * 1000
                
                # Get additional health info from SERVAL dashboard
                additional_info = await self._get_serval_dashboard_info()
                
                return ServiceHealthStatus(
                    is_healthy=True,
                    is_connected=True,
                    last_check=start_time,
                    response_time_ms=response_time,
                    additional_info=additional_info
                )
            else:
                return ServiceHealthStatus(
                    is_healthy=False,
                    is_connected=False,
                    last_check=start_time,
                    error_message="SERVAL API not responding"
                )
                
        except Exception as e:
            return ServiceHealthStatus(
                is_healthy=False,
                is_connected=False,
                last_check=start_time,
                error_message=str(e)
            )
    
    # ========================================================================
    # SERVAL-Specific Methods
    # ========================================================================
    
    async def _check_port_open(self) -> bool:
        """
        Check if SERVAL port is open.
        
        Returns:
            True if port is open and accepting connections
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.serval_config.host, self.serval_config.port),
                timeout=2.0
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (OSError, asyncio.TimeoutError):
            return False
    
    async def _check_api_responding(self) -> bool:
        """
        Check if SERVAL HTTP API is responding.
        
        Returns:
            True if API returns welcome message
        """
        # Create session if not exists
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self._request_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        
        try:
            url = f"http://{self.serval_config.host}:{self.serval_config.port}/"
            async with self._session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    # SERVAL 2.1.6 should return some HTML content
                    # Check for case-insensitive "serval" or other indicators
                    text_lower = text.lower()
                    return len(text) > 0 and ("serval" in text_lower or "timepix" in text_lower or "<html>" in text_lower or "amsterdam scientific" in text_lower)
                return False
        except Exception as e:
            logger.debug(f"SERVAL API check failed: {e}")
            return False
    
    async def _get_serval_dashboard_info(self) -> Dict[str, Any]:
        """
        Get additional information from SERVAL dashboard.
        
        Returns:
            Dictionary with SERVAL status information
        """
        if self._session is None:
            return {}
        
        try:
            url = f"http://{self.serval_config.host}:{self.serval_config.port}/dashboard"
            async with self._session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                return {}
        except Exception:
            return {}
    
    # ========================================================================
    # Public Interface
    # ========================================================================
    
    @property
    def camera_connected(self) -> bool:
        """Check if camera is connected to SERVAL."""
        return self._camera_connected
    
    @property
    def discovered_jar_path(self) -> Optional[Path]:
        """Get the discovered SERVAL JAR path."""
        return self._discovered_jar_path
    
    @property
    def startup_output(self) -> str:
        """Get captured SERVAL startup output."""
        return self._startup_output
    
    async def discover_and_validate_serval(self) -> dict:
        """
        Run the complete SERVAL discovery and validation process without starting.
        
        Returns:
            Dictionary with discovery results and validation status
        """
        result = {
            "jar_found": False,
            "jar_path": None,
            "installations_found": [],
            "java_available": False,
            "validation_errors": []
        }
        
        try:
            # Check Java installation
            result["java_available"] = validate_java_installation()
            if not result["java_available"]:
                result["validation_errors"].append("Java not found or not working")
            
            # Discover installations once
            installations = await discover_serval_installations()
            result["installations_found"] = [str(inst) for inst in installations]
            
            # Try to find JAR using the discovered installations (avoids re-discovery)
            jar_path = await find_serval_jar(
                user_provided_path=Path(self.serval_config.path_to_serval) if self.serval_config.path_to_serval else None,
                discovered_installations=installations  # Pass pre-discovered installations
            )
            
            if jar_path:
                result["jar_found"] = True
                result["jar_path"] = str(jar_path)
                self._discovered_jar_path = jar_path  # Cache the result for later use
                logger.info(f"SERVAL discovery completed successfully - using JAR: {jar_path}")
            else:
                result["validation_errors"].append("No valid SERVAL JAR file found")
                
        except Exception as e:
            result["validation_errors"].append(f"Discovery failed: {str(e)}")
            logger.error(f"SERVAL discovery/validation failed: {e}")
        
        return result
    
    async def start_with_full_validation(self) -> bool:
        """
        Start SERVAL with complete discovery, validation, and camera checking.
        This implements the full 4-step process.
        
        Returns:
            True if SERVAL started successfully with camera connected
        """
        logger.info("Starting SERVAL with full validation (4-step process)...")
        
        # Run discovery and validation first - this caches the result
        validation_result = await self.discover_and_validate_serval()
        
        if not validation_result["jar_found"]:
            logger.error("SERVAL validation failed:")
            for error in validation_result["validation_errors"]:
                logger.error(f"  - {error}")
            return False
        
        # Start process with output capture and camera checking
        # The JAR path is now cached in self._discovered_jar_path
        success = await self.start_process_with_output_capture()
        
        if success:
            logger.info("SERVAL startup process completed successfully")
            if self.process_config.require_camera_connection:
                if self._camera_connected:
                    logger.info("✓ Camera connection verified")
                else:
                    logger.warning("⚠ Camera connection could not be verified")
        else:
            logger.error("SERVAL startup failed")
        
        return success
    
    async def get_serval_version(self) -> Optional[str]:
        """
        Get SERVAL version information.
        
        Returns:
            Version string if available, None otherwise
        """
        try:
            dashboard_info = await self._get_serval_dashboard_info()
            return dashboard_info.get("server", {}).get("version")
        except Exception:
            return None
    
    async def wait_for_ready(self, timeout: float = None) -> bool:
        """
        Wait for SERVAL to be ready and responding.
        
        Args:
            timeout: Maximum time to wait (uses startup_timeout if None)
            
        Returns:
            True if SERVAL becomes ready within timeout
        """
        if timeout is None:
            timeout = self._startup_timeout
        
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            if await self._check_api_responding():
                return True
            await asyncio.sleep(1.0)
        
        return False
    
    def get_api_base_url(self) -> str:
        """
        Get the base URL for SERVAL API calls.
        
        Returns:
            Base URL string
        """
        return self.serval_config.base_url
    
    async def shutdown_serval_gracefully(self) -> bool:
        """
        Shutdown SERVAL using its API shutdown endpoint.
        
        Returns:
            True if shutdown command sent successfully
        """
        if self._session is None:
            return False
        
        try:
            url = f"{self.get_api_base_url()}/server/shutdown"
            async with self._session.get(url) as response:
                success = response.status == 200
                if success:
                    logger.info("SERVAL shutdown command sent")
                    # Wait a moment for graceful shutdown
                    await asyncio.sleep(2.0)
                return success
        except Exception as e:
            logger.error(f"Failed to send SERVAL shutdown command: {e}")
            return False
    
    # ========================================================================
    # Enhanced Process Management
    # ========================================================================
    
    async def stop_process(self) -> None:
        """Stop SERVAL process with graceful shutdown attempt."""
        if self._process is None:
            return
        
        logger.info("Stopping SERVAL process...")
        
        # Try graceful shutdown via API first
        if await self._check_api_responding():
            graceful_success = await self.shutdown_serval_gracefully()
            if graceful_success:
                # Wait for process to exit
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=10.0)
                    logger.info("SERVAL shut down gracefully")
                    self._process = None
                    # Clean up HTTP session after graceful shutdown
                    if self._session:
                        await self._session.close()
                        self._session = None
                    return
                except asyncio.TimeoutError:
                    logger.warning("SERVAL graceful shutdown timed out")
        
        # Clean up HTTP session before forceful termination
        if self._session:
            await self._session.close()
            self._session = None
        
        # Fall back to parent class termination
        await super().stop_process()
    
    async def restart_process(self) -> bool:
        """
        Restart SERVAL process.
        
        Returns:
            True if restart successful
        """
        logger.info("Restarting SERVAL process...")
        await self.stop_process()
        await asyncio.sleep(2.0)  # Brief pause
        return await self.start_process()


# ========================================================================
# SERVAL Discovery and Validation
# ========================================================================

class ServalVersion:
    """Represents a discovered SERVAL installation."""
    
    def __init__(self, path: Path, version: str = None):
        self.path = path
        self.version = version or "unknown"
        self.jar_file = self._find_jar_file()
    
    def _find_jar_file(self) -> Optional[Path]:
        """Find the JAR file in this SERVAL installation."""
        # Look for various SERVAL JAR naming patterns
        patterns = [
            "serval-*.jar",
            "serv-*.jar", 
            "SERVAL-*.jar",
            "serval.jar"
        ]
        
        for pattern in patterns:
            jar_files = list(self.path.glob(pattern))
            if jar_files:
                # If multiple JARs, prefer the one with highest version number
                return max(jar_files, key=lambda p: self._extract_version_from_name(p.name))
        
        return None
    
    def _extract_version_from_name(self, filename: str) -> tuple:
        """Extract version tuple from JAR filename for comparison."""
        import re
        match = re.search(r'(\d+)\.(\d+)\.(\d+)', filename)
        if match:
            return tuple(int(x) for x in match.groups())
        return (0, 0, 0)
    
    @property
    def is_valid(self) -> bool:
        """Check if this SERVAL installation is valid."""
        return self.jar_file is not None and self.jar_file.exists()
    
    def __str__(self):
        return f"SERVAL {self.version} at {self.path}"


async def discover_serval_installations() -> List[ServalVersion]:
    """
    Discover SERVAL installations following the 4-step process:
    1. Look for SERVAL versions in /opt/serval/
    2. Check common installation locations
    3. Return ordered list of valid installations
    
    Returns:
        List of ServalVersion objects, ordered by preference
    """
    installations = []
    
    # Step 1: Check /opt/serval/ for multiple versions
    opt_serval = Path("/opt/serval")
    if opt_serval.exists() and opt_serval.is_dir():
        logger.info("Scanning /opt/serval/ for SERVAL installations...")
        
        # Look for version subdirectories
        for version_dir in opt_serval.iterdir():
            if version_dir.is_dir():
                version = ServalVersion(version_dir, version_dir.name)
                if version.is_valid:
                    installations.append(version)
                    logger.info(f"Found SERVAL installation: {version}")
        
        # Also check directly in /opt/serval/
        direct_version = ServalVersion(opt_serval)
        if direct_version.is_valid:
            installations.append(direct_version)
            logger.info(f"Found SERVAL installation: {direct_version}")
    
    # Step 2: Check other common locations
    other_locations = [
        Path("/usr/local/serval"),
        Path.home() / "serval",
        Path.home() / "Programs" / "TPX3Cam" / "Serval",  # Common macOS location
        Path.cwd() / "serval",
        Path.cwd()
    ]
    
    for location in other_locations:
        if location.exists() and location.is_dir():
            # For directories like ~/Programs/TPX3Cam/Serval, check subdirectories too
            if "TPX3Cam" in str(location) or "Serval" in location.name:
                # Check subdirectories for version folders
                for subdir in location.iterdir():
                    if subdir.is_dir():
                        version = ServalVersion(subdir, subdir.name)
                        if version.is_valid:
                            if not any(inst.path.samefile(subdir) for inst in installations):
                                installations.append(version)
                                logger.info(f"Found SERVAL installation: {version}")
            
            # Also check the location directly
            version = ServalVersion(location)
            if version.is_valid:
                # Avoid duplicates
                if not any(inst.path.samefile(location) for inst in installations):
                    installations.append(version)
                    logger.info(f"Found SERVAL installation: {version}")
    
    if not installations:
        logger.warning("No SERVAL installations found in standard locations")
    
    return installations


async def find_serval_jar(user_provided_path: Optional[Path] = None, 
                         search_paths: List[Path] = None,
                         discovered_installations: Optional[List[ServalVersion]] = None) -> Optional[Path]:
    """
    Find SERVAL JAR file implementing the 4-step discovery process.
    
    Args:
        user_provided_path: User-specified path to SERVAL (step 2)
        search_paths: Additional paths to search
        discovered_installations: Pre-discovered installations to avoid re-discovery
        
    Returns:
        Path to SERVAL JAR file if found, None otherwise
    """
    # Step 2: If user provided a path, check that first
    if user_provided_path:
        logger.info(f"Checking user-provided SERVAL path: {user_provided_path}")
        user_version = ServalVersion(user_provided_path)
        if user_version.is_valid:
            logger.info(f"Using user-provided SERVAL: {user_version}")
            return user_version.jar_file
        else:
            logger.warning(f"User-provided SERVAL path is invalid: {user_provided_path}")
    
    # Step 1: Use pre-discovered installations or discover them
    if discovered_installations is not None:
        installations = discovered_installations
    else:
        installations = await discover_serval_installations()
    
    if installations:
        # Use the first valid installation (could add version preference logic here)
        best_installation = installations[0]
        logger.info(f"Selected SERVAL installation: {best_installation}")
        return best_installation.jar_file
    
    # Fallback: Check additional search paths if provided
    if search_paths:
        for search_path in search_paths:
            if search_path.exists() and search_path.is_dir():
                version = ServalVersion(search_path)
                if version.is_valid:
                    logger.info(f"Found SERVAL in additional search path: {version}")
                    return version.jar_file
    
    logger.error("No valid SERVAL JAR file found after complete search")
    return None


async def check_camera_connection_from_output(process_output: str) -> bool:
    """
    Check SERVAL process output to determine if camera is connected (step 4).
    
    Args:
        process_output: SERVAL startup output text
        
    Returns:
        True if camera connection is detected, False otherwise
    """
    # Common indicators of successful camera connection in SERVAL output
    success_patterns = [
        "camera connected",
        "timepix3 connected", 
        "detector connected",
        "tpx3 initialization successful",
        "camera ready",
        "detector ready"
    ]
    
    # Error patterns indicating no camera
    error_patterns = [
        "no camera found",
        "camera not found", 
        "no detector",
        "connection failed",
        "timeout connecting",
        "camera initialization failed"
    ]
    
    output_lower = process_output.lower()
    
    # Check for error patterns first
    for error_pattern in error_patterns:
        if error_pattern in output_lower:
            logger.warning(f"Camera connection issue detected: {error_pattern}")
            return False
    
    # Check for success patterns
    for success_pattern in success_patterns:
        if success_pattern in output_lower:
            logger.info(f"Camera connection confirmed: {success_pattern}")
            return True
    
    # If no explicit patterns found, we can't determine status
    logger.debug("No explicit camera connection status found in SERVAL output")
    return False


def validate_java_installation() -> bool:
    """
    Validate that Java is installed and accessible.
    
    Returns:
        True if Java is available, False otherwise
    """
    try:
        import subprocess
        result = subprocess.run(
            ["java", "-version"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        success = result.returncode == 0
        if success:
            logger.debug("Java installation validated")
        else:
            logger.error("Java not found or not working")
        return success
    except Exception as e:
        logger.error(f"Failed to validate Java installation: {e}")
        return False