# Stage 3 — Take a short measurement

**Status:** Complete. Built, unit-tested, and verified live on the real camera
2026-08-26: five 0.1 s exposures (AUTOTRIGSTART_TIMERSTOP) recorded 5 frames,
0 dropped, 5 valid `.tpx3` files (TPX3 magic confirmed), run status `completed`.

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

- Config-driven, like stage 2: the measurement runs when `config.run_timing` is
  present, so the same acquisition function serves the read-only connect, the
  configure-only run, and the measurement run. No mode flags or extra knobs.
  `run.py` records `status = running` before the measurement, then `completed`
  when the camera finished on its own with no errors, else `failed`.
- Effective detector config (`build_effective_detector_config`) starts from the
  JSON at `detector_config_file` when set (it wins over the inline
  `detector_config`), otherwise the inline config, otherwise an empty
  `DetectorConfiguration`. The `run_timing` values are layered on top with
  `model_copy(update=...)`; `trigger_count` maps to the detector's `n_triggers`.
  The applied config is read back and any drift is recorded as a warning.
- Monitoring is one poll loop over `/dashboard` with a `seen_active` flag. A run
  is only "completed" once the camera has been observed busy (an active status
  or a non-zero frame count) and then returns to `DA_IDLE`; this avoids treating
  the brief idle just after `start` as a finished run, and still catches an
  instant-finish run (frames already counted). The loop tolerates transient
  dashboard read failures by retrying until the deadline.
- Three stop reasons: `completed`, `stopped_after_timeout` (wait limit reached,
  HERMES stops the measurement), and `no_activity` (never left idle and made no
  frames within the start window). The no-activity check is decided before the
  timeout check, so a short run that never starts is reported as `no_activity`
  rather than `stopped_after_timeout` even when both limits coincide.
- The wait limit is derived from the timing (`trigger_count × (trigger_period_s
  or exposure_time_s)`, else `exposure_time_s`), doubled with a small margin and
  capped at 300 s; a run whose length cannot be computed waits the 300 s
  default. This is an internal safety limit, not a config knob.
- Raw files are gathered from `raw_data_directory` by globbing `*.tpx3`; each is
  recorded as a `FileReference` with its resolved path, size, and modification
  time. `FileReference` gained an optional `size_bytes` field for this.
- Tests use a fake clock (sleep advances a counter, monotonic reads it) so the
  timeout and no-activity paths are exercised without waiting real seconds. The
  measurement test file is `test_serval_measurement.py` (a unique basename is
  required because these test dirs have no `__init__.py`).
