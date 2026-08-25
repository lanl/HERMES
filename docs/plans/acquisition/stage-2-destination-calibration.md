# Stage 2 — Destination and calibration

**Status:** Not started (needs stage 1)

**Goal:** Tell SERVAL where to write raw `.tpx3` data, and load the SoPhy pixel
and DAC calibration files. Still no measurement. After this stage the camera is
fully configured and could record, but we stop short of starting.

## Work

1. **Destination** — new `src/hermes/runner/acquisition/serval/destination.py`:
   - Build a `DestinationConfiguration` with one `Raw` entry writing into the
     run's `raw_data_directory`. The `Base` is a `file:` URI of the resolved local
     directory (valid because SERVAL runs locally). Keep the old prototype's
     working choices: a time-based `FilePattern` and `SplitStrategy: FRAME`
     (`tpx3Spider_lumacam.py:47-55`), unless a reason to change appears.
   - Create the directory, `PUT /server/destination`, then `GET` it back and
     confirm it matches. Record requested and applied destination on the record.

2. **Calibration** — new `src/hermes/runner/acquisition/serval/calibration.py`:
   - Take the user-provided `.bpc` and `.dacs` paths from the plan.
   - Copy each into the run's `config/` directory, compute its SHA-256, and record
     `PixelConfigFile` / `DacsFile` with the relative saved path and hash.
   - Load each into SERVAL: `GET /config/load?format=pixelconfig&file=<abs>` and
     `format=dacs`. Record `PixelConfigLoad` / `DacsLoad` (server path, HTTP
     status, completion status, short response body).
   - HERMES never generates these files; SoPhy does. HERMES validates, saves,
     records, and hands them to SERVAL.

3. **Preflight checks** before writing anything:
   - Detector present and `DA_IDLE`.
   - Health readings within limits; bias within the 40 V manual maximum for normal
     operation even though the API allows more.
   - Output directory usable and enough disk space.

4. **Run function.** Extend `run.py` to run destination + calibration after the
   snapshot, and set the run status to `configured`.

## Test against the real machine

- Configure the destination and load real `.bpc`/`.dacs` files.
- Confirm the read-back destination matches, both loads return success, and the
  run's `config/` folder holds the saved, hashed copies.

## Open items

- Real `.bpc` / `.dacs` paths on this machine (SoPhy output). Supplied through
  `config.yaml`.

## Notes / findings

(update as we build and test)
