# evals

Known-good cases that pin down how a HERMES workflow should behave for a known
input, so a code change can be checked against a known-good target instead of
quietly drifting from the intended design.

## Layout

```
evals/
├── cases/
│   ├── 01-unpacking/     unpacking a raw TPX3 file into parquet tables
│   ├── 02-two-stage/     unpacking followed by photon reconstruction
│   ├── 03-event-quad/    unpacking, photon, and event reconstruction (quad)
│   ├── 04-many-files/    many raw files, moved out to sibling list files
│   ├── 05-earlier-global-timestamp/  a raw file with no global timestamp
│   ├── 06-photon-average/    default timing, including fractional and large means
│   ├── 07-photon-brightest/  largest-ToT hit time with correction off
│   └── 08-photon-calibrated/ shared linear correction followed by average timing
├── photon_timing_inputs.py  shared synthetic pixel inputs for cases 06–08
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
    ├── *-summary.json           the per-file summary log(s), for the first file
    ├── <stem>_unpacker_summary.json  the unpacker summary of one named file
    └── parquet_rows.json       optional exact rows from named Parquet files
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

## Numerical Parquet checks

An optional `expected/parquet_rows.json` maps each file's path, relative to the
case's run directory, to its expected rows. For example:

```json
{
  "analysis/photons/sample_chip_0_photon_00000.parquet": [
    {"photon_id": 0, "x": 0.5, "y": 0.0, "timestamp_canonical": 105.5, "tot": 40, "quality_flags": 0}
  ]
}
```

Rows, row order, columns, and values are compared exactly, without rounding or
a numerical tolerance. Missing or unreadable files fail the case. Cases 06–08
use hand-calculated expectations that are exactly representable as float64,
including timestamps above 2^53. This catches even a single float64 step of
unwanted rounding. The same cases check the original pixel rows and the
pixel-to-photon assignments, so timing changes cannot silently change the
source data or clustering. Their `case.md` files explain each expected time.

The optional `input/prepare.py` creates synthetic Parquet files in the ignored
`data/` directory before the workflow runs. No generated detector data is
committed. Run `pixi run build-cpp-photon-clusterer` before using the new cases
with a local build. A config names the executable it uses; for an installed
program on `PATH`, refresh the installation after changing C++ code.

## Intended vs actual

These cases encode the **intended** design, which the current code may not match
yet. If a run disagrees with a case, either the code drifted (fix the code) or
the design changed on purpose (update the case in the same change). The counts
were taken from real runs of the `tests/data` files, so they are internally
consistent; only the naming and JSON shape reflect the target design.

Raw inputs live in `tests/data/tpx3/` and are read-only — all workflow output
goes to a separate working directory.
