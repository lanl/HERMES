# Connect + detector snapshot

This example goes one step further than `server_control/`: it launches SERVAL,
waits until it answers, waits until SERVAL has connected to the camera, then
reads the detector's info, health, layout, and configuration and prints a short
summary before shutting SERVAL down. This is still read-only — no measurement is
taken.

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
pixi run python examples/acquisition/serval/connect_snapshot/run_connect_snapshot.py
```

Pass another HERMES YAML file as the optional argument to use your own config.

## Output

Prints the software version, then a snapshot: interface, chip board and chip
names, temperatures, bias voltage, humidity, and detector size. The same
`serval-server.log` and `acquisition.serval.jsonl` are written under the
configured working directory, now also recording the detector-connected event
and each `/detector/*` read.
