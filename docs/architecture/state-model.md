# State Model

`src/state/` owns the Pydantic state of record. These models should be
durable enough to save to JSON and load later.

The central object in HERMES is a Pydantic model that records:

- what acquisition was requested
- what detector, SERVAL, and run configuration was used
- what runtime environment, tool locations, tool versions, and directories were used
- what actually happened during acquisition
- what files and derived artifacts were produced
- what analysis was requested
- what analysis actually ran
- what summary results, warnings, and errors were produced

The model should contain metadata, configuration, provenance, and summary
results. It should not contain large raw arrays, full decoded event tables, image
stacks, generated plots, detector data files, or build products.

## How model is used to keep a record of acquisition and analysis
The initial model is recorded in a log, then every change to the model is logged with initial and final values. This creates a complete reconstructable model at any point in time during the acquisition and analysis process. The final model is saved to disk as a JSON file for later reference.

## Expected model groups ###
Expected model groups and their responsibilities include:
- MeasurementInfo: metadata about the measurement, including measurement ID, run number, beamline, proposal ID, image intensifier serial number, scintillator serial number, sample name, operator name, log notes, and any other relevant metadata fields that are important for provenance and record-keeping.
- RuntimeEnvironment: information about the runtime environment used for the measurement, including working directory, data directory, log directory, preview directory, analysis directory, and any other relevant environment information.
- AcquisitionState: modality-specific information about the acquisition process, using discriminated unions to allow for different fields based on the acquisition modes (e.g. serval, pymepix, mcp2hist).
- AnalysisState: modality-specific information about the analysis process, using discriminated unions to allow for different fields based on the analysis modes (e.g. empir, hermes_tpx3_spidr).

The models should use discriminated unions for modality-specific acquisition and analysis plans once the modalities are known.

The top-level record should explicitly include environment state:

### Expected model structures ###

#### HermesRecord ####
The top-level record should explicitly include measurement metadata, acquisition state, analysis state, and environment state. This keeps all durable information about the run in one place and makes it easy to save and load the complete record.

```python
HermesRecord
  measurement_info: MeasurementInfo
  environment: RuntimeEnvironment
  acquisition: AcquisitionState
  analysis: AnalysisState
```

#### MeasurementInfo ####
MeasurementInfo should capture all relevant metadata about the measurement, including:
- measurement ID
- run number
- beamline
- proposal ID
- image intensifier serial number
- scintillator serial number
- sample name
- operator name
- log notes
- any other relevant metadata fields that are important for provenance and record-keeping

```python
MeasurementInfo
  measurement_id: str
  run_number: int
  beamline: str | None
  proposal_id: str | None
  image_intensifier_sn: str | None
  scintillator_sn: str | None
  sample_name: str | None
  operator_name: str | None
  log_notes: str | None
  ...
```

#### RuntimeEnvironment ####
The RuntimeEnvironment model should capture all relevant information about the runtime environment used for the measurement, including:
- working directory
- data directory
- log directory
- preview directory
- analysis directory

```python
RuntimeEnvironment
  working_directory: str
  data_directory: str
  log_directory: str
  preview_directory: str
  analysis_directory: str
  ...
```

#### AcquisitionState ####
AcquisitionState should capture modality-specific information about the acquisition process. It should use discriminated unions to allow for different fields based on the acquisition modes.

```python
AcquisitionState
  mode: serval | pymepix | mcp2hist
  ...
```

Depending on the mode, the AcquisitionState may include different fields. For example, if the mode is `serval`, it may include fields for SERVAL environment, configuration, and detector information:

##### ServalAcquisitionState ####
```python 
serval
  serval_environment: ServalEnvironment
  destination_configuration: DestinationConfig
  detector_info: DetectorInfo 
  ...

ServalEnvironment
  version: str
  path: str
  destination_configuration: DestinationConfig
  detector_info: DetectorInfo 
  ...
```
NOTE: for ServalEnviroment fields and submodels please reference 20231023_ASIServer_TPX3_manual_V3.3.pdf

#### AnalysisState ####
AnalysisState should capture modality-specific information about the analysis process. It should use discriminated unions to allow for different fields based on the analysis modes.

```python
AnalysisState
  mode: hermes_tpx3_spidr | empir
```

Depending on the mode, the AnalysisState may include different fields. For example, if the mode is `hermes_tpx3_spidr`, it may include fields for the HERMES TPX3 SPIDR analysis environment, configuration, and cluster configuration:

##### HermesTpx3SpidrAnalysisState ####
```python
hermes_tpx3_spidr
  cluster_config: ClusterConfig
```

If the mode is `empir`, it may include fields for the EMPIR analysis environment, configuration, and related settings:

##### EmpirAnalysisState ####
```python
empir
  empir_environment: EmpirEnvironment
  empir_config: EmpirConfig
  pixel_to_photon_config: PixelToPhotonConfig
  photon_to_event_config: PhotonToEventConfig
  exporter_config: ExporterConfig
  ...
```

## Expected file structure of state/ ###
The `state/` directory should be organized into a top-level `state.py` file that defines the top-level aggregate model (e.g. `HermesRecord`) and a `models/` subdirectory that contains the individual models for measurement info, acquisition state, analysis state, environment state, and any shared models or enums.

```text
state/
├── __init__.py         # makes state a Python package. Keep __init__.py empty!
├── state.py            # top-level aggregate model
│
└── models/
    ├── __init__.py                 # makes models a Python package. Keep __init__.py empty!
    ├── measurement.py              # measurement info and metadata
    ├── analysis/                   # analysis environments that are unioned in the top-level record
    │   ├── empir.py                # EMPIR analysis environment, configuration, and related settings
    │   └── hermes_tpx3_spidr.py    # TPX3 SPIDR analysis environment, configuration, and related settings
    ├── acquisition/                # acquisition environments that are unioned in the top-level record
    │   ├── serval.py               # SERVAL acquisition environment, configuration, and related settings
    │   └── pymepix.py              # PyMEPIX acquisition environment, configuration, and related settings
    ├── detector.py                 # TPX3Cam, SERVAL, chip, layout, health, and detector config metadata
    ├── environment.py              # working directories, data directories, log directories, preview directories, analysis directories, and config directories
    └── shared_models.py            # shared models and enums for the state models
``` 