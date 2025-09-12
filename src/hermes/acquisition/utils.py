# Utility functions shared between tpx3logging and tpx3serval
import os
import json
import configparser
from pathlib import Path
from typing import Dict, Any, Union, Type, TypeVar, Optional
from pydantic import BaseModel, ValidationError

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from hermes.acquisition.logger import logger

# Type variable for generic model loading
ModelType = TypeVar('ModelType', bound=BaseModel)

def _normalize_run_config(run_config):
    # Placeholder for normalization logic
    pass

def _safe_join(base, *paths):
    """Safely join path parts using pathlib."""
    return str(Path(base).joinpath(*paths))

def check_request_status(response):
    # Placeholder for checking HTTP request status
    pass

# ========================================================================
# Pydantic Model File I/O Utilities
# ========================================================================

def save_pydantic_model(model: BaseModel, 
                       output_file: Union[str, Path], 
                       format: str = "auto",
                       exclude_none: bool = True) -> None:
    """
    Save a Pydantic model to file in JSON, YAML, or INI format.
    
    Args:
        model: Pydantic model instance to save
        output_file: Path to save file
        format: File format ('json', 'yaml', 'ini', or 'auto' to detect from extension)
        exclude_none: Whether to exclude None values from output
        
    Raises:
        ValueError: If format is unsupported or YAML not available
        IOError: If file cannot be written
    """
    output_file = Path(output_file)
    
    # Determine format from extension if auto
    if format == "auto":
        suffix = output_file.suffix.lower()
        if suffix in ['.yaml', '.yml']:
            format = "yaml"
        elif suffix in ['.ini', '.cfg', '.conf']:
            format = "ini"
        else:
            format = "json"
    
    # Validate format availability
    if format == "yaml" and not YAML_AVAILABLE:
        raise ValueError("YAML format requested but PyYAML not installed")
    
    try:
        # Get model as dictionary
        model_dict = model.model_dump(exclude_none=exclude_none)
        
        # Ensure parent directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Save based on format
        if format == "yaml":
            _save_yaml(model_dict, output_file)
        elif format == "ini":
            _save_ini(model_dict, output_file)
        else:  # json
            _save_json(model_dict, output_file)
        
        logger.success(f"Model saved to {output_file} ({format} format)")
        
    except Exception as e:
        logger.error(f"Failed to save model to {output_file}: {e}")
        raise


def load_pydantic_model(model_class: Type[ModelType], 
                       input_file: Union[str, Path],
                       format: str = "auto") -> ModelType:
    """
    Load a Pydantic model from file in JSON, YAML, or INI format.
    
    Args:
        model_class: Pydantic model class to instantiate
        input_file: Path to input file
        format: File format ('json', 'yaml', 'ini', or 'auto' to detect from extension)
        
    Returns:
        Instance of the model class
        
    Raises:
        FileNotFoundError: If input file doesn't exist
        ValueError: If format is unsupported or validation fails
    """
    input_file = Path(input_file)
    
    if not input_file.exists():
        raise FileNotFoundError(f"Model file not found: {input_file}")
    
    # Determine format from extension if auto
    if format == "auto":
        suffix = input_file.suffix.lower()
        if suffix in ['.yaml', '.yml']:
            format = "yaml"
        elif suffix in ['.ini', '.cfg', '.conf']:
            format = "ini"
        else:
            format = "json"
    
    # Validate format availability
    if format == "yaml" and not YAML_AVAILABLE:
        raise ValueError("YAML format requested but PyYAML not installed")
    
    try:
        # Load data based on format
        if format == "yaml":
            model_dict = _load_yaml(input_file)
        elif format == "ini":
            model_dict = _load_ini(input_file)
        else:  # json
            model_dict = _load_json(input_file)
        
        # Validate and create model
        model = model_class.model_validate(model_dict)
        logger.success(f"Model loaded from {input_file} ({format} format)")
        
        return model
        
    except ValidationError as e:
        logger.error(f"Model validation failed for {input_file}: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to load model from {input_file}: {e}")
        raise


def save_model_dict(model_dict: Dict[str, Any], 
                   output_file: Union[str, Path], 
                   format: str = "auto") -> None:
    """
    Save a dictionary (e.g., from model.model_dump()) to file.
    
    Args:
        model_dict: Dictionary to save
        output_file: Path to save file
        format: File format ('json', 'yaml', 'ini', or 'auto')
    """
    output_file = Path(output_file)
    
    # Determine format from extension if auto
    if format == "auto":
        suffix = output_file.suffix.lower()
        if suffix in ['.yaml', '.yml']:
            format = "yaml"
        elif suffix in ['.ini', '.cfg', '.conf']:
            format = "ini"
        else:
            format = "json"
    
    try:
        # Ensure parent directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Save based on format
        if format == "yaml":
            _save_yaml(model_dict, output_file)
        elif format == "ini":
            _save_ini(model_dict, output_file)
        else:  # json
            _save_json(model_dict, output_file)
        
        logger.success(f"Dictionary saved to {output_file} ({format} format)")
        
    except Exception as e:
        logger.error(f"Failed to save dictionary to {output_file}: {e}")
        raise


def load_model_dict(input_file: Union[str, Path], 
                   format: str = "auto") -> Dict[str, Any]:
    """
    Load a dictionary from file.
    
    Args:
        input_file: Path to input file
        format: File format ('json', 'yaml', 'ini', or 'auto')
        
    Returns:
        Dictionary loaded from file
    """
    input_file = Path(input_file)
    
    if not input_file.exists():
        raise FileNotFoundError(f"File not found: {input_file}")
    
    # Determine format from extension if auto
    if format == "auto":
        suffix = input_file.suffix.lower()
        if suffix in ['.yaml', '.yml']:
            format = "yaml"
        elif suffix in ['.ini', '.cfg', '.conf']:
            format = "ini"
        else:
            format = "json"
    
    try:
        # Load data based on format
        if format == "yaml":
            return _load_yaml(input_file)
        elif format == "ini":
            return _load_ini(input_file)
        else:  # json
            return _load_json(input_file)
        
    except Exception as e:
        logger.error(f"Failed to load dictionary from {input_file}: {e}")
        raise


# ========================================================================
# Format-Specific Helper Functions
# ========================================================================

def _save_json(data: Dict[str, Any], output_file: Path) -> None:
    """Save data as JSON."""
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_json(input_file: Path) -> Dict[str, Any]:
    """Load data from JSON."""
    with open(input_file, 'r') as f:
        return json.load(f)


def _save_yaml(data: Dict[str, Any], output_file: Path) -> None:
    """Save data as YAML."""
    if not YAML_AVAILABLE:
        raise ValueError("PyYAML not installed - cannot save YAML format")
    
    with open(output_file, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, indent=2, 
                 allow_unicode=True, sort_keys=False)


def _load_yaml(input_file: Path) -> Dict[str, Any]:
    """Load data from YAML."""
    if not YAML_AVAILABLE:
        raise ValueError("PyYAML not installed - cannot load YAML format")
    
    with open(input_file, 'r') as f:
        return yaml.safe_load(f)


def _save_ini(data: Dict[str, Any], output_file: Path) -> None:
    """
    Save data as INI file.
    
    Note: INI format has limitations - nested dicts become sections,
    lists become comma-separated values, complex objects may not serialize well.
    """
    config = configparser.ConfigParser()
    
    # Convert nested dictionary to INI sections
    for key, value in data.items():
        if isinstance(value, dict):
            # Nested dict becomes a section
            config.add_section(key)
            for subkey, subvalue in value.items():
                config.set(key, subkey, _serialize_ini_value(subvalue))
        else:
            # Top-level values go in DEFAULT section
            if not config.has_section('DEFAULT'):
                config.add_section('DEFAULT')
            config.set('DEFAULT', key, _serialize_ini_value(value))
    
    with open(output_file, 'w') as f:
        config.write(f)


def _load_ini(input_file: Path) -> Dict[str, Any]:
    """
    Load data from INI file.
    
    Attempts to deserialize values back to appropriate types.
    """
    config = configparser.ConfigParser()
    config.read(input_file)
    
    result = {}
    
    # Process all sections
    for section_name in config.sections():
        if section_name == 'DEFAULT':
            # DEFAULT section items go to top level
            for key, value in config.items(section_name):
                result[key] = _deserialize_ini_value(value)
        else:
            # Other sections become nested dicts
            result[section_name] = {}
            for key, value in config.items(section_name):
                # Skip DEFAULT items that appear in other sections
                if key not in dict(config.items('DEFAULT')):
                    result[section_name][key] = _deserialize_ini_value(value)
    
    return result


def _serialize_ini_value(value: Any) -> str:
    """Convert a Python value to INI string representation."""
    if isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, (list, tuple)):
        return ', '.join(str(item) for item in value)
    elif isinstance(value, dict):
        # For nested dicts, use JSON representation
        return json.dumps(value)
    else:
        return str(value)


def _deserialize_ini_value(value: str) -> Any:
    """Convert INI string back to appropriate Python type."""
    # Try boolean
    if value.lower() in ('true', 'false'):
        return value.lower() == 'true'
    
    # Try integer
    try:
        return int(value)
    except ValueError:
        pass
    
    # Try float
    try:
        return float(value)
    except ValueError:
        pass
    
    # Try JSON (for complex objects)
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # Try comma-separated list
    if ',' in value:
        items = [item.strip() for item in value.split(',')]
        # Try to convert each item
        converted_items = []
        for item in items:
            converted_items.append(_deserialize_ini_value(item))
        return converted_items
    
    # Return as string
    return value


# ========================================================================
# Legacy Functions (maintained for compatibility)
# ========================================================================

def save_json_to_file(data: Dict[str, Any], file_path: Union[str, Path]) -> None:
    """
    Legacy function - save JSON data to file.
    
    Args:
        data: Dictionary to save
        file_path: Path to save file
    """
    save_model_dict(data, file_path, format="json")
