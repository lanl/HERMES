"""Compare a produced working directory against a case's expected/ files.

Any string of the form ``<...>`` in an expected value (e.g. ``<TIMESTAMP>`` or
``<IGNORE: non-deterministic timing>``) is treated as a wildcard and skipped.
Everything else is a hard expectation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_WILDCARD = re.compile(r"^<.*>$")

# Expected summary file -> glob (relative to the working dir) for the produced file.
_SUMMARY_GLOBS = {
    "unpacker-summary.json": "analysis/logs/unpacking/*_unpacker_summary.json",
    "reconstruction-summary.json": "analysis/logs/photon_reconstruction/*_photon_reconstruction_summary.json",
}

_LOG_RELATIVE_PATH = "logs/HERMES-workflow.jsonl"


def _is_wildcard(value) -> bool:
    return isinstance(value, str) and bool(_WILDCARD.match(value))


def _diff(expected, actual, path: str) -> list[str]:
    if _is_wildcard(expected):
        return []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected object, got {type(actual).__name__}"]
        problems = []
        for key in expected:
            if key not in actual:
                problems.append(f"{path}/{key}: missing")
            else:
                problems += _diff(expected[key], actual[key], f"{path}/{key}")
        for key in actual:
            if key not in expected:
                problems.append(f"{path}/{key}: unexpected key")
        return problems
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path}: expected list, got {type(actual).__name__}"]
        problems = []
        if len(expected) != len(actual):
            problems.append(f"{path}: length {len(actual)} != expected {len(expected)}")
        for i, (e, a) in enumerate(zip(expected, actual)):
            problems += _diff(e, a, f"{path}[{i}]")
        return problems
    if expected != actual:
        return [f"{path}: {actual!r} != expected {expected!r}"]
    return []


def compare_json(expected_file: Path, actual_file: Path) -> list[str]:
    expected = json.loads(expected_file.read_text())
    actual = json.loads(actual_file.read_text())
    return _diff(expected, actual, expected_file.name)


def compare_jsonl(expected_file: Path, actual_file: Path) -> list[str]:
    expected_lines = expected_file.read_text().splitlines()
    actual_lines = actual_file.read_text().splitlines()
    problems = []
    if len(expected_lines) != len(actual_lines):
        problems.append(
            f"{expected_file.name}: {len(actual_lines)} records != expected {len(expected_lines)}"
        )
    for i, (e, a) in enumerate(zip(expected_lines, actual_lines)):
        problems += _diff(json.loads(e), json.loads(a), f"{expected_file.name}[{i}]")
    return problems


def _filenames_in_tree(text: str) -> set[str]:
    # Leaf file names from an output_tree.txt drawing (lines that name a file).
    names = set()
    for line in text.splitlines():
        token = line.split("── ")[-1].strip()
        if token and not token.endswith("/") and "." in token:
            names.add(token)
    return names


def compare_tree(expected_tree_file: Path, working_dir: Path) -> list[str]:
    expected_names = _filenames_in_tree(expected_tree_file.read_text())
    produced_names = {p.name for p in working_dir.rglob("*") if p.is_file()}
    problems = []
    for name in sorted(expected_names - produced_names):
        problems.append(f"output_tree: missing produced file {name}")
    for name in sorted(produced_names - expected_names):
        problems.append(f"output_tree: unexpected produced file {name}")
    return problems


def compare_case(expected_dir: Path, working_dir: Path) -> list[str]:
    """Compare a case's expected/ files against a produced working directory."""
    problems = []

    expected_log = expected_dir / "HERMES-workflow.jsonl"
    if expected_log.exists():
        actual_log = working_dir / _LOG_RELATIVE_PATH
        if actual_log.exists():
            problems += compare_jsonl(expected_log, actual_log)
        else:
            problems.append(f"missing produced log: {actual_log}")

    for expected_name, glob_pattern in _SUMMARY_GLOBS.items():
        expected_file = expected_dir / expected_name
        if not expected_file.exists():
            continue
        matches = sorted(working_dir.glob(glob_pattern))
        if matches:
            problems += compare_json(expected_file, matches[0])
        else:
            problems.append(f"no produced file for {expected_name} (looked for {glob_pattern})")

    expected_tree = expected_dir / "output_tree.txt"
    if expected_tree.exists():
        problems += compare_tree(expected_tree, working_dir)

    return problems
