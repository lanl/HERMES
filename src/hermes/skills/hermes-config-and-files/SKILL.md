---
name: hermes-config-and-files
description: Look up HERMES config fields and what HERMES output files hold, instead of guessing. Use when writing, editing or explaining a HERMES config YAML (measurement_info, environment, acquisition, unpacking, photon or event reconstruction settings, folders, run timing, calibration files), or when reading HERMES Parquet files (pixel_hits, tdc_triggers, photons, events), timestamp_canonical, time-of-flight, TDC offsets, summaries or logs.
---

# HERMES config and output files

## Config fields

To see the fields of one config section, with types, defaults, allowed values
and what each one does, run this from the folder that holds `.claude/`:

    pixi run python .claude/skills/hermes-config-and-files/scripts/show_config_fields.py <section>

The sections are `measurement_info`, `environment`, `acquisition`, `analysis`,
`unpacking`, `photon_reconstruction` and `event_reconstruction`. It reads the
installed HERMES, so it is always up to date. Run only the section you need.

- `analysis` needs `mode: hermes`. Unpacking and photon and event
  reconstruction go under `analysis:`.
- `acquisition` settings go under `acquisition: config:`.
- HERMES sets where SERVAL writes raw files (`environment.raw_data_directory`),
  so there is no field for it.
- Check a finished config with the `validate_config` MCP tool.

## Output files

Open [output_files.md](output_files.md) for:

- the folders and columns of each Parquet file
- the time unit, and how to subtract times for time-of-flight
- the TDC offsets
- the known timing limits
- what the summaries and logs hold

To see the files of one run, use the `describe_output_files` MCP tool.
