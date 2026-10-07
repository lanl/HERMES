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

- Analysis only: it runs analysis.
- Acquisition only: it calls `run_acquisition()`, which runs the SERVAL
  acquisition (see [acquisition.md](acquisition.md)).
- Both acquisition and analysis: it runs the acquisition, which unpacks each
  raw file once SERVAL has finished writing it, and then runs one final
  analysis pass for anything the last frames left. A file unpacked or
  reconstructed during recording keeps its `completed` result in that final
  pass and is not reported as `skipped`. When the analysis during recording
  fails, HERMES logs the error with its traceback once, adds a warning to
  `acquisition.result.warnings`, and runs no more analysis until the recording
  ends; the final pass then handles every file. When the acquisition ended
  `failed` (for example after a timeout, no camera activity, a full disk, or no
  complete frames), the final pass still runs over the raw files it wrote, and
  HERMES logs a `workflow.analysis_after_failed_acquisition` warning, with the
  stop reason and errors, saying those files may be incomplete. When Ctrl-C or
  an error ends the acquisition, analysis does not run.
- Neither: it raises `ValueError`.

In every case `run()` saves the final record to `HERMES_record.yaml` in the run
directory and writes the run timeline to `HERMES-workflow.jsonl` in the log
directory (the run directory when no log directory is set). Both are written
in a `finally` block, so they are saved also when Ctrl-C or an error ends the
run early; the error is then raised again.

`HERMES-workflow.jsonl` holds one JSON object per line, in this order:

1. `HERMES_record_initialized`, with the path of the saved record.
2. `workflow_initialized`, with the `stages` the record configures, in order:
   `acquisition`, `unpacking`, `reconstruction`, `event_reconstruction`.
3. When an acquisition is configured, one `stage_completed` line with
   `"stage": "acquisition"`. It holds the acquisition `status` (`success` for
   `completed`, otherwise the saved status, such as `failed`, `stopped`, or
   `configured`; `planned` means the acquisition ended before it saved a
   status), `stop_reason`, `frames`, `dropped_frames`, and `errors` from the
   measurement result, and the measurement's `start` and `stop` times. Runs
   that take no measurement leave those fields empty (`null`, or `[]` for
   `errors`).
4. One `stage_completed` line per finished analysis file, in stage then file
   order, with its `status` (`success`, `skipped`, or `failed`) and the path to
   its summary.
5. One closing line:
   - `workflow_stopped` when Ctrl-C ended the run;
   - `workflow_failed` when an error ended the run, or when any stage line
     above has status `failed`. It lists those stages in `failed_stages` and,
     when an error ended the run, holds it in `error`;
   - `workflow_completed` otherwise.

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
