'''
Module for setting, loading, and saving configuration schemas within the HERMES acquisition package
'''

from pathlib import Path
from typing import Dict, Any, Optional, Union, Type, TypeVar
from pydantic import ValidationError

from hermes.acquisition.models.schema import Default as HermesDefault
from hermes.acquisition.models.software.environment import WorkingDir
from hermes.acquisition.models.software.serval import ServalConfig
from hermes.acquisition.models.software.parameters import RunSettings
from hermes.acquisition.models.software.epics import EPICSConfig
from hermes.acquisition.models.hardware.tpx3Cam import HardwareConfig
from hermes.acquisition.models.hardware.zabers import ZaberConfig
from hermes.acquisition.logger import logger

# Type variable for generic configuration loading
ConfigType = TypeVar('ConfigType')

class ConfigurationManager:
    """
    Manages configuration for HERMES acquisition system.
    
    Handles loading, saving, and validation of all configuration models.
    Can work with individual models or default HERMES schema.
    """
    
    def __init__(self, config: Optional[HermesDefault] = None):
        """
        Initialize configuration manager.
        
        Args:
            config: Optional pre-existing configuration. If None, creates default.
        """
        self.config = config or HermesDefault()
        logger.info("ConfigurationManager initialized")
        
    # ========================================================================
    # Setup and Creation Methods
    # ========================================================================
    
    def setup_environment(self, **kwargs) -> WorkingDir:
        """
        Setup or modify environment configuration.
        
        Args:
            **kwargs: WorkingDir parameters to override
            
        Returns:
            WorkingDir: Updated environment configuration
        """
        try:
            if kwargs:
                # Get current config as dict and update with new values
                current_config = self.config.environment.model_dump()
                current_config.update(kwargs)
                self.config.environment = WorkingDir(**current_config)
                logger.info(f"Environment configuration updated with: {list(kwargs.keys())}")
            
            return self.config.environment
            
        except ValidationError as e:
            logger.error(f"Environment configuration validation failed: {e}")
            raise
            
    def setup_serval(self, **kwargs) -> ServalConfig:
        """Setup or modify Serval configuration."""
        try:
            if kwargs:
                current_config = self.config.serval.model_dump()
                current_config.update(kwargs)
                self.config.serval = ServalConfig(**current_config)
                logger.info(f"Serval configuration updated with: {list(kwargs.keys())}")
            
            return self.config.serval
            
        except ValidationError as e:
            logger.error(f"Serval configuration validation failed: {e}")
            raise
            
    def setup_run_settings(self, **kwargs) -> RunSettings:
        """Setup or modify run settings configuration."""
        try:
            if kwargs:
                current_config = self.config.run_settings.model_dump()
                current_config.update(kwargs)
                self.config.run_settings = RunSettings(**current_config)
                logger.info(f"Run settings configuration updated with: {list(kwargs.keys())}")
            
            return self.config.run_settings
            
        except ValidationError as e:
            logger.error(f"Run settings configuration validation failed: {e}")
            raise
            
    def setup_hardware(self, **kwargs) -> HardwareConfig:
        """Setup or modify hardware configuration."""
        try:
            if self.config.hardware is None:
                self.config.hardware = HardwareConfig(**kwargs)
                logger.info("Hardware configuration created")
            else:
                current_config = self.config.hardware.model_dump()
                current_config.update(kwargs)
                self.config.hardware = HardwareConfig(**current_config)
                logger.info(f"Hardware configuration updated with: {list(kwargs.keys())}")
            
            return self.config.hardware
            
        except ValidationError as e:
            logger.error(f"Hardware configuration validation failed: {e}")
            raise
            
    def setup_zabers(self, **kwargs) -> ZaberConfig:
        """Setup or modify Zaber configuration."""
        try:
            if self.config.zabers is None:
                self.config.zabers = ZaberConfig(**kwargs)
                logger.info("Zaber configuration created")
            else:
                current_config = self.config.zabers.model_dump()
                current_config.update(kwargs)
                self.config.zabers = ZaberConfig(**current_config)
                logger.info(f"Zaber configuration updated with: {list(kwargs.keys())}")
            
            return self.config.zabers
            
        except ValidationError as e:
            logger.error(f"Zaber configuration validation failed: {e}")
            raise
            
    def setup_epics(self, **kwargs) -> EPICSConfig:
        """Setup or modify EPICS configuration."""
        try:
            if self.config.epics_control is None:
                self.config.epics_control = EPICSConfig(**kwargs)
                logger.info("EPICS configuration created")
            else:
                current_config = self.config.epics_control.model_dump()
                current_config.update(kwargs)
                self.config.epics_control = EPICSConfig(**current_config)
                logger.info(f"EPICS configuration updated with: {list(kwargs.keys())}")
            
            return self.config.epics_control
            
        except ValidationError as e:
            logger.error(f"EPICS configuration validation failed: {e}")
            raise
    
    # ========================================================================
    # File I/O Methods
    # ========================================================================
    
    def save_to_file(self, config_file: Union[str, Path], 
                     format: str = "auto") -> None:
        """
        Save current configuration to file.
        
        Args:
            config_file: Path to save configuration file
            format: File format ('json', 'yaml', 'ini', or 'auto' to detect from extension)
        """
        from hermes.acquisition.utils import save_pydantic_model
        
        try:
            save_pydantic_model(self.config, config_file, format=format)
            
        except Exception as e:
            logger.error(f"Failed to save configuration to {config_file}: {e}")
            raise
            
    def load_from_file(self, config_file: Union[str, Path]) -> HermesDefault:
        """
        Load configuration from file.
        
        Args:
            config_file: Path to configuration file
            
        Returns:
            HermesDefault: Loaded configuration
        """
        from hermes.acquisition.utils import load_pydantic_model
        
        try:
            self.config = load_pydantic_model(HermesDefault, config_file)
            logger.success(f"Configuration loaded from {config_file}")
            
            return self.config
            
        except Exception as e:
            logger.error(f"Failed to load configuration from {config_file}: {e}")
            raise
            
    def load_from_dict(self, config_dict: Dict[str, Any]) -> HermesDefault:
        """
        Load configuration from dictionary.
        
        Args:
            config_dict: Configuration dictionary
            
        Returns:
            HermesDefault: Loaded configuration
        """
        try:
            self.config = HermesDefault.model_validate(config_dict)
            logger.success("Configuration loaded from dictionary")
            return self.config
            
        except ValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    def to_dict(self, exclude_none: bool = True) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Args:
            exclude_none: Whether to exclude None values
            
        Returns:
            Dict: Configuration as dictionary
        """
        return self.config.model_dump(exclude_none=exclude_none)
        
    def get_config(self) -> HermesDefault:
        """Get the current configuration."""
        return self.config
        
    def validate_config(self) -> bool:
        """
        Validate the current configuration.
        
        Returns:
            bool: True if valid, raises exception if invalid
        """
        try:
            # Re-validate the current config
            HermesDefault.model_validate(self.config.model_dump())
            logger.info("Configuration validation successful")
            return True
        except ValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise
            
    def reset_to_defaults(self) -> HermesDefault:
        """Reset configuration to defaults."""
        self.config = HermesDefault()
        logger.info("Configuration reset to defaults")
        return self.config
        
    def summary(self) -> str:
        """Get a summary of the current configuration."""
        summary_lines = [
            "HERMES Configuration Summary:",
            "=" * 30,
            f"Working Directory: {self.config.environment.path_to_working_dir}",
            f"Run Directory: {self.config.environment.run_dir_name}",
            f"Log Level: {self.config.log_level}",
            f"Serval Host: {self.config.serval.host}:{self.config.serval.port}",
            f"Hardware Config: {'Configured' if self.config.hardware else 'Not configured'}",
            f"Zabers Config: {'Configured' if self.config.zabers else 'Not configured'}",
            f"EPICS Config: {'Configured' if self.config.epics_control else 'Not configured'}",
        ]
        
        return "\n".join(summary_lines)


# ========================================================================
# Convenience Functions
# ========================================================================

def create_default_config() -> ConfigurationManager:
    """Create a configuration manager with default settings."""
    return ConfigurationManager()

def load_config_from_file(config_file: Union[str, Path]) -> ConfigurationManager:
    """Load configuration from file."""
    manager = ConfigurationManager()
    manager.load_from_file(config_file)
    return manager

def create_config_from_dict(config_dict: Dict[str, Any]) -> ConfigurationManager:
    """Create configuration from dictionary."""
    manager = ConfigurationManager()
    manager.load_from_dict(config_dict)
    return manager

def save_individual_model(model: Any, output_file: Union[str, Path], 
                         format: str = "auto") -> None:
    """
    Save an individual pydantic model to file.
    
    Args:
        model: Pydantic model instance to save
        output_file: Path to save file
        format: File format ('json', 'yaml', 'ini', or 'auto')
    """
    from hermes.acquisition.utils import save_pydantic_model
    
    try:
        save_pydantic_model(model, output_file, format=format)
        
    except Exception as e:
        logger.error(f"Failed to save model to {output_file}: {e}")
        raise

def load_individual_model(model_class: Type[ConfigType], 
                         input_file: Union[str, Path]) -> ConfigType:
    """
    Load an individual pydantic model from file.
    
    Args:
        model_class: Pydantic model class to load
        input_file: Path to input file
        
    Returns:
        Instance of the model class
    """
    from hermes.acquisition.utils import load_pydantic_model
    
    try:
        model = load_pydantic_model(model_class, input_file)
        logger.success(f"Model loaded from {input_file}")
        
        return model
        
    except Exception as e:
        logger.error(f"Failed to load model from {input_file}: {e}")
        raise


if __name__ == "__main__":
    # Example usage
    manager = create_default_config()
    
    # Setup some configurations
    manager.setup_environment(
        path_to_working_dir="/data/experiments",
        run_dir_name="test_run_001"
    )
    
    manager.setup_zabers(
        port="/dev/ttyUSB0",
        debug=True
    )
    
    # Print summary
    print(manager.summary())
    
    # Save configuration
    manager.save_to_file("example_config.json")
    
    # Load it back
    new_manager = load_config_from_file("example_config.json")
    print(new_manager.summary())