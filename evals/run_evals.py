"""Run every eval case and compare its output against the case's expected/ files.

Run from the repo root:

    pixi run python evals/run_evals.py

Each case's config.yaml names its own working directory, so cases do not clobber
each other. Exit status is non-zero if any case deviates from its expected/ files.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from hermes.state_service.state_io import load_hermes_record_from_yaml
from hermes.workflows.workflow import Workflow

import compare

_CASES_DIR = Path(__file__).parent / "cases"


def run_case(case_directory: Path) -> list[str]:

    # Set the config file
    config_file = case_directory / "input" / "config.yaml"

    # Load the HERMES record from the config file
    record = load_hermes_record_from_yaml(str(config_file))

    # Determine the root directory for comparison based on the run directory of the record
    compare_root = record.environment.run_directory.resolved_path

    # Clear any output from a previous run so the workflow always runs fresh
    # rather than skipping files it already produced (a skipped file reports a
    # different status and leaves renamed-away files behind, both of which the
    # expected fixtures would flag).
    if compare_root.exists():
        shutil.rmtree(compare_root)

    # Run the workflow
    Workflow(record).run()

    # Return the comparison results
    return compare.compare_case(case_directory / "expected", compare_root)


def main() -> int:
    failures = 0
    for case_directory in sorted(p for p in _CASES_DIR.iterdir() if p.is_dir()):
        try:
            problems = run_case(case_directory)
        except Exception as error:  # a broken case should not stop the others
            failures += 1
            print(f"ERROR {case_directory.name}: {error}")
            continue
        if problems:
            failures += 1
            print(f"FAIL {case_directory.name}")
            for problem in problems:
                print(f"  {problem}")
        else:
            print(f"PASS {case_directory.name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
