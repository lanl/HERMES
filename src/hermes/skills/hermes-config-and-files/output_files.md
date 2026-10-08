# HERMES output files

HERMES writes one Parquet file per signal: pixel hits, TDC triggers, photons,
events and so on, each in its own folder under the run's analysis folder. Every
file has a `timestamp_canonical` column on the same clock. `<raw name>` is the
raw `.tpx3` file name without `.tpx3`. `<chip>` is 0–3. `<part>` is a five-digit
part number, starting at `00000`. The unpacker starts a new part every 1,000,000
rows. A file that would have no rows is not written, so a folder can be missing
or have fewer files than expected; the summaries still count them.

## Time

- Every `timestamp_canonical` counts ticks of 25 ns / 12288, about 2.03 ps
  (2.0345052083333334e-12 s). The photon and event files store this as
  `canonical_tick_seconds` in their file metadata.
- All signals use the same clock, measured from the start of the run, so times
  can be subtracted directly. For example, time-of-flight is an event's time
  minus the time of the TDC trigger just before it.
- Pixel, TDC and global timestamp times are whole numbers (uint64). Photon and
  event times are float64, because the time-walk correction gives fractions of a
  tick.
- TDC1 and TDC2 have independent fixed offsets, set by their cables and
  electronics. Find each one from the data, and never use one channel's offset
  for the other.

## Folders written by unpacking

Every file name starts with `<raw name>` and ends with `_<part>.parquet`.

- `pixel_hits/<raw name>_chip_<chip>_pixels_<part>.parquet`: one row per pixel
  hit, with columns `chunk_index`, `packet_index`, `local_x`, `local_y`,
  `tot_raw` and `timestamp_canonical`.
  - `local_x` and `local_y` are 0–255 on that chip.
  - `tot_raw` is the 10-bit time over threshold, in units of 25 ns; 1023 means
    the pixel was saturated.
  - `chunk_index` and `packet_index` give where the packet was in the raw file.
- `tdc_triggers/<raw name>_tdc<1|2>_<rising|falling>_triggers_<part>.parquet`:
  one row per trigger edge, with columns `chunk_index`, `packet_index` and
  `timestamp_canonical`.
  - The channel and edge are only in the file name.
  - The camera copies each trigger into every chip's data; HERMES keeps one row.
- `global_timestamps/<raw name>_global_timestamps_<part>.parquet`: the global
  timestamps HERMES used to line up the times, with columns `chunk_index`,
  `packet_index` and `timestamp_canonical`.
- `control_packets/`: SPIDR and Timepix3 control packets, with columns
  `chunk_index`, `packet_index`, `source` (0 SPIDR, 1 TPX3), `control_type`,
  and then `packet_id`, `subtype`, `packet_count`, `reserved_high`,
  `reserved_low`, `control_value_raw`, `control_payload_raw` and
  `timestamp_canonical`. Each of those has a `<name>_present` true/false column
  saying whether that packet type has the value.
- `unrecognized_packets/`: packets HERMES did not recognise, with columns
  `chunk_index`, `packet_index`, `raw_word` and `most_significant_byte`.
  Usually there are none, so there is no file.

## Folders written by photon reconstruction

Each pixel file gives at most one photon file, so the names keep the chip and
part. A pixel file with no photons gives no photon file, only its summary.

- `photons/<raw name>_chip_<chip>_photon_<part>.parquet`: one row per photon,
  with columns `photon_id`, `x`, `y`, `timestamp_canonical`, `tot` and
  `quality_flags`.
  - `photon_id` counts from 0 in each file. To identify a photon across files,
    use the file name together with `photon_id`.
  - `x` and `y` are the mean of the photon's pixels, in the sensor frame (see
    below).
  - `timestamp_canonical` is the earliest time of the photon's pixels, after
    time-walk correction when it is on.
  - `tot` is the sum of `tot_raw` over the photon's pixels.
  - `quality_flags` bits: 1 = a pixel was saturated (`tot_raw` 1023); 2 = the
    photon joined two groups of pixels that had started apart.
- `pixel_clusters/<raw name>_chip_<chip>_pixel_clusters_<part>.parquet`: only
  with `save_photon_pixels: true`. One row per pixel of each photon, with
  columns `photon_id`, `pixel_event_id`, `x`, `y`, `tot_raw` and
  `timestamp_canonical`.
  - `pixel_event_id` is the pixel's row number in its `pixel_hits/` file,
    counting from 0.
  - `x` and `y` are chip pixels (0–255).
  - The time is the pixel's own time, without time-walk correction.

Pixels dropped by `min_pixel_tot_raw`, and groups of pixels refused by the size,
`tot_raw`, aspect ratio or filled fraction limits, are not written. The photon
summary counts them.

## Folders written by event reconstruction

Each raw file gives at most one events file, covering all chips. A raw file with
no events gives no events file, only its summary.

- `events/<raw name>_event_candidates.parquet`: one row per event, with columns
  `event_id`, `x`, `y`, `timestamp_canonical`, `photon_count` and
  `quality_flags`.
  - `x` and `y` are the mean of the event's photons.
  - `timestamp_canonical` is the time of its earliest photon.
  - `quality_flags` bits: 1 = only one photon; 2 = the event lasted longer than
    `max_event_duration_ticks`.
  - No event is dropped. `min_photon_count` is only recorded; filter on
    `photon_count` yourself.
- `event_photons/<raw name>_event_photons.parquet`: only with
  `save_event_photons: true`. One row per photon of each event, with columns
  `event_id`, `photon_id`, `x`, `y` and `timestamp_canonical`.

## Sensor frame

Photon and event `x` and `y` use `analysis.detector_layout.kind`:

- `single_chip`: the chip's own 0–255 pixels.
- `quad`: a 516 × 516 frame, with no pixels from 256 to 259 on either axis.
  From chip pixel (x, y): chip 0 → (x + 260, y), chip 1 → (515 − x, 515 − y),
  chip 2 → (255 − x, 515 − y), chip 3 → (x, y).

## File metadata

The photon and pixel cluster files carry the settings that made them in their
Parquet metadata: `clustering_settings`, `correction_model`,
`correction_parameters`, `detector_layout` and `chip_index`. The event files
carry `event_settings` and `detector_layout`. Read it with
`pyarrow.parquet.read_schema(path).metadata`. The unpacking files have none.

## Summaries

There is one JSON file per file processed, under `analysis/logs/`:

- `unpacking/<raw name>_unpacker_summary.json`
  - `unpacking`: packet counts, including `tdc1_rising`, `tdc1_falling`,
    `tdc2_rising` and `tdc2_falling`, plus `errors` and `warnings`.
  - `timestamp_processing.heartbeat_pairs`: `number_of_beats` (global
    timestamps in the file), its first and last timestamp, and
    `previous_file_timestamp_canonical` when an earlier file's timestamp was
    used.
  - `timestamp_processing.time_adjustments`: how many pixel, TDC and control
    times were lined up, and `failed`, how many could not be.
  - `sorting`, `output_parquet` (files written) and `processing_times_seconds`.
- `photon_reconstruction/<raw name>_chip_<chip>_photon_reconstruction_summary_<part>.json`
  - `reconstruction`: `pixels_read`, `clusters_formed`, `rejected_clusters`,
    `rejection_reasons` (counts for each limit), `quality_flag_counts`,
    `total_photons`, `warnings` and `errors`.
  - `clustering` (the settings used), `photon_timing` (the time-walk
    correction used), `parquet_files` and `processing_times_seconds`.
- `event_reconstruction/<raw name>_event_reconstruction_summary.json`
  - `reconstruction`: `photons_read`, `event_count`, `quality_flag_counts`,
    `min_photon_count_below` (events under `min_photon_count`), `warnings` and
    `errors`.
  - `clustering`, `event_timing`, `parquet` and `processing_times_seconds`.

## Logs and the record

These are in `log_directory`. When it is not set, only `HERMES-workflow.jsonl`
is written, to the run folder.

- `analysis.jsonl`, `acquisition.serval.jsonl` and `state.jsonl`: JSON-lines
  logs. Each line has `record.level.name`, `record.message`,
  `record.extra.event_type` and `record.process.id`.
  - These files are added to by every run in the folder. Lines from one run
    share a process id.
  - `state.jsonl` has the full starting config in its `state.initial_record`
    line.
- `HERMES-workflow.jsonl`: written again when each run ends. It holds one
  `stage_completed` line per file per stage, with `stage`, `file`, `status`
  (success, skipped or failed) and `summary`, then `workflow_completed` or
  `workflow_failed`. The stage called `reconstruction` is photon reconstruction.
- `HERMES_record.yaml`, in the run folder: the final config, with each stage's
  results and the acquisition outcome. It is written when the run ends.

Raw `.tpx3` files from a HERMES acquisition are in `raw_data_directory`, one per
frame, named by start time (`yyyy-MM-ddTHHmmss_<number>.tpx3`). The
calibration files used are copied to the run's `config/` folder.

## Known timing limits

Update this list when those issues are fixed.

- Global timestamps far apart, or missing from some files
  ([#136](https://github.com/lanl/HERMES/issues/136)).
  - The pixel clock wraps every 26.84 s. Times more than about 13.4 s after the
    last global timestamp can come out early by whole wraps, with no error.
  - In releases after HERMES 3.3.7, a HERMES acquisition refuses a
    `GlobalTimestampInterval` that is 0 or less, over 13 s, or over half the
    trigger period (in AUTOTRIGSTART_TIMERSTOP and CONTINUOUS). It sets 1 s when
    the interval is unset.
  - When unpacking, a file with no global timestamp of its own uses the last one
    from the file before.
  - Data recorded outside HERMES or with older versions can still have the
    problem. Look in `analysis.jsonl` for the warnings
    `analysis.tpx3_unpacking.earlier_timestamp_too_far` (those times may be off
    by whole wraps) and `analysis.tpx3_unpacking.timestamps_unanchored`.
- No global timestamps at all
  ([#129](https://github.com/lanl/HERMES/issues/129), still open).
  - TDC times and pixel, photon and event times end up on different clocks, and
    can be tens of seconds apart in the same file.
  - The sign of this is `heartbeat_pairs.number_of_beats` 0 and
    `time_adjustments.failed` greater than 0 in the unpacker summary.
  - Do not subtract TDC times from pixel, photon or event times for those files.
