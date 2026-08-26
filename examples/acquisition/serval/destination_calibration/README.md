# Destination + calibration

This example prepares the camera for a measurement without taking one yet. It
launches SERVAL, connects to the camera, tells SERVAL where to write raw `.tpx3`
files, and loads the SoPhy calibration files into SERVAL. It then prints the
raw destination and the load status of each calibration file. Because there is
no `run_timing` in the config, no exposures run and no raw data is written.

## Point at your camera and calibration

Edit `destination_calibration_config.yaml`. Set the jar path and camera address
as in the earlier examples, then set the destination and the two SoPhy
calibration files:

```yaml
environment:
  working_directory: data/examples/acquisition/serval/destination-calibration
  raw_data_directory: raw          # where SERVAL will write raw .tpx3 files

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
```

HERMES copies the two calibration files into a `config/` folder under the run,
records each file's SHA-256, and loads them into SERVAL. Point these at your own
SoPhy output.

## Run it

```bash
pixi run python examples/acquisition/serval/destination_calibration/run_destination_calibration.py
```

Pass another HERMES YAML file as the optional argument to use your own config.

## Output

Prints the raw destination, the copied calibration file paths with their
SHA-256, and the HTTP status of each calibration load. The run writes ignored
development output under the configured working directory:

```text
data/examples/acquisition/serval/destination-calibration/
├── config/                        # the two calibration files, copied in
│   ├── pixelConfig.bpc
│   └── dacsFile.dacs
└── logs/
    ├── serval-server.log
    └── acquisition.serval.jsonl
```

The `raw/` directory is only the configured destination here — no `.tpx3` files
are written because this example takes no measurement. The `measurement/`
example is the one that records data there.
