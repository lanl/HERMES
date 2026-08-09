# evals

Known-good cases that pin down how a HERMES workflow should behave for a known
input, so a code change can be checked against a known-good target instead of
quietly drifting from the intended design.

## Layout

```
evals/
├── cases/
│   ├── 01-unpacking/     unpacking a raw TPX3 file into parquet tables
│   └── 02-two-stage/     unpacking followed by photon reconstruction
├── run_evals.py          runs each case, then compares against its expected/ files
└── compare.py            the sentinel-aware comparison used by run_evals.py
```

Each case:

```
NN-name/
├── case.md          what the case exercises + notes
├── input/
│   ├── config.yaml     the HERMES record the workflow loads
│   └── run_script.py   how the workflow is run
└── expected/
    ├── output_tree.txt         working-dir layout after a correct run
    ├── HERMES-workflow.jsonl    the workflow log, one JSON record per line
    └── *-summary.json           the per-file summary log(s)
```

## Running

From the repo root:

```
pixi run python evals/run_evals.py
```

This runs every case under `cases/`, writing output to the working directory
named in each case's `config.yaml`, then compares that output against the case's
`expected/` files and reports any deviation.

## Placeholders

Any string of the form `<...>` in an expected file marks a value that changes
every run and is not matched literally:

- `<TIMESTAMP>` — a wall-clock time in a log record (the `time` field, or a
  stage's `start`/`stop`).
- `<IGNORE: non-deterministic timing>` — a timing block whose durations vary run
  to run.

`compare.py` treats any `<...>` value in an expected file as a wildcard and skips
it; everything else is a hard expectation.

## Intended vs actual

These cases encode the **intended** design, which the current code may not match
yet. If a run disagrees with a case, either the code drifted (fix the code) or
the design changed on purpose (update the case in the same change). The counts
were taken from real runs of the `tests/data` files, so they are internally
consistent; only the naming and JSON shape reflect the target design.

Raw inputs live in `tests/data/tpx3/` and are read-only — all workflow output
goes to a separate working directory.
