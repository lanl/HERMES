# Stage 4 — Integration and robustness

**Status:** Not started (needs stage 3)

**Goal:** Turn the working measurement into a dependable run: hand the raw files
to the existing unpacker, harden the failure paths, and make the run reproducible.

## Work

1. **Acquisition to analysis handoff.** `docs/architecture/workflows.md` describes
   the full flow: acquire, then unpack the raw `.tpx3` files, then run analysis.
   Today `Workflow.run()` rejects a record that configures both acquisition and
   analysis. Decide the sequencing (likely: acquisition runs, then the same run's
   raw files feed unpacking) and update `Workflow.run()` accordingly. Confirm raw
   filenames are unique before unpacking, as the unpacker workflow requires.

2. **Robustness.**
   - Sensible timeouts on every SERVAL call.
   - Bounded retries on transient connect errors, not an endless loop (the old
     prototype retried config forever, `tpx3Spider_lumacam.py:23-65`).
   - On any failure mid-run: stop the measurement, shut down the server, and leave
     the record in a clear `failed` state with the reason.

3. **Reproducibility.** The saved record plus the `config/` copies of `.bpc` and
   `.dacs` should be enough to explain and repeat the run. Keep large detector
   configuration out of the logs; reference the saved file and hash instead.

## Optional / later

- Live preview output (`Preview` channels) only if monitoring during a run is
  needed. Off by default.
- A manual hardware-test checklist. Note that deterministic evals under `evals/`
  cannot cover acquisition because it needs the camera, so acquisition testing
  stays a manual, hardware-in-the-loop step for now.

## Notes / findings

(update as we build and test)
