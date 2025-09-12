# HERMES Acquisition Module

The acquisition module provides a comprehensive, schema-based system for configuring and controlling neutron imaging data acquisition with TPX3 cameras.

## Module Structure

```
src/hermes/acquisition/
├── __init__.py
├── configure.py              # Configuration management (create, load, save configs)
├── initialize.py             # System initialization from configurations
├── acquire.py               # Main acquisition control logic
├── logger.py                # Centralized logging with loguru
├── serval.py                # Serval server communication
├── zaber.py                 # Zaber motor controller interface
├── calibrate.py             # Calibration routines
├── setup.py                 # System setup utilities  
├── utils.py                 # General utility functions
├── legacy/                  # Legacy code (deprecated)
│   └── models.py
└── models/
    ├── __init__.py
    ├── schema.py            # Master configuration schema (Default class)
    ├── software/            # Software configuration models
    │   ├── __init__.py
    │   ├── environment.py   # WorkingDir - directory management
    │   ├── serval.py        # ServalConfig - server settings
    │   ├── parameters.py    # RunSettings - acquisition parameters
    │   └── epics.py         # EPICSConfig - process variable settings
    └── hardware/            # Hardware configuration models
        ├── __init__.py
        ├── tpx3Cam.py       # HardwareConfig - detector/SPIDR settings
        └── zabers.py        # ZaberConfig - motor controller settings
```

## Core Components

### Configuration Management

#### `schema.py` - Master Configuration Schema
- **Purpose**: Define the complete system configuration as a unified data structure
- **Focus**: Type safety, validation, and structural integrity of all settings
- **Key Class**: `Default` - combines all software and hardware configurations

```
Default
├── Software Components (Required)
│   ├── environment: WorkingDir
│   ├── serval: ServalConfig  
│   ├── run_settings: RunSettings
│   └── epics_control: EPICSConfig (Optional)
├── Hardware Components (Optional)
│   ├── hardware: HardwareConfig
│   └── zabers: ZaberConfig
└── Global Settings
    └── log_level: str
```

#### `configure.py` - Configuration Manager
- Create, modify, validate, and persist configuration objects
- Load/save configurations from JSON/YAML files
- Provides `ConfigurationManager` class for managing all configuration aspects

#### `initialize.py` - System Initialization
- Transform configurations into operational system state
- Create directories, setup logging, initialize hardware connections
- Accepts `Default` configuration objects and makes them operational

### Hardware Integration

#### `serval.py` - Serval Server Communication
- Interface for communicating with Serval data acquisition server
- Handles server connection, data streaming, and control commands

#### `zaber.py` - Motor Controller Interface  
- Control Zaber linear actuators and rotation stages
- Motor positioning, velocity control, and coordinate system management

#### `calibrate.py` - Calibration Routines
- Detector calibration procedures
- Energy calibration and geometric corrections

### Data Models

#### Software Configuration Models (`models/software/`)
- **`environment.py`**: `WorkingDir` - Directory structure and file organization
- **`serval.py`**: `ServalConfig` - Server connection parameters
- **`parameters.py`**: `RunSettings` - Acquisition run parameters and metadata
- **`epics.py`**: `EPICSConfig` - EPICS process variable configurations

#### Hardware Configuration Models (`models/hardware/`)
- **`tpx3Cam.py`**: `HardwareConfig` - TPX3 detector and SPIDR readout settings
- **`zabers.py`**: `ZaberConfig` - Motor controller configuration and limits

## Usage Workflow

### 1. Configure System
```python
from hermes.acquisition.configure import create_default_config

# Create configuration manager
manager = create_default_config()

# Setup components
manager.setup_environment(
    path_to_working_dir="/data/experiments",
    run_dir_name="test_run_001"
)
manager.setup_serval(host="192.168.1.100", port=8080)
manager.setup_zabers(port="/dev/ttyUSB0")

# Get complete configuration
config = manager.get_config()  # Returns Default schema object
```

### 2. Initialize System
```python
from hermes.acquisition.initialize import initialize_hermes_system

# Make configuration operational
runtime = initialize_hermes_system(config)
# Creates directories, starts logging, initializes hardware
```

### 3. Execute Acquisition
```python
from hermes.acquisition.acquire import run_acquisition

# Run data acquisition with initialized system
results = run_acquisition(runtime)
```

## Key Features

### Type Safety and Validation
- All configurations use Pydantic models for automatic validation
- Type hints throughout for IDE support and error catching
- Runtime validation of configuration parameters

### Modular Architecture  
- Clear separation between software and hardware components
- Optional hardware components for software-only testing
- Extensible design for adding new hardware types

### Configuration Persistence
- Save/load configurations as JSON or YAML files
- Version-controlled configuration management
- Easy deployment of standardized configurations

### Comprehensive Logging
- Centralized logging with loguru for structured output
- Configurable log levels and file output
- Integration with directory structure for organized log files

## Development Status

### Implemented
- ✅ Configuration schema architecture
- ✅ Directory management and validation
- ✅ Logging system integration
- ✅ Basic Pydantic model framework

### In Progress  
- 🔄 Serval server integration
- 🔄 Zaber motor controller implementation
- 🔄 Hardware initialization routines
- 🔄 EPICS process variable integration

### Planned
- 📋 Complete acquisition control logic
- 📋 Calibration procedure implementation
- 📋 Error handling and recovery
- 📋 Performance optimization

## Dependencies

- **Pydantic**: Configuration validation and serialization
- **Loguru**: Advanced logging functionality
- **PyYAML**: YAML configuration file support
- **Pathlib**: Modern path handling

## Contributing

When adding new functionality:

1. **Configuration**: Add new models to appropriate `models/software/` or `models/hardware/` directories
2. **Integration**: Update `schema.py` to include new configuration components  
3. **Initialization**: Add initialization logic to `initialize.py`
4. **Documentation**: Update this README and add docstrings

Follow the established patterns for type hints, validation, and error handling.
