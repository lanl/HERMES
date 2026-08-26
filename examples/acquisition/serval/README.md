# SERVAL server control example (stage 0)

This example launches the SERVAL server from the jar named in the config, waits
until it answers, prints its software version, and shuts it back down. HERMES
talks only to SERVAL over HTTP; SERVAL talks to the camera. No detector reads or
measurements happen yet — that is later stages.

## Set the jar path

SERVAL is a `.jar` that runs on this machine. Edit `config.yaml` and set
`acquisition.config.serval.program_path` to the SERVAL jar on your machine
(and confirm `java` is on your `PATH`):

```yaml
acquisition:
  mode: serval
  config:
    serval:
      url: http://localhost:8080
      program_path: /path/to/serval-3.3.0.jar
      version: "3.3.0"
```

## Run it

```bash
pixi run python examples/acquisition/serval/run_serval_control.py
```

Pass another HERMES YAML file as the optional argument to use your own config:

```bash
pixi run python examples/acquisition/serval/run_serval_control.py /path/to/config.yaml
```

## Output

The run writes ignored development output under the configured working
directory:

```text
data/examples/acquisition/serval/stage0/
└── logs/
    ├── serval-server.log        # SERVAL's own stdout and stderr
    └── acquisition.serval.jsonl # HERMES launch / ready / shutdown events
```

Confirm after a run: the version prints, both log files exist, and the SERVAL
process is gone.

# Connect + detector snapshot example (stage 1)

`run_connect_snapshot.py` goes one step further: it launches SERVAL, waits until
it answers, waits until SERVAL has connected to the camera, then reads the
detector's info, health, layout, and configuration and prints a short summary
before shutting SERVAL down. This is still read-only — no measurement is taken.

## Point SERVAL at your camera

Launching SERVAL alone does not connect the camera; SERVAL must be told the
camera's address. Edit `connect_snapshot_config.yaml` and set both the jar path
and the camera's TCP address:

```yaml
acquisition:
  mode: serval
  config:
    serval:
      url: http://localhost:8080
      program_path: /path/to/serval-3.3.0.jar
      version: "3.3.0"
      tcp_ip: 192.168.100.10   # your camera's address (default SPIDR port 50000)
      tcp_port: 50000
```

On the 10 GB link the camera is typically at `192.168.100.10`; confirm it is
reachable first with `ping 192.168.100.10`. SERVAL answers within a second, but
the camera handshake takes a few seconds more, so the example waits for a
connected detector before reading it.

## Run it

```bash
pixi run python examples/acquisition/serval/run_connect_snapshot.py
```

Pass another HERMES YAML file as the optional argument to use your own config.

## Output

Prints the software version, then a snapshot: interface, chip board and chip
names, temperatures, bias voltage, humidity, and detector size. The same
`serval-server.log` and `acquisition.serval.jsonl` are written under the
configured working directory, now also recording the detector-connected event
and each `/detector/*` read.
