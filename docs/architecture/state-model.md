# State Model

`src/hermes/models/` owns the Pydantic state of record. These models should be
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

### Expected model groups
Expected model groups and their responsibilities include:

- `record.py`: top-level run or experiment record
- `infomation.py`: measurement info like measurement ID, run number, beamline, proposal ID, image intensifier sn, and other metadata
- `acquisition/serval.py` and `acquisition/pymepix.py`: acquisition environments, configurations, and other metadata pertinent to acquisition state and provenance
- `analysis/empir.py` and `analysis/hermes_tpx3_spidr.py`: analysis evnvironment, configurations, and other metadata pertinent to analysis state and provenance
- `detector.py`: TPX3Cam, SERVAL, chip, layout, health, and detector config metadata
- `environment.py`: working directories, data directories, log directories, preview directories, analysis directories, and config directories 
- `enums.py`: shared enums for status, artifact kinds, acquisition modes, and analysis modes

The models should use discriminated unions for modality-specific acquisition and
analysis plans once the modalities are known.

The top-level record should explicitly include environment state:

```text
HermesRecord
  measurement_info: MeasurementInfo
  environment: RuntimeEnvironment
  acquisition: AcquisitionState
  analysis: AnalysisState

MeasurementInfo
  measurement_id: str
  run_number: int
  beamline: str | None
  proposal_id: str | None
  image_intensifier_sn: str | None
  scintillator_sn: str | None
  sample_name: str | None
  operator_name: str | None
  log_note: str | None
  ...

RuntimeEnvironment
  working_directory: str
  data_directory: str
  log_directory: str
  preview_directory: str
  analysis_directory: str
  ...

AcquisitionState
  mode: serval | pymepix | mcp2hist
  ...

serval
  serval_environment: ServalEnvironment
  destination_configuration: DestinationConfig
  detector_info: DetectorInfo 
  ...

AnalysisState
  mode: hermes_tpx3_spidr | empir
  
hermes_tpx3_spidr
  cluster_config: ClusterConfig

empir
  empir_environment: EmpirEnvironment
  empir_config: EmpirConfig
  pixel_to_photon_config: PixelToPhotonConfig
  photon_to_event_config: PhotonToEventConfig
  exporter_config: ExporterConfig
  ...

ServalEnvironment
  version: str
  path: str
  destination_configuration: DestinationConfig
  detector_info: DetectorInfo 
  ...

NOTE: for ServalEnviroment fields and submodels please reference 20231023_ASIServer_TPX3_manual_V3.3.pdf

```

This keeps runtime paths, external tool locations, and versions in the durable
state model instead of scattering them across scripts or logs.

