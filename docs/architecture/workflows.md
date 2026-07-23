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
8. Apply the HERMES `running` status. If the trusted-workflow state change is
   not allowed, do not launch an unpacker.
9. Calculate the worker count from the saved `resource_limit_percent`, physical
   CPU count, available memory, and the largest pending raw file size.
10. Run independent unpacker processes concurrently using `ThreadPoolExecutor`
    with the calculated worker count. Each worker waits for one C++ subprocess.
11. Write each packet category to its shared directory. Start every Parquet
    filename with the raw TPX3 filename stem, followed by its chip and part
    numbers.
12. Write one input-specific unpacker summary JSON file under `analysis/logs/`.
13. Keep the summary JSON file as the sole detailed result for its raw TPX3
    file. Save only the shared analysis directory, raw TPX3 list, unpacker
    program, resource limit percentage, and overall unpacking status and times
    in the HERMES record.
14. Return completed files in the original input order, regardless of completion
    order.
15. If one unpacker fails, cancel work that has not started, allow already
    running processes to finish, mark overall unpacking `failed`, and keep valid
    output from successful processes.
16. When repeating the workflow, skip an input only when its summary is valid
    and every listed Parquet file exists. Run an input only when neither its
    summary nor matching Parquet files exist. Stop on an invalid summary or
    partial output files.

This workflow is enough to test the HERMES state, file tracking, logging, and
the connection between Python and a selected C++ or Rust backend.
