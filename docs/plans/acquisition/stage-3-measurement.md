# Stage 3 — Take a short measurement

**Status:** Not started (needs stage 2)

**Goal:** Apply the run's detector configuration, start a short measurement,
watch it to completion, and record the raw `.tpx3` files it produced. This is the
first stage that records real data.

## Work

1. **Client** — extend `serval/client.py`:
   - `put_detector_config(config)` — `PUT /detector/config`.
   - `measurement_start()` — `GET /measurement/start`.
   - `measurement_stop()` — `GET /measurement/stop`.

2. **Apply detector config.** Build the effective config from the loaded
   `config`: start from `config.detector_config` (or the JSON at
   `config.detector_config_file`, which wins when both are set), then apply the
   `config.run_timing` overrides (trigger mode, exposure time, trigger period,
   trigger count → `nTriggers`). `PUT /detector/config` with that. Read
   `/detector/config` back and record it as `final_detector_snapshot.configuration`;
   warn on any difference from what was sent.

3. **Run and monitor.**
   - `GET /measurement/start`.
   - Poll `/dashboard` until `Measurement.Status == DA_IDLE`, or a timeout, or an
     explicit stop. Track frame count, dropped frames, elapsed time, time left, and
     event rates in the acquisition log (not one line per poll — summarize).
   - On timeout or failure, `GET /measurement/stop` and record the stop reason.

4. **Record output.**
   - Read a final `/dashboard` and `/detector/health`; record the final snapshot.
   - Find the raw `.tpx3` files in `raw_data_directory` and record their paths,
     sizes, and timestamps.
   - Fill `ServalAcquisitionResult` (started/completed time, stop reason, frames,
     dropped frames, output files). Record the final `/dashboard` in the state's
     `dashboard` field. Set the run `status` (top level of the state) to
     `completed` or `failed`.

## Safety for the first real run

- Start with a short, low-intensity plan (short exposure, few triggers) so the
  first recorded measurement is quick and low-risk.
- Bias stays within the 40 V manual maximum.
- Always stop the measurement and shut down cleanly if any step fails.

## Test against the real machine

- Take a short measurement.
- Confirm one or more `.tpx3` files land in `raw_data_directory`, the record shows
  frame counts and the output files, and the run status is `completed`.

## Notes / findings

(update as we build and test)
