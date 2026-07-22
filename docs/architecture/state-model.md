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
point in the measurement, assuming the saved detector-configuration files named
in the state are still available.

HERMES saves the SoPhy `.bpc` pixel-configuration file and `.dacs` DAC-settings
file under the run's `config/` directory. The state names each file directly
with `PixelConfigFile` or `DacsFile`. Parsed JSON returned by SERVAL endpoints is
stored in its typed detector or SERVAL model; HERMES does not create a second
generic file for a server response body.

Operational logs are not the source of truth for reconstructing state. They may
reference state paths and file hashes, but they should not duplicate complete
detector configurations or server response bodies.

The final `HermesRecord` should be saved to disk as a YAML file for later
reference. YAML is the primary persisted record format because it is readable and
practical for user-authored run inputs. JSON may still be supported as an
optional export format for tools that need strict machine-readable records, but
the Pydantic `HermesRecord` schema remains the authoritative field definition.

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
should use a clearly named `Path` field, such as `analysis_directory`.

```python
FileReference
  path: Path
  media_type: str | None
  sha256: str | None
  size_bytes: int | None
  created_at: datetime | None
  description: str | None
```

#### Saved calibration files ####
The two SERVAL calibration files have separate models because their formats and
uses are different. `path` names the copy saved under the run directory and must
be relative so the run directory can be moved. `source_path` records where the
user supplied the file from. `file_hash` is the 64-character hexadecimal SHA-256
hash of the saved file. The hash is required so HERMES can verify that the saved
file has not changed. File size, media type, creation time, and a generic
description are not needed in these models.

```python
PixelConfigFile
  path: Path
  source_path: Path | None
  file_hash: str

DacsFile
  path: Path
  source_path: Path | None
  file_hash: str
```

`PixelConfigFile.path` must end with `.bpc`. `DacsFile.path` must end with
`.dacs`. The models validate names and metadata but do not copy files; the
SERVAL acquisition workflow performs the copy before recording the paths.

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
  pixel_config: str | None
  dacs: list[dict[str, int]] | None
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
SERVAL-side `/config/load` results. SERVAL loads TPX3Cam
calibration files with `GET /config/load?format=<format>&file=<filepath>`, not
with `PUT`. The `file` parameter is a string resolved by the SERVAL host, so it
should not be modeled as a local HERMES `Path`.

```python
CalibrationState
  pixel_config_file: PixelConfigFile | None
  dacs_file: DacsFile | None
  pixel_config_load: PixelConfigLoad | None
  dacs_load: DacsLoad | None

PixelConfigLoad
  server_file_path: str
  applied_at: datetime | None
  status: str | None
  http_status_code: int | None
  server_response_body: str | None

DacsLoad
  server_file_path: str
  applied_at: datetime | None
  status: str | None
  http_status_code: int | None
  server_response_body: str | None
```

The class identifies whether the request used SERVAL's `pixelconfig` or `dacs`
format, so the state does not repeat a separate `format` field. The optional
`server_response_body` records the short text returned by `/config/load` when it
is useful for diagnosing a load failure. Large or unrelated response bodies
should remain in bounded acquisition logs rather than the HERMES record.

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
  mode: hermes | empir
```

For `hermes`, record one unpacking run for each raw TPX3 file. Photon and event
reconstruction remain optional empty models until their settings and output
columns are defined.

##### HermesTpx3AnalysisState ####
```python
HermesTpx3AnalysisState
  mode: Literal["hermes"]
  unpacking_runs: list[Tpx3SpidrUnpackingRun]
  photon_reconstruction: HermesPhotonReconstructionState | None
  event_reconstruction: HermesEventReconstructionState | None

Tpx3SpidrUnpackingRun
  program: Tpx3SpidrUnpackerProgram
  settings: Tpx3SpidrUnpackerSettings
  result: Tpx3SpidrUnpackerResult

Tpx3SpidrUnpackerProgram
  name: str
  executable_path: Path
  version: str | None

Tpx3SpidrUnpackerSettings
  input_tpx3_file: FileReference
  analysis_directory: Path
  command_args: list[str]

Tpx3SpidrUnpackerResult
  status: planned | running | completed | failed | skipped | unknown
  started_at: datetime | None
  completed_at: datetime | None
  exit_code: int | None
  summary_json_file: FileReference | None
  pixel_hit_count: int | None
  tdc_hit_count: int | None
  global_timestamp_count: int | None
  spidr_control_count: int | None
  tpx3_control_count: int | None
  unknown_packet_count: int | None
  warnings: list[str]
  errors: list[str]

HermesPhotonReconstructionState

HermesEventReconstructionState
```

Every `Tpx3SpidrUnpackingRun` uses the same `analysis_directory`. The separate
run entries keep each raw TPX3 file's status, timestamps, counts, warnings,
errors, and summary JSON file together. The analysis runner must reject a
HERMES analysis configuration when its unpacking runs specify different
analysis directories or duplicate raw TPX3 filename stems.

The shared directory contains `pixelHits/`, `tdcTriggers/`,
`globalTimestamps/`, `controlPackets/`, `unknownPackets/`, and `logs/`.
Parquet filenames begin with the corresponding raw TPX3 filename stem. The
`summary_json_file` is the input-specific
`logs/<raw-file-stem>-unpacker-summary.json` file.

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
