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

Expected model groups:

- `record.py`: top-level run or experiment record
- `acquisition.py`: acquisition plans, runtime state, and acquisition outcomes
- `analysis.py`: analysis plans, runtime state, and analysis outcomes
- `detector.py`: TPX3Cam, SERVAL, chip, layout, health, and detector config metadata
- `environment.py`: working directories, data directories, log directories,
  preview directories, external tool locations, and tool versions
- `artifacts.py`: raw files, decoded files, images, plots, reports, config
  snapshots, hashes, and provenance
- `enums.py`: shared enums for status, artifact kinds, acquisition modes, and
  analysis modes

The models should use discriminated unions for modality-specific acquisition and
analysis plans once the modalities are known.

The top-level record should explicitly include environment state:

```text
HermesRecord
  environment: RuntimeEnvironment
  acquisition: AcquisitionState
  analysis: AnalysisState
  artifacts: list[Artifact]

RuntimeEnvironment
  paths: HermesPaths
  serval: ServalEnvironment
  empir: ToolEnvironment | None
  hermes: ToolEnvironment
  tpx3_spidr: ToolEnvironment
  python: PythonEnvironment | None
```

This keeps runtime paths, external tool locations, and versions in the durable
state model instead of scattering them across scripts or logs.
