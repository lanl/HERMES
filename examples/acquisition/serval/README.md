# SERVAL acquisition examples

These examples drive a TPX3Cam through the ASI SERVAL server. HERMES launches
and talks to SERVAL over HTTP; SERVAL talks to the camera. Each example builds on
the one before it, from just starting the server up to taking a real measurement.

Each example lives in its own folder with a runnable script, a YAML config, and
its own README:

| Example | What it does |
| --- | --- |
| [`server_control/`](server_control/) | Launch SERVAL, wait until it answers, print its version, and shut it down. No camera reads yet. |
| [`connect_snapshot/`](connect_snapshot/) | Also wait for the camera to connect, then read and print the detector's info, health, and layout. Still read-only. |
| [`destination_calibration/`](destination_calibration/) | Choose where SERVAL writes raw `.tpx3` files, then load the SoPhy calibration files into SERVAL. |
| [`measurement/`](measurement/) | Take a real measurement: run short exposures and write raw `.tpx3` files to disk. |

Start with `server_control/` and work down the list.

## Before you run any example

Every config points at a SERVAL `.jar` on your machine, and every example past
`server_control/` also needs the camera's address. Set these in each folder's
YAML config:

```yaml
acquisition:
  mode: serval
  config:
    serval:
      url: http://localhost:8080
      program_path: /path/to/serval-3.3.0.jar   # the SERVAL .jar on your machine
      version: "3.3.0"
      tcp_ip: 192.168.100.10                     # your camera's address
      tcp_port: 50000                            # default SPIDR port
```

Confirm `java` is on your `PATH`, and that the camera answers `ping 192.168.100.10`
before running the examples that read or measure. SERVAL answers within a second,
but the camera handshake takes a few seconds more.

## Output

Every example writes ignored development output under the `working_directory` set
in its config, always including a `logs/` folder with SERVAL's own
`serval-server.log` and HERMES's `acquisition.serval.jsonl` event log. See each
folder's README for the exact output it produces.
