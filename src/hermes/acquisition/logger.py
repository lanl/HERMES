"""
Centralized logging configuration using loguru for the HERMES acquisition system.
"""

from loguru import logger
import sys
from pathlib import Path
from typing import Optional

def setup_logger(
    log_file: Optional[Path] = None,
    log_level: str = "INFO",
    enable_console: bool = True
) -> None:
    """
    Configure loguru logger for the acquisition system.
    
    Args:
        log_file: Path to log file. If None, only console logging is used.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_console: Whether to enable console output
    """
    # Remove default handler
    logger.remove()
    
    # Add console handler if enabled
    if enable_console:
        logger.add(
            sys.stderr,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            colorize=True
        )
    
    # Add file handler if log_file is provided
    if log_file:
        logger.add(
            log_file,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="10 MB",
            retention="7 days",
            compression="zip"
        )

# Initialize with default settings
setup_logger()

# Export the configured logger
__all__ = ["logger", "setup_logger"]