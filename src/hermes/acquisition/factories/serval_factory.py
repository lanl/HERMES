"""
SERVAL factory for configuration management and service instantiation.

This factory layer handles:
1. Loading and validating SERVAL configurations from various sources
2. Creating properly configured SERVAL process managers
3. Discovery and validation of SERVAL installations
4. Configuration merging and override management

The factory pattern separates configuration concerns from the service layer,
allowing for flexible configuration sources and validation strategies.
"""

import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Union
import logging

from pydantic import BaseModel, Field, ValidationError

from hermes.acquisition.models.software.serval import ServalConfig
from hermes.acquisition.services.direct.serval_process_manager import (
    ServalProcessManager, 
    ServalProcessConfig,
    discover_serval_installations,
    validate_java_installation
)
from hermes.acquisition.services.exceptions import ServalProcessError

logger = logging.getLogger(__name__)


class ServalFactoryConfig(BaseModel):
    """Configuration for SERVAL factory behavior."""
    
    # Discovery settings
    auto_discover: bool = Field(default=True, description="Automatically discover SERVAL installations")
    search_paths: list[Path] = Field(default_factory=list, description="Additional search paths for SERVAL")
    
    # Process management defaults
    default_startup_timeout: float = Field(default=60.0, description="Default startup timeout")
    default_require_camera: bool = Field(default=True, description="Default require camera connection")
    auto_restart: bool = Field(default=True, description="Default auto-restart setting")
    
    # Validation settings
    validate_java: bool = Field(default=True, description="Validate Java installation before creating manager")
    validate_serval_paths: bool = Field(default=True, description="Validate SERVAL paths before creating manager")
    
    # Logging
    log_level: Optional[str] = Field(default=None, description="SERVAL log level override")


class ServalInstallationInfo(BaseModel):
    """Information about a discovered SERVAL installation."""
    
    path: Path
    version: str
    jar_file: Optional[Path]
    is_valid: bool
    validation_errors: list[str] = Field(default_factory=list)


class ServalFactory:
    """
    Factory for creating and configuring SERVAL process managers.
    
    This factory implements the recommended pattern for the Factories layer:
    - Configuration loading and validation
    - Service client instantiation with proper settings  
    - Dependency injection and resource management
    """
    
    def __init__(self, factory_config: Optional[ServalFactoryConfig] = None):
        """
        Initialize SERVAL factory.
        
        Args:
            factory_config: Factory configuration, uses defaults if None
        """
        self.factory_config = factory_config or ServalFactoryConfig()
        self._discovered_installations: Optional[list[ServalInstallationInfo]] = None
        self._java_validated: Optional[bool] = None
        
        logger.info("SERVAL factory initialized")
    
    # ========================================================================
    # Discovery and Validation
    # ========================================================================
    
    async def discover_installations(self, force_rediscover: bool = False) -> list[ServalInstallationInfo]:
        """
        Discover available SERVAL installations.
        
        Args:
            force_rediscover: Force rediscovery even if cached results exist
            
        Returns:
            List of discovered SERVAL installations
        """
        if self._discovered_installations is not None and not force_rediscover:
            return self._discovered_installations
        
        logger.info("Discovering SERVAL installations...")
        
        # Use the service layer discovery functions
        installations = await discover_serval_installations()
        
        # Convert to factory info format
        installation_info = []
        for inst in installations:
            info = ServalInstallationInfo(
                path=inst.path,
                version=inst.version,
                jar_file=inst.jar_file,
                is_valid=inst.is_valid,
                validation_errors=[] if inst.is_valid else ["JAR file not found or invalid"]
            )
            installation_info.append(info)
        
        self._discovered_installations = installation_info
        logger.info(f"Discovered {len(installation_info)} SERVAL installations")
        
        return installation_info
    
    async def validate_prerequisites(self) -> Dict[str, Any]:
        """
        Validate system prerequisites for SERVAL.
        
        Returns:
            Dictionary with validation results
        """
        results = {
            "java_available": False,
            "serval_installations": [],
            "validation_errors": [],
            "recommendations": []
        }
        
        # Validate Java if configured
        if self.factory_config.validate_java:
            if self._java_validated is None:
                self._java_validated = validate_java_installation()
            
            results["java_available"] = self._java_validated
            if not self._java_validated:
                results["validation_errors"].append("Java not found or not working")
                results["recommendations"].append("Install Java JRE/JDK to run SERVAL")
        
        # Discover SERVAL installations if configured
        if self.factory_config.auto_discover:
            installations = await self.discover_installations()
            results["serval_installations"] = [
                {
                    "path": str(inst.path),
                    "version": inst.version,
                    "valid": inst.is_valid,
                    "errors": inst.validation_errors
                }
                for inst in installations
            ]
            
            valid_installations = [inst for inst in installations if inst.is_valid]
            if not valid_installations:
                results["validation_errors"].append("No valid SERVAL installations found")
                results["recommendations"].append(
                    "Install SERVAL in /opt/serval/ or provide path_to_serval in configuration"
                )
        
        return results
    
    # ========================================================================
    # Configuration Creation
    # ========================================================================
    
    def create_serval_config(
        self,
        host: str = "localhost",
        port: int = 8080,
        version: str = "3.3.0",
        path_to_serval: Optional[Union[str, Path]] = None,
        **kwargs
    ) -> ServalConfig:
        """
        Create a validated ServalConfig.
        
        Args:
            host: SERVAL host
            port: SERVAL port
            version: SERVAL version
            path_to_serval: Path to SERVAL installation
            **kwargs: Additional ServalConfig parameters
            
        Returns:
            Validated ServalConfig instance
            
        Raises:
            ValidationError: If configuration is invalid
        """
        config_data = {
            "host": host,
            "port": port,
            "version": version,
            **kwargs
        }
        
        if path_to_serval:
            config_data["path_to_serval"] = str(Path(path_to_serval))
        
        try:
            config = ServalConfig(**config_data)
            logger.info(f"Created SERVAL config: {config.base_url}")
            return config
        except ValidationError as e:
            logger.error(f"SERVAL config validation failed: {e}")
            raise
    
    def create_process_config(
        self,
        serval_config: ServalConfig,
        startup_timeout: Optional[float] = None,
        require_camera: Optional[bool] = None,
        camera_timeout: Optional[float] = None,
        auto_restart: Optional[bool] = None,
        java_executable: str = "java",
        **kwargs
    ) -> ServalProcessConfig:
        """
        Create a ServalProcessConfig from ServalConfig with factory defaults.
        
        Args:
            serval_config: Base SERVAL configuration
            startup_timeout: Process startup timeout override
            require_camera: Require camera connection override  
            camera_timeout: Camera connection timeout override (seconds)
            auto_restart: Auto-restart setting override
            java_executable: Java executable path
            **kwargs: Additional process config parameters
            
        Returns:
            Configured ServalProcessConfig instance
        """
        # Apply factory defaults
        overrides = {
            "java_executable": java_executable,
            "startup_timeout": startup_timeout or self.factory_config.default_startup_timeout,
            "require_camera_connection": require_camera if require_camera is not None else self.factory_config.default_require_camera,
            "camera_connection_timeout": camera_timeout or 30.0,  # Default 30s camera timeout
            "auto_restart": auto_restart if auto_restart is not None else self.factory_config.auto_restart,
            **kwargs
        }
        
        # Apply log level override if configured
        if self.factory_config.log_level:
            overrides["log_level"] = self.factory_config.log_level
        
        return ServalProcessConfig.from_serval_config(serval_config, **overrides)
    
    # ========================================================================
    # Service Instantiation
    # ========================================================================
    
    async def create_process_manager(
        self,
        serval_config: Optional[ServalConfig] = None,
        process_config: Optional[ServalProcessConfig] = None,
        validate_before_creation: bool = False,  # Changed default to False - process manager does its own validation
        **config_overrides
    ) -> ServalProcessManager:
        """
        Create a fully configured SERVAL process manager.
        
        Args:
            serval_config: SERVAL configuration (created with defaults if None)
            process_config: Process configuration (created from serval_config if None)
            validate_before_creation: Run validation before creating manager
            **config_overrides: Additional configuration overrides
            
        Returns:
            Configured ServalProcessManager instance
            
        Raises:
            ServalProcessError: If validation fails or configuration is invalid
        """
        logger.info("Creating SERVAL process manager...")
        
        # Validate prerequisites if requested
        if validate_before_creation:
            validation = await self.validate_prerequisites()
            if validation["validation_errors"]:
                error_msg = "SERVAL prerequisites validation failed:\n"
                for error in validation["validation_errors"]:
                    error_msg += f"  - {error}\n"
                if validation["recommendations"]:
                    error_msg += "Recommendations:\n"
                    for rec in validation["recommendations"]:
                        error_msg += f"  - {rec}\n"
                raise ServalProcessError(error_msg)
        
        # Create ServalConfig if not provided
        if serval_config is None:
            serval_config = self.create_serval_config(**config_overrides)
        
        # Create ServalProcessConfig if not provided
        if process_config is None:
            process_config = self.create_process_config(serval_config, **config_overrides)
        
        # Create and return the process manager
        manager = ServalProcessManager(process_config, serval_config)
        logger.info("SERVAL process manager created successfully")
        
        return manager
    
    # ========================================================================
    # Convenience Methods
    # ========================================================================
    
    async def create_and_start_manager(
        self,
        serval_config: Optional[ServalConfig] = None,
        **config_overrides
    ) -> ServalProcessManager:
        """
        Create and start a SERVAL process manager in one call.
        
        Args:
            serval_config: SERVAL configuration
            **config_overrides: Configuration overrides
            
        Returns:
            Started ServalProcessManager instance
            
        Raises:
            ServalProcessError: If creation or startup fails
        """
        manager = await self.create_process_manager(serval_config, **config_overrides)
        
        success = await manager.start_with_full_validation()
        if not success:
            await manager.disconnect()  # Cleanup on failure
            raise ServalProcessError("Failed to start SERVAL process manager")
        
        return manager
    
    @classmethod
    async def quick_start(
        cls,
        host: str = "localhost", 
        port: int = 8080,
        path_to_serval: Optional[Union[str, Path]] = None,
        require_camera: bool = True,
        **kwargs
    ) -> ServalProcessManager:
        """
        Quick start method for creating and starting SERVAL with minimal configuration.
        
        Args:
            host: SERVAL host
            port: SERVAL port  
            path_to_serval: Path to SERVAL installation
            require_camera: Require camera connection
            **kwargs: Additional configuration options
            
        Returns:
            Started ServalProcessManager instance
        """
        factory = cls()
        
        serval_config = factory.create_serval_config(
            host=host,
            port=port,
            path_to_serval=path_to_serval,
            **kwargs
        )
        
        return await factory.create_and_start_manager(
            serval_config=serval_config,
            require_camera=require_camera,
            **kwargs
        )