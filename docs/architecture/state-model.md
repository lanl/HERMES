# State Model

`src/hermes/state/` owns the Pydantic state of record. These models should be
durable enough to save to YAML and load later.

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
The initial `HermesRecord` is recorded by the state logger. Every later durable
state change is also logged with the changed state path, previous value, new
value, status, proposer, origin, approver or approval-bypass marker, and
timestamps. This creates an audit trail that can reconstruct the state at any
point in the measurement, assuming any external payload files referenced by the
state are still available.

Large configuration structures that are part of reproducibility, such as SERVAL
`PixelConfig` or DAC settings, are still state values. They should be recorded
when they first enter state and only recorded again if they change. If a value is
too large or awkward to duplicate inline in the state log, the value may be saved
as a separate payload file under `logs/payloads/` and represented in the record
and state log by an `ExternalPayloadRef`.

Operational logs are not the source of truth for reconstructing state. They may
reference state paths, hashes, and payload references, but they should not
duplicate full state payloads.

The final `HermesRecord` should be saved to disk as a YAML file for later
reference. YAML is the primary persisted record format because it is readable and
practical for user-authored run inputs. JSON may still be supported as an
optional export format for tools that need strict machine-readable records, but
the Pydantic `HermesRecord` schema remains the canonical contract.

## Expected model groups ###
Expected model groups and their responsibilities include:
- MeasurementInfo: metadata about the measurement, including measurement ID, run number, beamline, proposal ID, image intensifier serial number, scintillator serial number, sample name, operator name, log notes, and any other relevant metadata fields that are important for provenance and record-keeping.
- RuntimeEnvironment: information about the runtime environment used for the measurement, including `Path` fields for working directory, data directory, raw data directory, analyzed data directory, log directory, preview directory, optional config directory, executable paths, and any other relevant environment information.
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

#### ExternalPayloadRef ####
Large durable state values may be externalized into files under the run's
`logs/payloads/` directory. There should not be a separate `state_payload_dir`.
In that case, the state field should contain an
`ExternalPayloadRef` rather than a bare path string.

```python
ExternalPayloadRef
  kind: Literal["external_payload_ref"]
  path: Path
  media_type: str
  sha256: str
  size_bytes: int
  created_at: datetime
  description: str | None
  source_path: Path | None
```

The `path` should be relative to the run `working_dir` or to the persisted
record location so the record can be moved as a bundle. The hash and size make
the external payload verifiable when reconstructing or reloading state.

Fields that may be large should use a typed union rather than loose `Any`. For
example:

```python
pixel_config: str | ExternalPayloadRef
dacs: list[dict[str, int]] | ExternalPayloadRef
```

The Pydantic model should validate the shape of `ExternalPayloadRef`, but it
should not write files. External payload file creation belongs in
`hermes.state_service`.

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
The RuntimeEnvironment model should capture all relevant information about the
runtime environment used for the measurement. Directory and executable path
fields should be `Path` values in the model, not loose strings. The canonical
directory field names are:
- `working_dir`
- `data_dir`
- `raw_data_dir`
- `analyzed_data_dir`
- `log_dir`
- `preview_dir`
- `config_dir`, if needed

```python
RuntimeEnvironment
  working_dir: Path
  data_dir: Path
  raw_data_dir: Path
  analyzed_data_dir: Path
  log_dir: Path
  preview_dir: Path
  config_dir: Path | None
  empir_path: Path | None
  hermes_tpx3_spidr_binary: Path
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
  serval_url: str
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

## Expected file structure of src/hermes/state/ ###
The `src/hermes/state/` directory should be organized into a top-level `state.py` file that defines the top-level aggregate model (e.g. `HermesRecord`) and a `models/` subdirectory that contains the individual models for measurement info, acquisition state, analysis state, environment state, and any shared models or enums.

```text
src/
└── hermes/
    └── state/
        ├── __init__.py         # makes state a Python package. Keep __init__.py empty!
        ├── state.py            # top-level aggregate model
        │
        └── models/
            ├── __init__.py                 # makes models a Python package. Keep __init__.py empty!
            ├── measurement.py              # measurement info and metadata
            ├── payloads.py                 # external payload reference models
            ├── analysis/                   # analysis environments that are unioned in the top-level record
            │   ├── empir.py                # EMPIR analysis environment, configuration, and related settings
            │   └── hermes_tpx3_spidr.py    # TPX3 SPIDR analysis environment, configuration, and related settings
            ├── acquisition/                # acquisition environments that are unioned in the top-level record
            │   ├── serval.py               # SERVAL acquisition environment, configuration, and related settings
            │   ├── pymepix.py              # PyMEPIX acquisition environment, configuration, and related settings
            │   └── mcp2hist.py             # MCP2Hist acquisition environment, configuration, and related settings
            ├── detector.py                 # TPX3Cam, SERVAL, chip, layout, health, and detector config metadata
            ├── environment.py              # working directories, data directories, log directories, preview directories, analysis directories, and config directories
            └── shared_models.py            # shared models and enums for the state models
``` 
