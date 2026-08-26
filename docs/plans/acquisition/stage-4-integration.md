# Stage 4 — Integration and robustness

**Status:** Complete — built and unit-tested; evals green (2026-08-26). Live
camera verification of a combined acquire-and-unpack run is still pending.

**Goal:** Turn the working measurement into a dependable run: unpack the raw
files as the camera writes them, hand the run to the existing analysis, and let
long runs bound their own disk use.

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

Built 2026-08-26 on branch `stage-4-integration`.

**What we built.** A record may now configure both acquisition and analysis.
`Workflow.run()` runs the acquisition, then the analysis; it only rejects a
record that configures neither. During a recording, HERMES unpacks each raw
`.tpx3` file as soon as SERVAL finishes writing it, so reconstructed Parquet
(pixels, and photons/events when those stages are configured) grows while the
camera is still running. An external viewer or notebook can watch that Parquet
fill in — HERMES renders nothing itself.

**How the live unpacking works.**

- The measurement poll loop (`serval/measurement.py`) gained an optional
  `on_poll` callback, called once per dashboard poll. The measurement code stays
  analysis-agnostic; it just offers the hook.
- `serval/run.py` builds that callback when the record's analysis is a HERMES
  analysis. Each time new `.tpx3` files appear in the raw directory, it calls the
  existing `run_analysis` once. The existing runner already skips files it has
  already unpacked, so re-invoking it as frames land is naturally incremental.
- The unpacker's `tpx3_files` now defaults to `"auto"` (matching the photon and
  event stages), so a run that does not know its filenames up front picks them up
  by listing the raw directory at run time.
- A failed unpack during a recording is logged and swallowed — it never stops the
  camera. After the measurement ends, `Workflow.run()` makes one final analysis
  pass to catch the last frame and anything a mid-run failure skipped.

**Disk use on long runs.** `Tpx3UnpackingRuntimeOptions.delete_raw_after_unpack`
(off by default) deletes each raw `.tpx3` after this run unpacks it without error.
Files that were skipped or that failed are left on disk. Verified live
(2026-08-26): because the deletion happens *during* the recording, each file is
gone before the run makes its final gather of the raw directory, so the
acquisition result records `frames: 20` but `output_files: []`. The frame count
still says how many frames were taken; the retained Parquet and the per-file
unpacking summaries are the kept record of what was processed. This is the user's
explicit trade-off, and every deletion is logged.

**Why single-threaded.** The interleaved unpacking runs inside the poll loop, not
a second thread. `StateManager` has no locking and replaces the whole record on
every write, so a second thread mutating state would race and lose writes.
Interleaving in the one poll loop sidesteps that.

**Why a set, not a count, of dispatched files.** The callback tracks which raw
files it has already handed to analysis as a set of paths, not a running count,
because `delete_raw_after_unpack` shrinks the directory — a count would miscount
once files start disappearing.

**Robustness and reproducibility.** The per-SERVAL-call timeouts, the bounded
connect retry, and the stop-server-on-failure path were already in place from
stages 0–3. The saved record plus the `config/` copies of `.bpc`/`.dacs` remain
the record of a run; no large detector config is written into the logs.

**Not built (deferred).** SERVAL's own live `Preview` channels and any
HERMES-side rendering — live preview here is progressive Parquet only. Issue #104
(defaulting the run directory from `measurement_info.run`) is a separate follow-up.
