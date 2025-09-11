'''
Module for defining pydantic configuration models needed for setting up a working directory structure.
'''

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from pathlib import Path
import os
import shutil
from hermes.acquisition.logger import logger

class WorkingDir(BaseModel):
    """
    Pydantic model for managing working directory structure and configuration.
    
    This model handles the creation and validation of directory structures needed
    for data acquisition runs, including automatic directory creation and cleanup.
    """
    
    # Directory path configuration
    path_to_working_dir: str = Field(
        default="./", 
        description="Path to the working directory where all files will be stored."
    )
    run_dir_name: str = Field(
        default="dummy/", 
        description="Name of the run directory where all run-specific files will be stored."
    )
    
    # Subdirectory paths (relative to run directory)
    path_to_status_files: str = Field(
        default="statusFiles/", 
        description="Path to the directory where status files will be stored."
    )
    path_to_log_files: str = Field(
        default="logFiles/", 
        description="Path to the directory where log files will be stored."
    )
    path_to_image_files: str = Field(
        default="imageFiles/", 
        description="Path to the directory where image files will be stored."
    )
    path_to_preview_files: str = Field(
        default="previewFiles/", 
        description="Path to the directory where preview files will be stored."
    )
    path_to_tpx3_files: str = Field(
        default="tpx3Files/", 
        description="Path to the directory where raw files are stored."
    )
    path_to_init_files: str = Field(
        default="initFiles/", 
        description="Path to the initialization files."
    )
    
    # Directory management controls
    create_if_missing: bool = Field(
        default=True, 
        description="Create the directory tree if missing."
    )
    clean_if_exists: bool = Field(
        default=False, 
        description="If the run directory exists, clean it before use."
    )

    # ========================================================================
    # Field Validators
    # ========================================================================
    
    @field_validator('path_to_status_files', 'path_to_log_files', 'path_to_image_files', 
                     'path_to_preview_files', 'path_to_tpx3_files', 'path_to_init_files', mode='before')
    @classmethod
    def ensure_relative_path(cls, v):
        """
        Ensure subdirectory paths are relative, not absolute.
        
        This prevents security issues where absolute paths could escape
        the intended directory structure (e.g., "/etc/passwd" -> "etc/passwd").
        
        Args:
            v: The path value to validate
            
        Returns:
            str: Normalized relative path
        """
        if v is None:
            return v
        
        path = Path(v)
        
        # Convert absolute paths to relative by removing root
        if path.is_absolute():
            logger.warning(f"Converting absolute path '{v}' to relative path")
            # Strip leading slash to make relative
            return str(Path(*path.parts[1:]))
        
        # Return normalized relative path
        return str(path)

    @field_validator('run_dir_name', mode='before')
    @classmethod
    def sanitize_run_dir_name(cls, v):
        """
        Sanitize and validate the run directory name.
        
        Ensures the run directory name is safe and not empty.
        
        Args:
            v: The run directory name to validate
            
        Returns:
            str: Sanitized run directory name
        """
        # Handle None or empty values
        if v is None:
            logger.debug("Run directory name was None, using default 'run'")
            return "run"
        
        # Clean up whitespace and slashes
        run_dir_name = str(v).strip().strip("/")
        
        # Ensure we have a valid directory name
        if not run_dir_name or run_dir_name == "/":
            logger.warning(f"Invalid run directory name '{v}', using default 'run'")
            return "run"
        
        logger.debug(f"Sanitized run directory name: '{run_dir_name}'")
        return run_dir_name

    @field_validator('path_to_working_dir', mode='before')
    @classmethod
    def normalize_working_dir(cls, v):
        """
        Normalize and expand the working directory path.
        
        Handles user home directory expansion (~) and converts
        to absolute path for consistency.
        
        Args:
            v: The working directory path to validate
            
        Returns:
            str: Absolute, normalized working directory path
        """
        if v is None:
            v = "./"
        
        original_path = v
        # Expand user home directory and resolve to absolute path
        normalized = str(Path(v).expanduser().resolve())
        
        if original_path != normalized:
            logger.debug(f"Normalized working directory: '{original_path}' -> '{normalized}'")
        
        return normalized

    # ========================================================================
    # Model Validator
    # ========================================================================
    
    @model_validator(mode="after")
    def verify_and_prepare_dirs(cls, values):
        """
        Create directory structure and perform safety checks.
        
        This validator runs after all field validators and handles:
        - Directory structure creation
        - Safety checks (e.g., not operating on root)
        - Cleanup of existing directories if requested
        
        Args:
            values: The validated model instance
            
        Returns:
            The model instance after directory operations
            
        Raises:
            RuntimeError: If attempting to operate on root directory
        """
        # Get normalized paths using pathlib
        working_dir = Path(values.path_to_working_dir)
        run_dir = working_dir / values.run_dir_name

        logger.info(f"Setting up directory structure at: {run_dir}")

        # Safety check - prevent accidental operations on root directory
        if run_dir == Path("/") or str(run_dir) == "/":
            logger.error("Attempted to operate on root directory - BLOCKED")
            raise RuntimeError("Refusing to operate on root directory")

        # Define all subdirectories that need to be created
        directories = {
            'run_dir': run_dir,
            'status_files_dir': run_dir / values.path_to_status_files,
            'log_files_dir': run_dir / values.path_to_log_files,
            'image_files_dir': run_dir / values.path_to_image_files,
            'preview_files_dir': run_dir / values.path_to_preview_files,
            'tpx3_files_dir': run_dir / values.path_to_tpx3_files,
            'init_files_dir': run_dir / values.path_to_init_files,
        }

        # Handle directory creation and cleanup
        if values.create_if_missing:
            # Check if directory exists and handle cleanup
            if run_dir.exists():
                logger.info(f"Directory '{run_dir}' already exists")
                
                # If clean_if_exists is True, prompt user for confirmation
                if values.clean_if_exists:
                    # Check if directory has any content
                    try:
                        # List all contents (files and directories)
                        contents = list(run_dir.iterdir())
                        if contents:
                            logger.warning(f"Directory '{run_dir}' contains {len(contents)} items")
                            print(f"\nDirectory '{run_dir}' exists and contains {len(contents)} items:")
                            
                            # Show first few items as examples
                            for i, item in enumerate(contents[:5]):
                                print(f"  - {item.name}")
                            if len(contents) > 5:
                                print(f"  ... and {len(contents) - 5} more items")
                            
                            # Prompt user for confirmation
                            while True:
                                response = input(f"\nDo you want to delete the existing directory and all its contents? (y/n): ").lower().strip()
                                if response in ['y', 'yes']:
                                    logger.warning(f"User confirmed deletion of directory: {run_dir}")
                                    print(f"Cleaning existing directory: {run_dir}")
                                    shutil.rmtree(run_dir)
                                    logger.info(f"Successfully cleaned directory: {run_dir}")
                                    break
                                elif response in ['n', 'no']:
                                    logger.info("User chose to keep existing directory")
                                    print("Keeping existing directory. New files will be added alongside existing ones.")
                                    break
                                else:
                                    print("Please enter 'y' for yes or 'n' for no.")
                        else:
                            # Directory exists but is empty, safe to proceed
                            logger.info(f"Directory '{run_dir}' exists but is empty - proceeding")
                            print(f"Directory '{run_dir}' exists but is empty. Proceeding...")
                    except Exception as e:
                        logger.error(f"Could not check directory contents: {e}")
                        print(f"Warning: Could not check directory contents: {e}")
                else:
                    logger.info(f"Directory exists but clean_if_exists=False - skipping cleanup")

            # Create all directories with parents if needed
            logger.debug(f"Creating {len(directories)} directories")
            for dir_name, dir_path in directories.items():
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    logger.debug(f"Ensured directory exists: {dir_path}")
                    #print(f"Ensured directory exists: {dir_path}")
                except Exception as e:
                    logger.error(f"Failed to create {dir_name} at {dir_path}: {e}")
                    raise RuntimeError(f"Failed to create {dir_name} at {dir_path}: {e}")

            logger.success(f"Directory structure setup completed successfully")
        else:
            logger.info("Directory creation disabled (create_if_missing=False)")

        return values
    