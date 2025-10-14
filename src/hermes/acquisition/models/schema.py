'''
Master schema for HERMES acquisition system configuration.

Schema Versioning:
-----------------
All configuration schemas include a schema_version field to ensure backward 
compatibility and enable data migration as the HERMES acquisition system evolves.

WHY SCHEMA VERSIONING IS CRITICAL:
=================================

1. **Data Preservation Across Software Updates**
   - Experimental data configurations must remain readable years later
   - Research reproducibility requires access to original acquisition parameters
   - Funding agencies and publications demand long-term data accessibility

2. **Beamtime Protection**
   - Neutron beamtime is extremely valuable and limited
   - Software updates during experiments must not break existing configurations
   - Users need confidence that their carefully tuned settings will work

3. **Collaborative Research**
   - Multiple institutions may use different HERMES versions
   - Configuration sharing between labs requires version compatibility
   - Standard measurement protocols need version-independent exchange

4. **Regulatory Compliance**
   - Scientific data management standards require metadata preservation
   - Audit trails must include software version information
   - Configuration provenance is essential for data validation

5. **Migration Safety**
   - Automatic detection of outdated configurations
   - Controlled migration with validation and rollback capability
   - Warning systems for deprecated features or breaking changes

REAL-WORLD SCENARIOS:
===================

Example 1: Lab upgrade discovers data from 2023 is unreadable because 
          detector configuration format changed

Example 2: Multi-user facility needs to support both legacy and new 
          acquisition workflows during transition period

Example 3: Publication review requires reproducing 2022 measurements
          with exact original parameters

Example 4: Beamtime interrupted by urgent software bug fix that changes
          configuration schema

Version History:
- 1.0.0: Initial layered architecture with SERVAL integration
- Future versions will be documented here with migration notes

The schema_version follows semantic versioning (MAJOR.MINOR.PATCH):
- MAJOR: Breaking changes requiring data migration
- MINOR: New optional fields, backward compatible
- PATCH: Bug fixes, no schema changes

When loading older configurations:
1. Check schema_version compatibility
2. Apply automatic migrations if needed
3. Warn users about deprecated fields
4. Preserve data integrity across version changes
'''

from pydantic import BaseModel, Field, field_validator
from typing import Optional
import re

from hermes.acquisition.models.software.environment import WorkingDir
from hermes.acquisition.models.software.serval import ServalConfig
from hermes.acquisition.models.software.parameters import RunSettings
from hermes.acquisition.models.software.epics import EPICSConfig
from hermes.acquisition.models.hardware.tpx3Cam import HardwareConfig
from hermes.acquisition.models.hardware.zabers import ZaberConfig

# Current schema version - update when making schema changes
CURRENT_SCHEMA_VERSION = "1.0.0"

class Default(BaseModel):  
    """
    Default acquisition schema combining all software and hardware configurations.
    
    This is the primary configuration schema for complete HERMES acquisitions
    including detector control, motion systems, and EPICS integration.
    """
    
    # Schema versioning for backward compatibility
    schema_version: str = Field(
        default=CURRENT_SCHEMA_VERSION,
        description="Schema version for backward compatibility and migration support"
    )
    
    # Software configuration
    environment: WorkingDir = Field(default_factory=WorkingDir)
    serval: ServalConfig = Field(default_factory=ServalConfig)
    run_settings: RunSettings = Field(default_factory=RunSettings)
    
    # Hardware configuration (optional)
    hardware: Optional[HardwareConfig] = Field(default=None, description="Hardware configuration (optional)")
    zabers: Optional[ZaberConfig] = Field(default=None, description="Zaber motor configuration (optional)")
    epics_control: Optional[EPICSConfig] = Field(default=None, description="EPICS control settings (optional)")
    
    # Global settings
    log_level: str = Field(default="INFO")
    
    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        """Validate schema version format and compatibility."""
        # Check semantic version format (MAJOR.MINOR.PATCH)
        if not re.match(r'^\d+\.\d+\.\d+$', v):
            raise ValueError(f"Schema version must follow semantic versioning (MAJOR.MINOR.PATCH), got: {v}")
        
        # Parse version components
        major, minor, patch = map(int, v.split('.'))
        current_major, current_minor, current_patch = map(int, CURRENT_SCHEMA_VERSION.split('.'))
        
        # Check compatibility (future versions not supported)
        if major > current_major:
            raise ValueError(f"Schema version {v} is newer than supported version {CURRENT_SCHEMA_VERSION}")
        
        # Even minor/patch increases in the same major version should be rejected during loading
        # This ensures we don't accidentally load configs meant for newer software
        if major == current_major and (minor > current_minor or 
                                     (minor == current_minor and patch > current_patch)):
            raise ValueError(f"Schema version {v} is newer than supported version {CURRENT_SCHEMA_VERSION}")
        
        # Major version 0 had different structure (if we ever had one)
        if major == 0:
            raise ValueError(f"Schema version {v} is too old and no longer supported")
            
        return v

class JustServal(BaseModel):  
    """
    SERVAL-only acquisition schema for testing SERVAL setup without hardware.
    
    Useful for:
    - SERVAL server development and testing
    - Software-only acquisition workflows  
    - Debugging SERVAL API communication
    """
    
    # Schema versioning
    schema_version: str = Field(
        default=CURRENT_SCHEMA_VERSION,
        description="Schema version for backward compatibility"
    )
    
    # Software configuration
    environment: WorkingDir = Field(default_factory=WorkingDir)
    serval: ServalConfig = Field(default_factory=ServalConfig)
    run_settings: RunSettings = Field(default_factory=RunSettings)

    # Global settings
    log_level: str = Field(default="INFO")
    
    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        """Validate schema version format and compatibility."""
        return Default.validate_schema_version(v)
    
class JustCamera(BaseModel):  
    """
    Camera-only acquisition schema for testing detector setup without SERVAL.
    
    Useful for:
    - Direct TPX3 hardware testing
    - Hardware validation and calibration
    - Testing without SERVAL dependency
    """
    
    # Schema versioning
    schema_version: str = Field(
        default=CURRENT_SCHEMA_VERSION,
        description="Schema version for backward compatibility"
    )
    
    # Software configuration
    environment: WorkingDir = Field(default_factory=WorkingDir)
    run_settings: RunSettings = Field(default_factory=RunSettings)
    
    # Hardware configuration (optional)
    hardware: Optional[HardwareConfig] = Field(default=None, description="Hardware configuration (optional)")
    
    # Global settings
    log_level: str = Field(default="INFO")
    
    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        """Validate schema version format and compatibility."""
        return Default.validate_schema_version(v)
    
class NoEpics(BaseModel):  
    """
    Complete acquisition schema without EPICS integration.
    
    Useful for:
    - Installations without EPICS infrastructure
    - Standalone detector systems  
    - Testing full acquisition workflows without beamline control
    """
    
    # Schema versioning
    schema_version: str = Field(
        default=CURRENT_SCHEMA_VERSION,
        description="Schema version for backward compatibility"
    )
    
    # Software configuration
    environment: WorkingDir = Field(default_factory=WorkingDir)
    serval: ServalConfig = Field(default_factory=ServalConfig)
    run_settings: RunSettings = Field(default_factory=RunSettings)
    
    # Hardware configuration (optional)
    hardware: Optional[HardwareConfig] = Field(default=None, description="Hardware configuration (optional)")
    zabers: Optional[ZaberConfig] = Field(default=None, description="Zaber motor configuration (optional)")
    
    # Global settings
    log_level: str = Field(default="INFO")
    
    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        """Validate schema version format and compatibility."""
        return Default.validate_schema_version(v)


# Utility functions for schema management
def get_current_schema_version() -> str:
    """Get the current schema version."""
    return CURRENT_SCHEMA_VERSION


def is_schema_compatible(version: str) -> bool:
    """
    Check if a schema version is compatible with the current version.
    
    Args:
        version: Schema version to check (MAJOR.MINOR.PATCH format)
        
    Returns:
        bool: True if compatible, False otherwise
    """
    try:
        major, minor, patch = map(int, version.split('.'))
        current_major, current_minor, current_patch = map(int, CURRENT_SCHEMA_VERSION.split('.'))
        
        # Same major version is compatible
        if major == current_major:
            return True
            
        # Newer major versions not supported
        if major > current_major:
            return False
            
        # Older major versions may need migration
        return major > 0  # Version 0.x.x is no longer supported
        
    except (ValueError, IndexError):
        return False


def needs_migration(version: str) -> bool:
    """
    Check if a configuration needs migration to current schema.
    
    Args:
        version: Schema version to check
        
    Returns:
        bool: True if migration is needed
    """
    if not is_schema_compatible(version):
        return False
        
    try:
        major, minor, patch = map(int, version.split('.'))
        current_major, current_minor, current_patch = map(int, CURRENT_SCHEMA_VERSION.split('.'))
        
        # Same version, no migration needed
        if version == CURRENT_SCHEMA_VERSION:
            return False
            
        # Older versions within same major version may need minor migrations
        return major == current_major and (minor < current_minor or patch < current_patch)
        
    except (ValueError, IndexError):
        return False