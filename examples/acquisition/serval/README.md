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
