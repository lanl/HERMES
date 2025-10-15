"""
SERVAL HTTP client for direct API communication.

This service handles HTTP requests to the SERVAL REST API, providing:
- Dashboard and status monitoring
- Configuration management
- Camera control operations
- Data acquisition coordination

Works in conjunction with ServalProcessManager for complete SERVAL integration.
"""

import asyncio
import aiohttp
import json
from typing import Optional, Dict, Any, List
from pathlib import Path
import time

from pydantic import BaseModel, Field, ValidationError
from hermes.acquisition.logger import logger
from hermes.acquisition.models.software.serval import ServalConfig, Dashboard
from hermes.acquisition.services.base import BaseServiceClient, ServiceHealthStatus
from hermes.acquisition.services.exceptions import ServalAPIError, ConnectionError, TimeoutError


class ServalHTTPClient(BaseServiceClient):
    """
    HTTP client for SERVAL REST API communication.
    
    Provides direct access to SERVAL's HTTP endpoints with:
    - Type-safe request/response handling
    - Automatic retries and error handling
    - Connection management and health monitoring
    - Integration with HERMES configuration system
    """
    
    def __init__(self, serval_config: ServalConfig):
        """
        Initialize SERVAL HTTP client.
        
        Args:
            serval_config: SERVAL connection and HTTP configuration
        """
        super().__init__(serval_config, "SERVAL_HTTP")
        self.serval_config = serval_config
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_dashboard: Optional[Dashboard] = None
        
        # Set timeouts from configuration
        self._connection_timeout = self.serval_config.timeout
        self._request_timeout = self.serval_config.timeout
        self._max_retries = self.serval_config.max_retries
        self._retry_delay = self.serval_config.retry_delay
        self._health_check_interval = self.serval_config.health_check_interval
        
        logger.debug(f"SERVAL HTTP client initialized for {self.serval_config.base_url}")
    
    # ========================================================================
    # BaseServiceClient Implementation
    # ========================================================================
    
    async def _connect_impl(self) -> bool:
        """
        Establish HTTP session and verify SERVAL connectivity.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Create aiohttp session with timeout
            timeout = aiohttp.ClientTimeout(total=self._connection_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
            
            # Test connectivity with a simple GET request
            async with self._session.get(f"{self.serval_config.base_url}/dashboard") as response:
                if response.status == 200:
                    logger.info(f"Successfully connected to SERVAL at {self.serval_config.base_url}")
                    return True
                else:
                    logger.warning(f"SERVAL responded with status {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to connect to SERVAL: {e}")
            if self._session:
                await self._session.close()
                self._session = None
            return False
    
    async def _disconnect_impl(self) -> None:
        """Close HTTP session and cleanup resources."""
        if self._session:
            await self._session.close()
            self._session = None
            logger.debug("SERVAL HTTP session closed")
    
    async def _health_check_impl(self) -> ServiceHealthStatus:
        """
        Perform health check by requesting dashboard information.
        
        Returns:
            Current health status
        """
        start_time = time.time()
        
        try:
            # Try to get dashboard info as health check
            dashboard = await self.get_dashboard()
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            
            # Consider healthy if we got a response
            is_healthy = dashboard is not None
            is_connected = self._session is not None and not self._session.closed
            
            additional_info = {}
            if dashboard:
                # Extract useful info from Dashboard model
                if dashboard.Measurement:
                    additional_info["acquiring"] = dashboard.Measurement.Status == "DA_RECORDING"
                    if dashboard.Measurement.FrameCount:
                        additional_info["frame_count"] = dashboard.Measurement.FrameCount
                if dashboard.Server and dashboard.Server.SoftwareVersion:
                    additional_info["serval_version"] = dashboard.Server.SoftwareVersion
                if dashboard.Detector and dashboard.Detector.DetectorType:
                    additional_info["detector_type"] = dashboard.Detector.DetectorType
            
            return ServiceHealthStatus(
                is_healthy=is_healthy,
                is_connected=is_connected,
                last_check=time.time(),
                response_time_ms=response_time,
                additional_info=additional_info
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return ServiceHealthStatus(
                is_healthy=False,
                is_connected=self._session is not None and not self._session.closed,
                last_check=time.time(),
                error_message=str(e),
                response_time_ms=response_time
            )
    
    # ========================================================================
    # HTTP Request Helpers
    # ========================================================================
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request to SERVAL with retry logic.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., '/dashboard')
            data: Request body data (for POST/PUT)
            params: URL parameters
            timeout: Request timeout override
            
        Returns:
            Response data as dictionary
            
        Raises:
            ConnectionError: If not connected or connection failed
            ServalAPIError: If SERVAL returns an error response
            TimeoutError: If request times out
        """
        if not self._session:
            raise ConnectionError("Not connected to SERVAL")
        
        url = f"{self.serval_config.base_url}{endpoint}"
        request_timeout = timeout or self._request_timeout
        
        for attempt in range(self._max_retries + 1):
            try:
                # Set up request arguments
                kwargs = {
                    "url": url,
                    "timeout": aiohttp.ClientTimeout(total=request_timeout)
                }
                
                if params:
                    kwargs["params"] = params
                
                if data:
                    kwargs["json"] = data
                
                # Make the request
                async with self._session.request(method, **kwargs) as response:
                    response_text = await response.text()
                    
                    # Check for HTTP errors
                    if response.status >= 400:
                        error_msg = f"SERVAL API error: {response.status} - {response_text}"
                        raise ServalAPIError(error_msg, response.status, response_text)
                    
                    # Parse JSON response
                    if response_text:
                        try:
                            return json.loads(response_text)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse JSON response: {e}")
                            return {"raw_response": response_text}
                    else:
                        return {}
                        
            except asyncio.TimeoutError:
                if attempt == self._max_retries:
                    raise TimeoutError(f"Request to {url} timed out after {request_timeout}s")
                logger.warning(f"Request timeout (attempt {attempt + 1}/{self._max_retries + 1})")
                
            except (aiohttp.ClientError, ServalAPIError) as e:
                if attempt == self._max_retries:
                    raise
                logger.warning(f"Request failed (attempt {attempt + 1}/{self._max_retries + 1}): {e}")
            
            # Wait before retry
            if attempt < self._max_retries:
                await asyncio.sleep(self._retry_delay)
        
        # This shouldn't be reached due to the raises above, but just in case
        raise ConnectionError("Maximum retries exceeded")
    
    # ========================================================================
    # SERVAL API Methods
    # ========================================================================
    
    async def get_dashboard(self) -> Optional[Dashboard]:
        """
        Get dashboard information from SERVAL.
        
        Returns:
            Dashboard information, or None if request failed
        """
        try:
            logger.debug("Requesting SERVAL dashboard")
            response = await self._make_request("GET", "/dashboard")
            
            # Use the existing Dashboard model directly
            dashboard = Dashboard(**response)
            self._last_dashboard = dashboard
            
            logger.debug(f"Dashboard retrieved successfully")
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Failed to get dashboard: {e}")
            return None
    
    def get_last_dashboard(self) -> Optional[Dashboard]:
        """
        Get the last retrieved dashboard information without making a new request.
        
        Returns:
            Last dashboard information, or None if never retrieved
        """
        return self._last_dashboard
    
    # ========================================================================
    # Convenience Properties
    # ========================================================================
    
    @property
    def api_base_url(self) -> str:
        """Get the base URL for SERVAL API."""
        return self.serval_config.base_url
    
    @property
    def is_acquiring(self) -> Optional[bool]:
        """
        Check if currently acquiring based on last dashboard info.
        
        Returns:
            True/False if known, None if no dashboard info available
        """
        if self._last_dashboard and self._last_dashboard.Measurement:
            return self._last_dashboard.Measurement.Status == "DA_RECORDING"
        return None
    
    @property
    def detector_type(self) -> Optional[str]:
        """
        Get detector type based on last dashboard info.
        
        Returns:
            Detector type if known, None if no dashboard info available
        """
        if self._last_dashboard and self._last_dashboard.Detector:
            return self._last_dashboard.Detector.DetectorType
        return None


# ========================================================================
# Factory Integration
# ========================================================================

def create_serval_http_client(serval_config: ServalConfig, **http_overrides) -> ServalHTTPClient:
    """
    Create a SERVAL HTTP client from ServalConfig.
    
    Args:
        serval_config: SERVAL configuration including HTTP settings
        **http_overrides: HTTP configuration overrides (timeout, max_retries, etc.)
        
    Returns:
        Configured ServalHTTPClient instance
    """
    # If overrides are provided, create a new config with those values
    if http_overrides:
        # Create a copy of the config with HTTP overrides
        config_dict = serval_config.model_dump()
        config_dict.update(http_overrides)
        updated_config = ServalConfig(**config_dict)
        return ServalHTTPClient(updated_config)
    else:
        return ServalHTTPClient(serval_config)