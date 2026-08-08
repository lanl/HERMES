# EMPIR analysis example

This example runs the three EMPIR programs in order, from a raw TPX3 file to a
TIFF image:

```text
raw TPX3 file
  -> photon file    (.empirphot, from empir_pixel2photon_tpx3spidr)
  -> event file     (.empirevent, from empir_photon2event)
  -> TIFF image     (.tiff, from empir_event2image)
```

The starting raw file (`tests/data/tpx3/Tantalum_IronPowder.tpx3`) is copied
into the working directory's `rawTpx3/` sub-directory, then the three programs
run in sequence. The completed HERMES state is saved separately once all three
stages finish.

Each program is timed with a monotonic clock. The measured duration for each
stage is written to the analysis log (see [Timing](#timing) below). This is the
value used to compare EMPIR with the HERMES pipeline: EMPIR pixel-to-photon time
is comparable to combined HERMES unpacking plus photon reconstruction, not to
unpacking alone. EMPIR photon-to-event has no current HERMES equivalent, and
event-to-image time should be reported on its own.

## Requirements

HERMES does not ship or install EMPIR. You supply your own licensed EMPIR
installation and put its `bin` directory on `PATH` so the three programs resolve
by name:

```bash
export PATH="/path/to/EMPIR/bin:$PATH"
```

The supplied EMPIR binaries target Ubuntu 22.04 and require `libtiff`. Confirm
the programs run before using this example:

```bash
empir_pixel2photon_tpx3spidr --help
empir_photon2event --help
empir_event2image --help
```

## Run the example

Run the checked-in `empir.yaml`:

```bash
pixi run python examples/analysis/empir/run_empir.py
```

To use another configuration, supply its path:

```bash
pixi run python examples/analysis/empir/run_empir.py \
  /path/to/empir.yaml
```

## Configure the stages

- `analysis.pixel_to_photon` selects `empir_pixel2photon_tpx3spidr`, its
  clustering settings (`-s` spatial distance in pixels, `-t` time distance in
  seconds, `-k` minimum pixel count), and whether to read TDC1 (`include_tdc1`
  adds `-T`).
- `analysis.photon_to_event` selects `empir_photon2event` and its settings
  (`-s`, `-t`, and `-D` maximum cluster duration in seconds).
- `analysis.event_to_image` selects `empir_event2image`, the image width
  (`-x`), and optional filters and binning. Setting `time_bin_width_seconds`
  requires `time_bin_count` (both together, producing a TIFF stack).
- `save_photon_files` and `save_event_files` control whether each stage's input
  is kept after the downstream stage succeeds. Both are `true` here so you can
  inspect the intermediates. Inputs are always kept if a downstream stage fails.
- The stages chain by path: each `photon_to_event` input must match a
  `pixel_to_photon` requested photon file, and each `event_to_image` input must
  match a `photon_to_event` requested event file.

## Timing

The example sets `environment.log_dir: logs`, which resolves under the working
directory, so the analysis log is written to:

```text
data/examples/analysis/empir/logs/analysis.jsonl
```

Without `log_dir` set, no `analysis.jsonl` is written and timing goes only to
the console. Each stage emits a `...completed` event carrying `elapsed_seconds`.
Read the per-stage durations with `jq`:

```bash
jq 'select(.record.extra.event_type | endswith(".completed"))
    | {step: .record.extra.step, elapsed_seconds: .record.extra.elapsed_seconds}' \
  data/examples/analysis/empir/logs/analysis.jsonl
```

## Output

The checked-in configuration writes ignored development output under:

```text
data/examples/analysis/empir/
├── hermes-record_final.yaml
├── rawTpx3/
│   └── Tantalum_IronPowder.tpx3
├── results/
│   ├── photons/
│   │   └── Tantalum_IronPowder.empirphot
│   ├── events/
│   │   └── Tantalum_IronPowder.empirevent
│   └── final/
│       └── Tantalum_IronPowder.tiff
└── logs/
    └── analysis.jsonl
```

The completed `hermes-record_final.yaml` records the exact command arguments and
the timed result for each stage. Re-running the example fails fast if an output
already exists, so remove the `results/` directory before a fresh run.
