''' 
Module for initializing the various models in the HERMES acquisition package

1. Initialize logging
2. Check environment variables and hardware configurations
    - Check for working directory and subdirectories
    - Check Serval configuration
    - Check hardware configuration
    - Check for other required software packages
3. Initialize Serval
4. Initialize run settings
'''

from pathlib import Path
from typing import Optional, Dict, Any
import os
from hermes.acquisition.logger import logger, setup_logger
from hermes.acquisition.models.software.environment import WorkingDir


def initialize_logging(
    log_file: Optional[Path] = None,
    log_level: str = "INFO",
    enable_console: bool = True
) -> None:
    """
    Initialize the logging system for HERMES acquisition.
    
    Args:
        log_file: Path to log file. If None, only console logging is used.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_console: Whether to enable console output
    """
    logger.info("Initializing HERMES acquisition logging system")
    setup_logger(log_file=log_file, log_level=log_level, enable_console=enable_console)
    logger.success("Logging system initialized successfully")

def initialize_working_directory(
    path_to_working_dir: Optional[str] = None,
    run_dir_name: Optional[str] = None,
    config_dict: Optional[Dict[str, Any]] = None,
    create_if_missing: bool = True,
    clean_if_exists: bool = False
) -> WorkingDir:
    """
    Initialize and validate the working directory structure.
    
    Args:
        path_to_working_dir: Path to the main working directory
        run_dir_name: Name of the run-specific directory
        config_dict: Dictionary of configuration parameters
        create_if_missing: Whether to create directories if they don't exist
        clean_if_exists: Whether to prompt for cleanup of existing directories
        
    Returns:
        WorkingDir: Configured and validated working directory instance
        
    Raises:
        RuntimeError: If directory initialization fails
    """
    
    logger.info("Initializing working directory structure")
    
    try:
        # Build configuration parameters
        config_params = {
            "create_if_missing": create_if_missing,
            "clean_if_exists": clean_if_exists
        }
        
        # Add optional parameters if provided
        if path_to_working_dir:
            config_params["path_to_working_dir"] = path_to_working_dir
        if run_dir_name:
            config_params["run_dir_name"] = run_dir_name
            
        # Merge with any additional config dictionary
        if config_dict:
            config_params.update(config_dict)
            
        # Create and validate the working directory
        working_dir = WorkingDir(**config_params)
        
        logger.success(f"Working directory initialized: {working_dir.path_to_working_dir}")
        return working_dir
        
    except Exception as e:
        logger.error(f"Failed to initialize working directory: {e}")
        raise RuntimeError(f"Working directory initialization failed: {e}")
    
def initialize_hermes_acquisition(
    path_to_working_dir: Optional[str] = None,  # 
    run_dir_name: Optional[str] = None,         
    log_level: str = "INFO",
    create_if_missing: bool = True,
    clean_if_exists: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Main initialization function for HERMES acquisition system.
    
    Sets up logging and initializes working directory structure.
    
    Args:
        path_to_working_dir: Path to working directory (matches WorkingDir.path_to_working_dir)
        run_dir_name: Name for run directory (matches WorkingDir.run_dir_name)
        log_level: Logging level to use
        create_if_missing: Whether to create directories if they don't exist
        clean_if_exists: Whether to prompt for cleanup of existing directories
        **kwargs: Additional configuration parameters for WorkingDir
        
    Returns:
        Dict[str, Any]: Dictionary containing initialized components
        
    Example:
        >>> config = initialize_hermes_acquisition(
        ...     path_to_working_dir="/data/experiments",
        ...     run_dir_name="test_run_001",
        ...     log_level="DEBUG"
        ... )
        >>> working_dir = config['working_dir']
        >>> working_dir_path = working_dir.path_to_working_dir  # Use the model attribute
    """
    # Step 1: Initialize basic logging
    initialize_logging(log_level=log_level)
    logger.info("Starting HERMES acquisition initialization")
    
    # Step 2: Initialize working directory structure using WorkingDir model
    working_dir_config = initialize_working_directory(
        path_to_working_dir=path_to_working_dir,
        run_dir_name=run_dir_name,
        create_if_missing=create_if_missing,
        clean_if_exists=clean_if_exists,
        config_dict=kwargs
    )
    
    # Step 3: Reconfigure logging to use the log directory from the WorkingDir model
    log_file_path = (
        Path(working_dir_config.path_to_working_dir) / 
        working_dir_config.run_dir_name / 
        working_dir_config.path_to_log_files / 
        "hermes_acquisition.log"
    )
    
    initialize_logging(
        log_file=log_file_path,
        log_level=log_level,
        enable_console=True
    )
    
    logger.success("HERMES acquisition initialization completed successfully")
    
    # Return configuration using the WorkingDir model attributes
    return {
        'working_dir': working_dir_config,                           # The WorkingDir instance
        'log_file': log_file_path,                                  # Path to log file
        'path_to_working_dir': working_dir_config.path_to_working_dir,  # Use model attribute
        'run_dir_name': working_dir_config.run_dir_name             # Use model attribute
    }