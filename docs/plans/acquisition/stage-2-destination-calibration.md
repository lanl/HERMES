# Stage 2 — Destination and calibration

**Status:** Implemented and verified against the live camera (2026-08-26).
Unit tests and evals green. `destination.py`, `calibration.py`, the client
`put_destination`/`load_pixel_config`/`load_dacs` methods, the preflight checks,
the run wiring, and the `run_destination_calibration.py` example are in place.
Live run: detector connected (Tpx3), destination PUT + read-back confirmed, both
calibration files copied/hashed and loaded (HTTP 200), status `configured`,
SERVAL stopped cleanly.

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

- **Config-driven, not a mode flag.** Destination and calibration each run only
  when the config supplies them (`raw_data_directory`, `calibration_files`). With
  neither, `run.py` keeps the stage-1 read-only behaviour (reads the existing
  destination, tolerates the 409 "not set") and ends `completed`. With either
  present it configures and ends `configured`. No new CLI knob.
- **Destination base is a `file:` URI.** `configure_raw_destination` uses
  `raw_data_directory.as_uri()` for the `Base`, valid because SERVAL runs locally.
  Read-back is compared with `_base_points_to`, which strips `file://`/`file:`,
  unquotes, and resolves both sides — so an equivalent-but-differently-spelled URI
  from the server still confirms. On mismatch we still record what the server
  reported, so the record shows the truth rather than what we asked for.
- **File pattern / split carried from the prototype.** `FilePattern`
  `%yyyy-MM-dd'T'HHmmss_` and `SplitStrategy: FRAME`
  (`tpx3Spider_lumacam.py:47-55`), unchanged pending a reason to change.
- **Calibration is copy-then-load.** Each `.bpc`/`.dacs` is copied into the run's
  `config/`, hashed (SHA-256), and recorded with its path relative to the run
  directory. SERVAL then loads it from the copy's absolute path via
  `GET /config/load`. HERMES never generates these files; SoPhy does.
- **Preflight before any write.** Raises if no detector is present or the
  measurement status is not idle (`None`/`DA_IDLE`); warns (does not block) when
  bias exceeds the 40 V manual maximum or free disk is low.
