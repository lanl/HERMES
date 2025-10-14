"""
Base service interface and common patterns for HERMES acquisition services.

This module provides the foundation for all service implementations, including
lifecycle management, health monitoring, error handling, and async context management.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, Union
import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic import BaseModel
from hermes.acquisition.logger import logger


class ServiceError(Exception):
    """Base exception for all service-related errors."""
    pass


class ConnectionError(ServiceError):
    """Raised when service cannot establish or maintain connection."""
    pass


class TimeoutError(ServiceError):
    """Raised when service operations exceed timeout limits."""
    pass


class ServiceNotAvailableError(ServiceError):
    """Raised when service is not available or not running."""
    pass


class ServiceHealthStatus(BaseModel):
    """Health status information for a service."""
    
    is_healthy: bool
    is_connected: bool
    last_check: float
    error_message: Optional[str] = None
    response_time_ms: Optional[float] = None
    additional_info: Dict[str, Any] = {}


class BaseServiceClient(ABC):
    """
    Abstract base class for all HERMES service clients.
    
    Provides common patterns for:
    - Connection management and health monitoring
    - Async context management
    - Error handling and logging
    - Timeout and retry logic
    """
    
    def __init__(self, config: BaseModel, name: Optional[str] = None):
        """
        Initialize base service client.
        
        Args:
            config: Pydantic configuration model for the service
            name: Optional name for logging and identification
        """
        self.config = config
        self.name = name or self.__class__.__name__
        self._connected = False
        self._last_health_check = 0.0
        self._health_check_interval = 30.0  # seconds
        self._connection_timeout = 10.0  # seconds
        self._request_timeout = 5.0  # seconds
        self._max_retries = 3
        self._retry_delay = 1.0  # seconds
        
        logger.debug(f"Initialized {self.name} service client")
    
    # ========================================================================
    # Abstract Methods - Must be implemented by subclasses
    # ========================================================================
    
    @abstractmethod
    async def _connect_impl(self) -> bool:
        """
        Implementation-specific connection logic.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def _disconnect_impl(self) -> None:
        """Implementation-specific disconnection logic."""
        pass
    
    @abstractmethod
    async def _health_check_impl(self) -> ServiceHealthStatus:
        """
        Implementation-specific health check logic.
        
        Returns:
            ServiceHealthStatus with current health information
        """
        pass
    
    # ========================================================================
    # Public Interface
    # ========================================================================
    
    async def connect(self) -> bool:
        """
        Connect to the service with timeout and error handling.
        
        Returns:
            True if connection successful, False otherwise
            
        Raises:
            ConnectionError: If connection fails after retries
            TimeoutError: If connection exceeds timeout
        """
        if self._connected:
            logger.debug(f"{self.name} already connected")
            return True
        
        logger.info(f"Connecting to {self.name} service...")
        
        try:
            # Use asyncio.wait_for for timeout control
            connected = await asyncio.wait_for(
                self._connect_impl(),
                timeout=self._connection_timeout
            )
            
            if connected:
                self._connected = True
                logger.success(f"Successfully connected to {self.name}")
            else:
                logger.error(f"Failed to connect to {self.name}")
            
            return connected
            
        except asyncio.TimeoutError:
            logger.error(f"Connection to {self.name} timed out after {self._connection_timeout}s")
            raise TimeoutError(f"Connection timeout for {self.name}")
        except Exception as e:
            logger.error(f"Connection error for {self.name}: {e}")
            raise ConnectionError(f"Failed to connect to {self.name}: {e}")
    
    async def disconnect(self) -> None:
        """Disconnect from the service."""
        if not self._connected:
            logger.debug(f"{self.name} already disconnected")
            return
        
        logger.info(f"Disconnecting from {self.name} service...")
        
        try:
            await self._disconnect_impl()
            self._connected = False
            logger.info(f"Disconnected from {self.name}")
        except Exception as e:
            logger.error(f"Error disconnecting from {self.name}: {e}")
            # Still mark as disconnected even if cleanup failed
            self._connected = False
    
    async def health_check(self, force: bool = False) -> ServiceHealthStatus:
        """
        Check service health with caching to avoid excessive checks.
        
        Args:
            force: If True, force a new health check regardless of cache
            
        Returns:
            ServiceHealthStatus with current health information
        """
        current_time = time.time()
        
        # Use cached result if recent enough and not forced
        if not force and (current_time - self._last_health_check) < self._health_check_interval:
            logger.debug(f"Using cached health status for {self.name}")
            # Return a basic cached status
            return ServiceHealthStatus(
                is_healthy=self._connected,
                is_connected=self._connected,
                last_check=self._last_health_check
            )
        
        logger.debug(f"Performing health check for {self.name}")
        
        try:
            start_time = time.time()
            status = await asyncio.wait_for(
                self._health_check_impl(),
                timeout=self._request_timeout
            )
            response_time = (time.time() - start_time) * 1000  # ms
            
            status.response_time_ms = response_time
            status.last_check = current_time
            self._last_health_check = current_time
            
            logger.debug(f"{self.name} health check: {status.is_healthy}")
            return status
            
        except asyncio.TimeoutError:
            logger.warning(f"Health check timeout for {self.name}")
            return ServiceHealthStatus(
                is_healthy=False,
                is_connected=False,
                last_check=current_time,
                error_message="Health check timeout"
            )
        except Exception as e:
            logger.error(f"Health check error for {self.name}: {e}")
            return ServiceHealthStatus(
                is_healthy=False,
                is_connected=False,
                last_check=current_time,
                error_message=str(e)
            )
    
    async def is_available(self) -> bool:
        """
        Quick check if service is available and responsive.
        
        Returns:
            True if service is available, False otherwise
        """
        try:
            status = await self.health_check()
            return status.is_healthy and status.is_connected
        except Exception:
            return False
    
    @property
    def is_connected(self) -> bool:
        """Check if service is currently connected."""
        return self._connected
    
    # ========================================================================
    # Async Context Manager Support
    # ========================================================================
    
    async def __aenter__(self):
        """Async context manager entry - connect to service."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - disconnect from service."""
        await self.disconnect()
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    async def with_retry(self, operation, *args, **kwargs) -> Any:
        """
        Execute an operation with retry logic.
        
        Args:
            operation: Async function to execute
            *args: Arguments for the operation
            **kwargs: Keyword arguments for the operation
            
        Returns:
            Result of the operation
            
        Raises:
            ServiceError: If all retries fail
        """
        last_exception = None
        
        for attempt in range(self._max_retries + 1):
            try:
                logger.debug(f"{self.name} operation attempt {attempt + 1}")
                return await operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                logger.warning(f"{self.name} operation failed (attempt {attempt + 1}): {e}")
                
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_delay * (attempt + 1))
                else:
                    logger.error(f"{self.name} operation failed after {self._max_retries + 1} attempts")
        
        raise ServiceError(f"Operation failed after {self._max_retries + 1} attempts: {last_exception}")
    
    def configure_timeouts(self, connection: float = None, request: float = None):
        """
        Configure timeout values for the service.
        
        Args:
            connection: Connection timeout in seconds
            request: Request timeout in seconds
        """
        if connection is not None:
            self._connection_timeout = connection
            logger.debug(f"{self.name} connection timeout set to {connection}s")
        
        if request is not None:
            self._request_timeout = request
            logger.debug(f"{self.name} request timeout set to {request}s")
    
    def configure_retry(self, max_retries: int = None, delay: float = None):
        """
        Configure retry behavior for the service.
        
        Args:
            max_retries: Maximum number of retry attempts
            delay: Base delay between retries in seconds
        """
        if max_retries is not None:
            self._max_retries = max_retries
            logger.debug(f"{self.name} max retries set to {max_retries}")
        
        if delay is not None:
            self._retry_delay = delay
            logger.debug(f"{self.name} retry delay set to {delay}s")


class ProcessManagedService(BaseServiceClient):
    """
    Base class for services that manage external processes.
    
    Extends BaseServiceClient with process lifecycle management,
    useful for services like SERVAL that run as separate processes.
    """
    
    def __init__(self, config: BaseModel, name: Optional[str] = None):
        super().__init__(config, name)
        self._process: Optional[asyncio.subprocess.Process] = None
        self._process_monitor_task: Optional[asyncio.Task] = None
        self._auto_restart = True
        self._startup_timeout = 30.0  # seconds
    
    @abstractmethod
    async def _build_process_command(self) -> list[str]:
        """
        Build the command line arguments to start the process.
        
        Returns:
            List of command arguments
        """
        pass
    
    @abstractmethod
    async def _verify_process_ready(self) -> bool:
        """
        Verify that the process is ready to accept connections.
        
        Returns:
            True if process is ready, False otherwise
        """
        pass
    
    async def start_process(self) -> bool:
        """
        Start the managed process.
        
        Returns:
            True if process started successfully, False otherwise
        """
        if self._process and self._process.returncode is None:
            logger.debug(f"{self.name} process already running")
            return True
        
        logger.info(f"Starting {self.name} process...")
        
        try:
            command = await self._build_process_command()
            logger.debug(f"Starting command: {' '.join(command)}")
            
            # Start the process
            self._process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL
            )
            
            # Wait for process to be ready
            ready = await asyncio.wait_for(
                self._wait_for_process_ready(),
                timeout=self._startup_timeout
            )
            
            if ready:
                logger.success(f"{self.name} process started successfully (PID: {self._process.pid})")
                
                # Start monitoring task
                if self._auto_restart:
                    self._process_monitor_task = asyncio.create_task(self._monitor_process())
                
                return True
            else:
                logger.error(f"{self.name} process failed to become ready")
                await self.stop_process()
                return False
                
        except asyncio.TimeoutError:
            logger.error(f"{self.name} process startup timeout after {self._startup_timeout}s")
            await self.stop_process()
            return False
        except Exception as e:
            logger.error(f"Failed to start {self.name} process: {e}")
            await self.stop_process()
            return False
    
    async def stop_process(self) -> None:
        """Stop the managed process."""
        if self._process_monitor_task:
            self._process_monitor_task.cancel()
            try:
                await self._process_monitor_task
            except asyncio.CancelledError:
                pass
            self._process_monitor_task = None
        
        if self._process:
            logger.info(f"Stopping {self.name} process (PID: {self._process.pid})")
            
            try:
                # Try graceful termination first
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    logger.info(f"{self.name} process terminated gracefully")
                except asyncio.TimeoutError:
                    # Force kill if graceful termination fails
                    logger.warning(f"Force killing {self.name} process")
                    self._process.kill()
                    await self._process.wait()
                    
            except Exception as e:
                logger.error(f"Error stopping {self.name} process: {e}")
            
            self._process = None
    
    async def _wait_for_process_ready(self) -> bool:
        """Wait for the process to be ready with periodic checks."""
        check_interval = 1.0  # seconds
        max_checks = int(self._startup_timeout / check_interval)
        
        for i in range(max_checks):
            # Check if process is still running
            if self._process.returncode is not None:
                logger.error(f"{self.name} process exited during startup (code: {self._process.returncode})")
                return False
            
            # Check if process is ready
            if await self._verify_process_ready():
                return True
            
            await asyncio.sleep(check_interval)
        
        return False
    
    async def _monitor_process(self) -> None:
        """Monitor the process and restart if it dies unexpectedly."""
        try:
            while True:
                if self._process is None:
                    break
                
                # Wait for process to exit
                await self._process.wait()
                
                if self._auto_restart:
                    logger.warning(f"{self.name} process died unexpectedly, restarting...")
                    await asyncio.sleep(2.0)  # Brief delay before restart
                    await self.start_process()
                else:
                    logger.info(f"{self.name} process exited")
                    break
                    
        except asyncio.CancelledError:
            logger.debug(f"Process monitor for {self.name} cancelled")
        except Exception as e:
            logger.error(f"Error in process monitor for {self.name}: {e}")
    
    @property
    def is_process_running(self) -> bool:
        """Check if the managed process is currently running."""
        return self._process is not None and self._process.returncode is None
    
    async def get_process_info(self) -> Dict[str, Any]:
        """
        Get information about the managed process.
        
        Returns:
            Dictionary with process information
        """
        if self._process is None:
            return {"status": "not_started"}
        
        return {
            "status": "running" if self._process.returncode is None else "exited",
            "pid": self._process.pid,
            "returncode": self._process.returncode
        }