# State Model

`src/hermes/state/` owns the Pydantic state of record. These models should be
durable enough to save to YAML and load later.

The central object in HERMES is a Pydantic model that records:

- what acquisition was requested, when HERMES is used for acquisition
- what detector, SERVAL, and run configuration was used, when available
- what runtime environment, tool locations, tool versions, and directories were used
- what actually happened during acquisition
- which raw TPX3 files, Parquet output directories, images, and plots were
  produced
- what analysis was requested, when HERMES is used for analysis
- what analysis actually ran, when available
- what summary results, warnings, and errors were produced

The model should contain metadata, configuration, provenance, and summary
results. It should not contain raw packet bytes, full pixel-hit or TDC-hit
tables, image stacks, generated plots, detector data files, or build products.

## How model is used to keep a record of acquisition and analysis
The initial `HermesRecord` is recorded by the state logger. Every later durable
state change is also logged with the changed state path, previous value, new
value, status, proposer, origin, approver or approval-bypass marker, and
timestamps. This creates an audit trail that can reconstruct the state at any
point in the measurement, assuming any separately saved detector-configuration
files or other state-value files referenced by the state are still available.

Large configuration structures that are part of reproducibility, such as the
detector `PixelConfig` or DAC settings observed through SERVAL, are still state
values. They should be recorded when they first enter state and only recorded
again if they change. If a value is too large or awkward to duplicate inline in
the state log, it may be saved as a separate detector-configuration file under
`logs/payloads/`. The record and state log then contain an `ExternalPayloadRef`
that identifies that file.

Operational logs are not the source of truth for reconstructing state. They may
reference state paths, file hashes, and `ExternalPayloadRef` values, but they
should not duplicate complete detector configurations or other large state
values.

The final `HermesRecord` should be saved to disk as a YAML file for later
reference. YAML is the primary persisted record format because it is readable and
practical for user-authored run inputs. JSON may still be supported as an
optional export format for tools that need strict machine-readable records, but
the Pydantic `HermesRecord` schema remains the canonical contract.

## Expected model groups ###
Expected model groups and their responsibilities include:
- MeasurementInfo: metadata about the measurement, including measurement ID, run number, beamline, proposal ID, image intensifier serial number, scintillator serial number, sample name, operator name, log notes, and any other relevant metadata fields that are important for provenance and record-keeping.
- RuntimeEnvironment: information about the runtime environment used for the measurement, including `Path` fields for working directory, data directory, raw data directory, analyzed data directory, log directory, preview directory, optional config directory, executable paths, and any other relevant environment information.
- DetectorSnapshot: TPX3Cam hardware identity, chip identity, layout, health, and applied detector configuration read from detector-specific endpoints.
- AcquisitionState: optional requested settings, applied settings, status, and
  output files for SERVAL, PyMEPix, or MCP2Hist acquisition.
- AnalysisState: optional input files, settings, status, output directories, and
  summary files for EMPIR or `hermes_tpx3_spidr` analysis.

Each supported acquisition or analysis program should have its own Pydantic
model. The `mode` field tells Pydantic which model to load from YAML.

The top-level record should explicitly include environment state:

### Expected model structures ###

#### HermesRecord ####
The top-level record should explicitly include measurement metadata and
environment state. Acquisition state and analysis state are optional because
HERMES may be used to acquire data only, analyze existing data only, or do both
in one run. This keeps all durable information that exists for the run in one
place and makes it easy to save and load the complete record.

```python
HermesRecord
  measurement_info: MeasurementInfo
  environment: RuntimeEnvironment
  acquisition: AcquisitionState | None = None
  analysis: AnalysisState | None = None
```

An acquisition-only record should leave `analysis` unset. An analysis-only record
should leave `acquisition` unset and list its input files directly in the
analysis state instead of creating fake acquisition state. A full
acquisition-to-analysis workflow may populate both fields.

#### FileReference ####
When the record needs more than a file path, use a `FileReference` to store
basic file metadata. This model is for files, not directories. Output directories
should use a clearly named `Path` field, such as `tpx3_parquet_directory`.

```python
FileReference
  path: Path
  media_type: str | None
  sha256: str | None
  size_bytes: int | None
  created_at: datetime | None
  description: str | None
```

#### ExternalPayloadRef ####
Large detector configurations or other durable state values may be saved in
separate files under the run's `logs/payloads/` directory. There should not be a
separate `state_payload_dir`. When a state value is saved this way, its state
field should contain an `ExternalPayloadRef` rather than a bare path string.

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
the saved detector-configuration file or other state-value file verifiable when
reconstructing or reloading state.

Fields that may be large should use a typed union rather than loose `Any`. For
example:

```python
pixel_config: str | ExternalPayloadRef
dacs: list[dict[str, int]] | ExternalPayloadRef
```

The Pydantic model should validate the shape of `ExternalPayloadRef`, but it
should not write files. Saving detector configurations or other large state
values in separate files belongs in `hermes.state_service`.

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

#### DetectorSnapshot ####
DetectorSnapshot should capture durable TPX3Cam facts and detector-facing state
needed to reproduce or audit a run. It should not represent the SERVAL backend
session as a whole. In SERVAL mode, detector snapshots are populated from
detector-specific endpoints:

```python
DetectorSnapshot
  captured_at: datetime
  info: DetectorInfo | None
  health: DetectorHealth | None
  layout: DetectorLayout | None
  configuration: DetectorConfiguration | None
```

`DetectorInfo`, `DetectorHealth`, and `DetectorLayout` should model the JSON
response bodies returned by the SERVAL detector endpoints, with aliases for
backend JSON keys and Pythonic field names in HERMES code:

```python
DetectorInfo
  iface_name: str | None
  software_version: str | None
  firmware_version: str | None
  pixel_count: int | None
  row_length: int | None
  number_of_chips: int | None
  number_of_rows: int | None
  medipix_type: int | None
  boards: list[DetectorInfoBoard]
  supported_acquisition_modes: int | None
  clock_readout_mhz: float | None
  max_pulse_count: int | None
  max_pulse_height: float | None
  max_pulse_period_s: float | None
  timer_max_s: float | None
  timer_min_s: float | None
  timer_step_s: float | None
  clock_timepix_mhz: float | None

DetectorInfoBoard
  chipboard_id: str | None
  ip_address: str | None
  firmware_version: str | None
  chips: list[DetectorInfoChip]

DetectorInfoChip
  index: int
  id: int
  name: str

DetectorHealth
  local_temperature_c: float | None
  fpga_temperature_c: float | None
  chip_temperatures_c: list[int]
  fan1_speed_rpm: int | None
  fan2_speed_rpm: int | None
  avdd: list[float] | None
  vdd: list[float] | None
  bias_voltage_v: float | None
  humidity_percent: int | None

DetectorLayout
  detector_orientation: UP | RIGHT | DOWN | LEFT | *_MIRRORED | None
  original: DetectorLayoutCanvas | None
  rotated: DetectorLayoutCanvas | None

DetectorLayoutCanvas
  width: int
  height: int
  chips: list[DetectorLayoutChip]

DetectorLayoutChip
  chip: int
  x: int
  y: int
  orientation: LtRBtT | RtLBtT | LtRTtB | RtLTtB | BtTLtR | TtBLtR | BtTRtL | TtBRtL

DetectorConfiguration
  log_level: 0 | 1 | 2 | None
  fan1_pwm: int | None
  fan2_pwm: int | None
  bias_voltage_v: float | None
  bias_enabled: bool | None
  polarity: Negative | Positive | None
  periph_clk_80: bool | None
  chain_mode: NONE | LEADER | FOLLOWER | None
  trigger_in: int | None
  trigger_out: int | None
  trigger_period_s: float | None
  exposure_time_s: float | None
  trigger_delay_s: float | None
  trigger_mode: DetectorTriggerMode | None
  n_triggers: int | None
  tdc: list[str] | None
  global_timestamp_interval_s: float | None
  external_reference_clock: bool | None
  pixel_config: str | ExternalPayloadRef | None
  dacs: list[dict[str, int]] | ExternalPayloadRef | None
```

Detector configuration constraints should mirror the SERVAL manual ranges:
fan PWM values in `[0, 100]`, bias voltage in `[0, 140]`, trigger input and
output in `[0, 6]` to allow the manual's disabled/example value `0`, trigger
period in `[0, 50]` seconds, exposure time in `[0, 10]` seconds, trigger delay
in `[0, 1]` seconds, and global timestamp interval either disabled with `<= 0`
or enabled with `[0.001, 10E6]` seconds. The TDC field should be a two-item
array of SERVAL edge strings such as `["P0", "N0"]`, `["PN0123", "PN0123"]`, or
`["", ""]`.

The TPX3Cam manual recommends a 40 V maximum bias for normal operation. That is
a workflow safety/pre-run check rather than a Pydantic schema limit because the
SERVAL API accepts the wider `[0, 140]` range and existing detector state may
need to record the actual readback value.

Detector-owned state includes:
- hardware identity and firmware/readout identity from `/detector/info`
- chip count, chip IDs, chip names, board IDs, and detector pixel layout
- detector health readings from `/detector/health`
- orientation, original layout, and rotated layout from `/detector/layout`
- applied detector configuration from `/detector/config`
- `PixelConfig` and DAC settings when they are needed for reproducibility

SERVAL `/dashboard` should not live inside `DetectorSnapshot`. It is a SERVAL
backend status snapshot because it combines server, measurement, disk,
notification, and detector summary fields.

#### AcquisitionState ####
AcquisitionState should record the settings and files used by the selected
acquisition program. The `mode` field selects the SERVAL, PyMEPix, or MCP2Hist
Pydantic model.

```python
AcquisitionState
  mode: serval | pymepix | mcp2hist
  ...
```

Depending on the mode, the AcquisitionState may include different fields. For
example, if the mode is `serval`, it may include fields for the SERVAL backend
session, requested and applied acquisition configuration, detector snapshots, and
measurement results:

##### ServalAcquisitionState ####
```python 
serval
  serval_environment: ServalEnvironment
  requested_plan: ServalAcquisitionPlan | None
  requested_detector_config: DetectorConfiguration | None
  requested_destination_configuration: DestinationConfiguration | None
  applied_detector_config: DetectorConfiguration | None
  applied_destination_configuration: DestinationConfiguration | None
  initial_detector_snapshot: DetectorSnapshot | None
  final_detector_snapshot: DetectorSnapshot | None
  calibration: CalibrationState | None
  result: ServalAcquisitionResult | None

ServalEnvironment
  serval_url: str
  version: str | None
  dashboard: ServalDashboard | None
```

CalibrationState should capture the HERMES-side calibration files and the
SERVAL-side `/config/load` requests and results. SERVAL loads TPX3Cam
calibration files with `GET /config/load?format=<format>&file=<filepath>`, not
with `PUT`. The `file` parameter is a string resolved by the SERVAL host, so it
should not be modeled as a local HERMES `Path`.

```python
CalibrationState
  pixel_config_file: FileReference | None
  dacs_file: FileReference | None
  pixel_config_load_request: ServalConfigLoadRequest | None
  dacs_load_request: ServalConfigLoadRequest | None
  pixel_config_load_result: ServalConfigLoadResult | None
  dacs_load_result: ServalConfigLoadResult | None

ServalConfigLoadRequest
  format: pixelconfig | dacs
  serval_file_path: str
  source_file: FileReference | None

ServalConfigLoadResult
  applied_at: datetime | None
  status: str | None
  http_status_code: int | None
  response_text: str | None
  response_summary: JsonObject
```

ServalDashboard should model the SERVAL `/dashboard` response with aliases for
the backend JSON keys and Pythonic field names in HERMES code:

```python
ServalDashboard
  server: ServalDashboardServer
  measurement: ServalDashboardMeasurement | None
  detector: ServalDashboardDetector | None

ServalDashboardServer
  software_version: str | None
  software_timestamp: str | None
  software_commit: str | None
  software_build: str | None
  disk_space: list[ServalDashboardDiskSpace]
  notifications: list[ServalDashboardNotification]

ServalDashboardDiskSpace
  message: str | None
  path: str | None
  free_space: int | None
  write_speed: float | None
  lower_limit: int | None
  disk_limit_reached: bool | None

ServalDashboardMeasurement
  start_date_time_ms: int | None
  time_left_s: float | None
  elapsed_time_s: float | None
  frame_count: int | None
  dropped_frames: int | None
  status: DA_IDLE | DA_PREPARING | DA_RECORDING | DA_STOPPING | None
  pixel_event_rate: int | None
  tdc1_event_rate: int | None
  tdc2_event_rate: int | None

ServalDashboardDetector
  detector_type: str | None
```

DestinationConfiguration should model the JSON response body returned by the
SERVAL `/server/destination` endpoint directly instead of flattening output
channels into a generic HERMES list:

```python
DestinationConfiguration
  raw: list[ServalRawDestination]
  image: list[ServalOutputChannel]
  preview: ServalPreviewDestination | None

ServalRawDestination
  base: str
  file_pattern: str | None
  split_strategy: single_file | frame | SINGLE_FILE | FRAME | None
  queue_size: int | None

ServalOutputChannel
  base: str
  file_pattern: str | None
  format: tiff | pgm | png | jsonimage | jsonhisto | None
  mode: count | tot | toa | tof | count_fb | None
  thresholds: list[int] | None
  integration_size: int | None
  integration_mode: sum | average | last | None
  stop_measurement_on_disk_limit: bool | None
  queue_size: int | None
  corrections: list[multiply] | None
  number_of_bins: int | None
  bin_width: float | None
  offset: int | None

ServalPreviewDestination
  period: float | None
  sampling_mode: skipOnFrame | skipOnPeriod | None
  image_channels: list[ServalOutputChannel]
  histogram_channels: list[ServalOutputChannel]
```

Destination `base` values should be strings, not `Path` values. SERVAL accepts
`file:`, `http:`, and `tcp:` URI forms, and those paths or sockets are resolved
from the machine running SERVAL rather than necessarily from the HERMES process.

SERVAL-owned state includes:
- SERVAL URL, software version, build metadata, disk-space summaries, and notifications
- `/dashboard` snapshots and measurement polling state
- `/server/destination` readback and requested destination configuration
- `/config/load` requests and responses for `.bpc` and `.dacs` files
- measurement lifecycle state from `/measurement/start`, `/measurement/stop`,
  `/measurement`, and `/dashboard`
- file references for raw `.tpx3`, preview, image, and other SERVAL outputs

SERVAL models may preserve backend-native endpoint shapes where that improves
round-tripping and validation. Destination `Base` values should remain URI-like
strings because SERVAL accepts `file:`, `http:`, and `tcp:` destinations that are
not all local HERMES filesystem paths.

NOTE: for `ServalEnvironment` fields and submodels please reference
`20231023_ASIServer_TPX3_manual_V3.3.pdf`.

#### AnalysisState ####
AnalysisState should record the files, configuration, status, and results for the
selected analysis program. Different analysis programs may use different
Pydantic models.

```python
AnalysisState
  mode: hermes_tpx3_spidr | empir
```

For `hermes_tpx3_spidr`, use explicit fields for the raw TPX3 input files, TPX3
Parquet output directory, summary JSON file, unpacker version, clustering
settings, and run result:

##### HermesTpx3SpidrAnalysisState ####
```python
HermesTpx3SpidrAnalysisState
  mode: Literal["hermes_tpx3_spidr"]
  environment: HermesTpx3SpidrEnvironment | None
  config: HermesTpx3SpidrConfig | None
  result: HermesTpx3SpidrResult | None

HermesTpx3SpidrEnvironment
  binary_path: Path | None
  version: str | None

HermesTpx3SpidrConfig
  input_tpx3_files: list[FileReference]
  tpx3_parquet_directory: Path
  cluster_config: ClusterConfig | ExternalPayloadRef | None

HermesTpx3SpidrResult
  status: planned | running | completed | failed | skipped | unknown
  started_at: datetime | None
  completed_at: datetime | None
  exit_code: int | None
  summary_json_file: FileReference | None
  pixel_hit_count: int | None
  tdc_hit_count: int | None
  global_timestamp_count: int | None
  control_packet_count: int | None
  photon_count: int | None
  warnings: list[str]
  errors: list[str]
```

The EMPIR fields remain undecided. When an EMPIR workflow is defined, name its
input files, output directories, configuration files, and result files directly:

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
            ├── payloads.py                 # references to separately saved state-value files
            ├── analysis/                   # analysis environments that are unioned in the top-level record
            │   ├── empir.py                # EMPIR analysis environment, configuration, and related settings
            │   └── hermes_tpx3_spidr.py    # TPX3 SPIDR analysis environment, configuration, and related settings
            ├── acquisition/                # acquisition environments that are unioned in the top-level record
            │   ├── serval.py               # SERVAL acquisition environment, configuration, and related settings
            │   ├── pymepix.py              # PyMEPIX acquisition environment, configuration, and related settings
            │   └── mcp2hist.py             # MCP2Hist acquisition environment, configuration, and related settings
            ├── detector.py                 # TPX3Cam chip, layout, health, and detector config metadata
            ├── environment.py              # Path fields for working, data, raw data, analyzed data, log, preview, config, and tool paths
            └── shared_models.py            # shared models and enums for the state models
``` 
