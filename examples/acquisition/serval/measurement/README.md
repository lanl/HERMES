# Measurement

This example takes a real measurement. It launches SERVAL, connects to the
camera, sets the raw destination, loads the SoPhy calibration files, then runs a
short series of exposures and writes raw `.tpx3` files to disk. It prints when
the measurement started and finished, how many frames it took, and the raw files
it produced.

What turns this run into a measurement is the `run_timing` section — everything
above it matches the `destination_calibration/` example.

## Point at your camera and calibration

Edit `measurement_config.yaml`. Set the jar path, camera address, and calibration
files as in the earlier examples, then set the timing of the measurement:

```yaml
environment:
  working_directory: data/examples/acquisition/serval/measurement
  raw_data_directory: raw

acquisition:
  mode: serval
  config:
    serval:
      url: http://localhost:8080
      program_path: /path/to/serval-3.3.0.jar
      version: "3.3.0"
      tcp_ip: 192.168.100.10
      tcp_port: 50000
    calibration_files:
      pixel_config_file: /path/to/settings.bpc
      dacs_file: /path/to/settings.bpc.dacs
    # The presence of run_timing is what makes this a measurement.
    run_timing:
      trigger_mode: AUTOTRIGSTART_TIMERSTOP
      exposure_time_s: 0.1
      trigger_period_s: 0.2
      trigger_count: 5
```

The checked-in timing is deliberately short and low-intensity for a first real
run: five 0.1 s exposures, auto-started and timer-stopped. Adjust the exposure
time, period, and count for your measurement.

## Run it

```bash
pixi run python examples/acquisition/serval/measurement/run_measurement.py
```

Pass another HERMES YAML file as the optional argument to use your own config.

## Output

Prints the measurement's start and finish times, stop reason, frame count, and
the raw files it wrote with their sizes. The run writes ignored development
output under the configured working directory:

```text
data/examples/acquisition/serval/measurement/
├── config/                        # the two calibration files, copied in
│   ├── pixelConfig.bpc
│   └── dacsFile.dacs
├── raw/                           # the raw .tpx3 files SERVAL wrote
│   └── ...tpx3
└── logs/
    ├── serval-server.log
    └── acquisition.serval.jsonl
```

Confirm after a run: the acquisition status is `completed`, the frame count
matches `trigger_count`, and one or more `.tpx3` files are present under `raw/`.
