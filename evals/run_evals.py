"""Run every eval case and compare its output against the case's expected/ files.

Run from the repo root:

    pixi run python evals/run_evals.py

Each case's config.yaml names its own working directory, so cases do not clobber
each other. Exit status is non-zero if any case deviates from its expected/ files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from hermes.state_service.state_io import load_hermes_record_from_yaml
from hermes.workflows.workflow import Workflow

import compare

_CASES_DIR = Path(__file__).parent / "cases"


def run_case(case_dir: Path) -> list[str]:
    config_file = case_dir / "input" / "config.yaml"
    config = yaml.safe_load(config_file.read_text())
    working_dir = Path(config["environment"]["working_dir"])

    record = load_hermes_record_from_yaml(str(config_file))
    Workflow(record).run()

    return compare.compare_case(case_dir / "expected", working_dir)


def main() -> int:
    failures = 0
    for case_dir in sorted(p for p in _CASES_DIR.iterdir() if p.is_dir()):
        try:
            problems = run_case(case_dir)
        except Exception as error:  # a broken case should not stop the others
            failures += 1
            print(f"ERROR {case_dir.name}: {error}")
            continue
        if problems:
            failures += 1
            print(f"FAIL {case_dir.name}")
            for problem in problems:
                print(f"  {problem}")
        else:
            print(f"PASS {case_dir.name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
