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
  -> record overall unpacking progress in the HERMES state
  -> run analysis workflow
  -> record image, plot, or photon-event output files and their counts
  -> persist final HERMES record
```

Each major step should produce structured Loguru events and update the record
through `hermes.state_service` with enough information to debug or reproduce the
run. Acquisition-only and analysis-only workflows are valid subsets of this full
flow; the `HermesRecord` may have only acquisition state, only analysis state, or
both.

## Workflow Class

`hermes.workflows.workflow.Workflow` is the user-facing entry point for running
these steps. It is constructed from one `HermesRecord` and owns the
`StateManager` for that record. Callers load the initial record before creating
the workflow and save `workflow.record` after the requested work finishes.

The current concrete operation is:

```python
from hermes.workflows.workflow import Workflow

workflow = Workflow(initial_record)
unpacked_raw_files = workflow.run_analysis(overwrite=False)
final_record = workflow.record
```

`run_analysis()` delegates to the analysis implementation. The workflow keeps
the trusted-workflow state-service setting internal, so user code does not
construct or configure `StateManager`. The lower-level
`run_hermes_analysis(state_manager, ...)` function remains available inside the
analysis module for focused tests and code that intentionally manages its own
state service.

`Workflow.run()` reads the record and runs the work it configures:

- Analysis only: it runs analysis, saves the final record to
  `HERMES_record.yaml` in the run directory, and writes the run timeline to
  `HERMES-workflow.jsonl` in the log directory.
- Acquisition only: it calls `run_acquisition()`, which raises
  `NotImplementedError` because acquisition execution does not exist yet.
- Both acquisition and analysis: it raises `ValueError`, because running the
  two together is not supported yet.
- Neither: it raises `ValueError`.

`Workflow.run_acquisition()` reserves the acquisition entry point and raises
`NotImplementedError` until a hardware-facing acquisition runner has its own
approved plan.

One workflow owns the record for acquisition-only, analysis-only, and combined
acquisition-to-analysis runs.

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
7. Validate the unpacker executable, every raw TPX3 file, every existing
   summary, and every existing Parquet file before launching any unpacker.
8. Calculate the worker count from the saved `resource_limit_percent`, physical
   CPU count, available memory, and the largest pending raw file size.
9. Run independent unpacker processes concurrently using `ThreadPoolExecutor`
   with the calculated worker count. Each worker waits for one C++ subprocess.
10. Write each packet category to its shared directory. Start every Parquet
    filename with the raw TPX3 filename stem, followed by its chip and part
    numbers.
11. Write one input-specific unpacker summary JSON file under `analysis/logs/`.
12. Keep the summary JSON file as the sole detailed result for its raw TPX3
    file. Save only the shared analysis directory, raw TPX3 list, unpacker
    program, resource limit percentage, and per-file unpacking status in the
    HERMES record.
13. Return completed files in the original input order, regardless of completion
    order.
14. If one unpacker fails, record that file `failed` and keep unpacking the
    remaining files, retaining valid output from successful processes. Only a
    whole-stage problem (a missing or unbuilt executable, a missing raw file, or
    an invalid or partial prior summary) stops the run.
15. When repeating the workflow, skip an input only when its summary is valid
    and every listed Parquet file exists. Run an input only when neither its
    summary nor matching Parquet files exist. Stop on an invalid summary or
    partial output files.

This workflow is enough to test the HERMES state, file tracking, logging, and
the connection between Python and a selected C++ or Rust backend.
