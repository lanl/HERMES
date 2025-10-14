# HERMES Acquisition Module

The acquisition module provides a comprehensive, schema-based system for configuring and controlling neutron imaging data acquisition with TPX3 cameras.

## Module Structure

The acquisition module follows a layered architecture pattern with clear separation of concerns:

```
src/hermes/acquisition/
├── __init__.py
├── README.md
├── logger.py
├── utils.py
│
├── models/                          # Data Models Layer - Pure Pydantic validation
│   ├── __init__.py
│   ├── schema.py                   # Master configuration schema
│   ├── hardware/                   # Hardware configuration models
│   │   ├── __init__.py
│   │   ├── tpx3Cam.py             # TPX3 detector & SERVAL API models
│   │   └── zabers.py              # Zaber motion control models
│   └── software/                   # Software configuration models
│       ├── __init__.py
│       ├── environment.py         # Working directory & file structure
│       ├── epics.py               # EPICS process variable models
│       ├── parameters.py          # Run settings & metadata models
│       ├── serval.py              # SERVAL software configuration models
│       └── serval.notes           # SERVAL API documentation
│
├── services/                        # Service Layer - External API communication
│   ├── __init__.py
│   ├── serval_client.py            # SERVAL HTTP API client
│   ├── zaber_client.py             # Zaber motion control client
│   └── epics_client.py             # EPICS process variable client
│
├── controllers/                     # Controller Layer - Business logic orchestration
│   ├── __init__.py
│   ├── acquisition_controller.py   # Main acquisition orchestrator
│   ├── calibration_controller.py   # Detector calibration workflows
│   └── motion_controller.py        # Motion control workflows
│
├── factories/                       # Factory Layer - Object creation & configuration
│   ├── __init__.py
│   ├── config_factory.py          # Configuration management & validation
│   └── client_factory.py          # Service client creation & initialization
│
├── workflows/                       # Workflow Layer - Complete procedures
│   ├── __init__.py
│   ├── standard_acquisition.py     # Standard measurement workflows
│   ├── calibration_workflows.py    # Complete calibration procedures
│   └── scan_workflows.py           # Multi-position scanning workflows
│
└── legacy/                          # Legacy support during transition
    ├── configure.py                # Original configuration management
    ├── initialize.py               # Original system initialization
    ├── calibrate.py                # Original calibration routines
    ├── serval.py                   # Original SERVAL interface
    ├── setup.py                    # Original setup procedures
    └── zaber.py                    # Original Zaber motor interface
```

## Architecture Layers

The acquisition module implements a layered architecture pattern that promotes separation of concerns, testability, and maintainability. Each layer has distinct responsibilities and clear interfaces:

### Quick Reference
- **Models**: Data structure definition and validation (*"What does the data look like?"*)
- **Services**: External system communication and integration (*"How do we communicate with external systems?"*)
- **Factories**: Object creation and configuration management (*"How do we build and configure system components?"*)
- **Controllers**: Business logic orchestration and workflow coordination (*"How do we orchestrate services to accomplish complex goals?"*)
- **Workflows**: Complete end-to-end user procedures (*"What complete tasks can users accomplish?"*)

### Models Layer (`models/`) - Data Structure & Validation
**Purpose**: Pure data validation and structure definition using Pydantic models

**Key Characteristics**:
- Pure data models with no external dependencies
- Comprehensive validation rules and type constraints
- Schema validation, type safety, serialization/deserialization
- **Examples**: `ServalConfig`, `DetectorConfig`, schema validation, hardware specifications

### Services Layer (`services/`) - External Communication
**Purpose**: Direct communication with external systems, APIs, and hardware

**Key Characteristics**:
- Protocol implementations (HTTP, serial, EPICS)
- Low-level hardware drivers and API clients
- Connection management and error handling
- **Dependencies**: Models for request/response validation
- **Examples**: SERVAL HTTP API calls, EPICS process variable reads, Zaber motor commands

### Factories Layer (`factories/`) - Object Creation & Configuration
**Purpose**: Create properly configured objects with dependency injection and lifecycle management

**Key Characteristics**:
- Configuration loading and validation
- Service client instantiation with proper settings
- Dependency injection and resource management
- **Dependencies**: Models, Services, Controllers
- **Examples**: Creating validated SERVAL clients, loading configurations from files, setting up logging

### Controllers Layer (`controllers/`) - Business Logic Orchestration
**Purpose**: Coordinate multiple services to implement cohesive business workflows

**Key Characteristics**:
- Multi-service coordination and sequencing
- Business rule implementation and acquisition logic
- Error recovery and state management
- **Dependencies**: Services and Models
- **Examples**: Initialize detector + configure SERVAL + start acquisition, calibration sequences

### Workflows Layer (`workflows/`) - End-to-End User Procedures
**Purpose**: Complete procedures that users directly interact with for accomplishing scientific tasks

**Key Characteristics**:
- High-level user-facing APIs
- Complete scientific procedures from start to finish
- Comprehensive error handling and user feedback
- **Dependencies**: All lower layers
- **Examples**: `quick_acquisition()`, `calibrate_detector()`, `run_scan()`, measurement campaigns

## Core Components

### Data Models (`models/`)

#### Master Configuration Schema (`schema.py`)
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

#### Software Configuration Models (`models/software/`)
- **`environment.py`**: `WorkingDir` - Directory structure and file organization
- **`serval.py`**: Multiple models for SERVAL API endpoints and configurations
- **`parameters.py`**: `RunSettings` - Acquisition run parameters and metadata
- **`epics.py`**: `EPICSConfig` - EPICS process variable configurations

#### Hardware Configuration Models (`models/hardware/`)
- **`tpx3Cam.py`**: Complete TPX3 detector and SERVAL API models for detector control
- **`zabers.py`**: `ZaberConfig` - Motor controller configuration and limits

### Service Layer (`services/`)

#### SERVAL API Client (`serval_client.py`)
- **Purpose**: Direct HTTP communication with SERVAL acquisition server
- **Features**: Type-safe API calls using Pydantic models for validation
- **Endpoints**: Server control, detector management, measurement control, configuration

#### Hardware Clients
- **`zaber_client.py`**: Direct communication with Zaber motion controllers
- **`epics_client.py`**: EPICS process variable monitoring and control

### Controller Layer (`controllers/`)

#### Acquisition Controller (`acquisition_controller.py`)
- **Purpose**: Orchestrate complete acquisition workflows
- **Features**: Initialize detectors, configure measurements, monitor progress
- **Integration**: Combines SERVAL, motion control, and EPICS systems

#### Specialized Controllers
- **`calibration_controller.py`**: Detector calibration and characterization workflows
- **`motion_controller.py`**: Complex motion sequences and positioning

### Factory Layer (`factories/`)

#### Configuration Factory (`config_factory.py`)
- **Purpose**: Enhanced configuration management and object creation
- **Features**: Load/save configurations, create service clients, validate settings
- **Evolution**: Replaces and enhances original `configure.py` functionality

#### Client Factory (`client_factory.py`)
- **Purpose**: Create properly configured service clients
- **Features**: Dependency injection, connection management, error handling

### Workflow Layer (`workflows/`)

#### Standard Acquisition (`standard_acquisition.py`)
- **Purpose**: Complete end-to-end measurement procedures
- **Features**: One-function acquisition, error recovery, data validation
- **Usage**: Primary user interface for common acquisition tasks

#### Specialized Workflows
- **`calibration_workflows.py`**: Complete calibration procedures
- **`scan_workflows.py`**: Multi-position scanning with motion control

### Legacy Support (`legacy/`)

During the transition period, original implementations remain available:
- **`configure.py`**: Original configuration management
- **`initialize.py`**: Original system initialization  
- **`serval.py`**: Original SERVAL interface
- **`calibrate.py`**, **`setup.py`**, **`zaber.py`**: Original hardware interfaces

## Usage Workflows

### Simple Acquisition (New Workflow Layer)
```python
from hermes.acquisition.workflows.standard_acquisition import quick_acquisition

# Single-function acquisition - handles everything internally
result = quick_acquisition(
    working_dir="/data/experiments/test_run_001",
    exposure_time=0.1,
    n_triggers=100,
    mode="tot"
)
```

### Advanced Configuration (Factory Layer)
```python
from hermes.acquisition.factories.config_factory import ConfigurationManager
from hermes.acquisition.controllers.acquisition_controller import AcquisitionController

# Create and customize configuration
config_manager = ConfigurationManager()
config_manager.setup_environment(
    path_to_working_dir="/data/experiments",
    run_dir_name="test_run_001"
)
config_manager.setup_serval(host="192.168.1.100", port=8080)
config_manager.setup_zabers(port="/dev/ttyUSB0")

# Use controller for fine-grained control
with AcquisitionController(config_manager) as controller:
    controller.initialize_detector()
    controller.setup_acquisition(exposure_time=0.1, n_triggers=100)
    controller.run_acquisition()
```

### Service Layer Access (For Advanced Users)
```python
from hermes.acquisition.services.serval_client import ServalAPIClient
from hermes.acquisition.models.software.serval import ServalConfig

# Direct SERVAL API access
serval_config = ServalConfig(host="192.168.1.100", port=8080)
with ServalAPIClient(serval_config) as client:
    detector_info = client.get_detector_info()
    client.connect_detector()
    client.start_measurement()
```

### Migration from Legacy Code
```python
# Legacy approach (still supported)
from hermes.acquisition.legacy.configure import create_default_config
from hermes.acquisition.legacy.initialize import initialize_hermes_system

# Gradually migrate to new architecture
from hermes.acquisition.workflows.standard_acquisition import migrate_from_legacy

# Automatic migration assistance
new_result = migrate_from_legacy(legacy_config)
```

## Key Features

### Layered Architecture
- **Clear separation of concerns** across models, services, controllers, factories, and workflows
- **Dependency injection** through factory pattern for better testability
- **Backward compatibility** with legacy code during transition period

### Type Safety and Validation
- All configurations use Pydantic models for automatic validation
- Type hints throughout for IDE support and error catching
- Runtime validation of configuration parameters and API responses

### SERVAL Integration
- **Complete API coverage** with type-safe Pydantic models matching SERVAL JSON schemas
- **Automatic request/response validation** for all SERVAL endpoints
- **High-level orchestration** combining detector control, measurement, and file management

### Modular Hardware Support
- Clear separation between software and hardware components
- Optional hardware components for software-only testing
- Extensible design for adding new hardware types (cameras, motion controllers, etc.)

### Configuration Management
- Save/load configurations as JSON or YAML files
- Version-controlled configuration management
- Template-based configuration for common acquisition types

### Comprehensive Error Handling
- Graceful error recovery in controllers and workflows
- Detailed logging with context at each layer
- Service health monitoring and connection management

### Testing & Development
- **Unit testable components** at each layer with clear interfaces
- **Mock services** for testing without hardware
- **Integration testing** support with real hardware

## Development Status

### Implemented ✅
- **Models Layer**: Complete Pydantic models for SERVAL API and hardware configuration
- **Configuration Schema**: Unified `Default` schema combining all system components
- **Directory Management**: Working directory structure and validation
- **Logging System**: Centralized logging with loguru integration
- **SERVAL Models**: Complete type-safe models matching SERVAL API endpoints

### In Progress 🔄
- **Services Layer**: SERVAL HTTP client, Zaber motion client, EPICS client implementation
- **Controllers Layer**: Acquisition controller and workflow orchestration
- **Factory Layer**: Enhanced configuration management and service instantiation
- **Legacy Migration**: Gradual transition from existing implementation

### Planned 📋
- **Workflows Layer**: Complete end-to-end acquisition procedures
- **Calibration System**: Automated detector calibration workflows
- **Scanning Capabilities**: Multi-position acquisition with motion control
- **Error Recovery**: Advanced error handling and system recovery
- **Performance Optimization**: Streaming data handling and memory management
- **Testing Suite**: Comprehensive unit and integration testing

## Dependencies

### Core Dependencies
- **Pydantic v2**: Configuration validation and serialization with type safety
- **Loguru**: Advanced logging functionality with structured output
- **PyYAML**: YAML configuration file support
- **Pathlib**: Modern path handling and directory management

### Service Layer Dependencies
- **httpx**: Async HTTP client for SERVAL API communication
- **pyepics**: EPICS process variable monitoring and control (optional)
- **zaber-motion**: Zaber motion controller communication (optional)

### Development Dependencies
- **pytest**: Unit and integration testing framework
- **pytest-asyncio**: Async testing support
- **httpx-mock**: HTTP client mocking for testing
- **coverage**: Test coverage analysis

## Contributing

When adding new functionality to the layered architecture:

### 1. **Models Layer** - Adding New Data Models
- Add new Pydantic models to appropriate `models/software/` or `models/hardware/` directories
- Update `schema.py` to include new configuration components in the `Default` schema
- Ensure all models have proper validation and type hints
- Add model documentation and examples

### 2. **Services Layer** - Adding New External Integrations
- Create new service clients in `services/` following the established pattern
- Use Pydantic models for all request/response validation
- Implement proper error handling and connection management
- Add comprehensive logging for debugging

### 3. **Controllers Layer** - Adding New Business Logic
- Create controllers in `controllers/` that orchestrate multiple services
- Focus on business logic rather than protocol implementation
- Implement proper error recovery and state management
- Use dependency injection for testability

### 4. **Factories Layer** - Adding Configuration Support
- Extend `config_factory.py` for new configuration requirements
- Add client creation methods to `client_factory.py` 
- Ensure proper validation and default handling
- Support both programmatic and file-based configuration

### 5. **Workflows Layer** - Adding User-Facing Procedures
- Create complete end-to-end procedures in `workflows/`
- Provide simple APIs that hide complexity from users
- Implement comprehensive error handling and recovery
- Add progress monitoring and user feedback

### Testing Strategy
- **Unit Tests**: Test each layer independently with mocking
- **Integration Tests**: Test layer interactions with real or simulated services
- **End-to-End Tests**: Test complete workflows with hardware simulation
- **Documentation Tests**: Ensure all examples in README work correctly

### Code Standards
- Follow the established patterns for type hints, validation, and error handling
- Use Pydantic models for all data validation at layer boundaries
- Implement proper logging with context information
- Add comprehensive docstrings with examples
- Maintain backward compatibility during transitions
