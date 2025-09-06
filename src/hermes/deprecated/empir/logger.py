"""
Logger configuration for the EMPIR module.
Provides centralized logging setup with both console and file output.
"""

import os
import sys
from loguru import logger

def configure_logger(log_file_path: str = None, verbose_level: int = 0, remove_existing: bool = True):
    """
    Configure the loguru logger for EMPIR processing.
    
    Args:
        log_file_path (str, optional): Path to the log file. If None, only console logging.
        verbose_level (int): Verbosity level (0-3)
            0: WARNING and above to console, DEBUG and above to file
            1: INFO and above to console, DEBUG and above to file  
            2: DEBUG to console, DEBUG and above to file
            3: DEBUG to console with more detailed format, DEBUG and above to file
        remove_existing (bool): Whether to remove existing handlers before adding new ones
    """
    
    if remove_existing:
        # Remove all existing handlers
        logger.remove()
    
    # Configure console handler based on verbose level
    if verbose_level == 0:
        # Minimal console output - only warnings and errors
        logger.add(
            sys.stderr,
            level="WARNING",
            format="<yellow>{time:HH:mm:ss}</yellow> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        )
    elif verbose_level == 1:
        # Standard info level
        logger.add(
            sys.stderr,
            level="INFO",
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        )
    elif verbose_level == 2:
        # Debug level
        logger.add(
            sys.stderr,
            level="DEBUG",
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        )
    else:  # verbose_level >= 3
        # Very detailed debug
        logger.add(
            sys.stderr,
            level="DEBUG",
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{module}</cyan>.<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>"
        )
    
    # Add file handler if log file path is provided
    if log_file_path:
        # Ensure the directory exists
        log_dir = os.path.dirname(log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # Add file handler - always DEBUG level for comprehensive logging
        logger.add(
            log_file_path,
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{module}.{function}:{line} | {message}",
            rotation="10 MB",  # Rotate when file gets too large
            retention="30 days",  # Keep logs for 30 days
            compression="zip"  # Compress old log files
        )
        
        logger.info(f"Logging configured - File: {log_file_path}, Console level: {verbose_level}")
    else:
        logger.info(f"Logging configured - Console only, level: {verbose_level}")


def setup_empir_logger(destination_dir: str = None, verbose_level: int = 0):
    """
    Convenience function to set up logger for EMPIR processing.
    
    Args:
        destination_dir (str, optional): Destination directory where hermes.log will be created
        verbose_level (int): Verbosity level (0-3)
    
    Returns:
        str: Path to the log file if created, None otherwise
    """
    log_file_path = None
    
    if destination_dir:
        log_file_path = os.path.join(destination_dir, "hermes.log")
    
    configure_logger(log_file_path, verbose_level)
    
    return log_file_path


# Create a module-level logger instance
empir_logger = logger
