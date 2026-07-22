# Workflows

The full acquisition-to-analysis state flow is:

```text
Create acquisition plan
  -> initialize HERMES record
  -> connect to SERVAL
  -> snapshot detector and SERVAL state
  -> configure acquisition
  -> run acquisition
  -> record raw TPX3 files and image files
  -> unpack raw TPX3 files into Parquet files if needed
  -> record the shared analysis directory and each input's summary JSON file
  -> run analysis workflow
  -> record image, plot, or photon-event output files and their counts
  -> persist final HERMES record
```

Each major step should produce structured Loguru events and update the record
through `hermes.state_service` with enough information to debug or reproduce the
run. Acquisition-only and analysis-only workflows are valid subsets of this full
flow; the `HermesRecord` may have only acquisition state, only analysis state, or
both.

## First Concrete Workflow

The first workflow should be intentionally narrow:

1. Connect to SERVAL.
2. Snapshot detector information, detector configuration, detector layout, and
   detector health.
3. Configure a SERVAL destination that writes raw `.tpx3` data.
4. Start acquisition and wait for completion.
5. Use `hermes.state_service` to save the raw TPX3 file path in the HERMES
   record.
6. Check that all raw TPX3 filename stems are unique before starting analysis.
7. Run the selected TPX3 SPIDR unpacker once for each raw TPX3 file, using the
   same analysis directory for every run.
8. Write each packet category to its shared directory. Start every Parquet
   filename with the raw TPX3 filename stem, followed by its chip and part
   numbers.
9. Write one input-specific unpacker summary JSON file under `analysis/logs/`.
10. Use `hermes.state_service` to save the shared analysis directory, summary
    JSON file, pixel-hit count, TDC-hit count, global-timestamp count,
    control-packet count, warnings, and errors for each raw TPX3 file in the
    same HERMES record.

This workflow is enough to test the HERMES state, file tracking, logging, and
the connection between Python and a selected C++ or Rust backend.
