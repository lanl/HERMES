from __future__ import annotations

import json
import math
import runpy
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

_ROOT = Path(__file__).resolve().parents[3]
_compare_case = runpy.run_path(str(_ROOT / "evals/compare.py"))["compare_case"]
_PARQUET_PATH = "analysis/photons/timing_chip_0_photon_00000.parquet"


def _expected_case(tmp_path: Path, rows: list[dict[str, object]]) -> tuple[Path, Path]:
    expected_dir = tmp_path / "expected"
    expected_dir.mkdir()
    (expected_dir / "parquet_rows.json").write_text(
        json.dumps({_PARQUET_PATH: rows}), encoding="utf-8",
    )
    run_directory = tmp_path / "run"
    (run_directory / _PARQUET_PATH).parent.mkdir(parents=True)
    return expected_dir, run_directory


def test_parquet_rows_compare_exactly_without_changing_files(tmp_path: Path) -> None:
    rows = [
        {"photon_id": 0, "timestamp_canonical": 106.5, "quality_flags": 0},
        {"photon_id": 1, "timestamp_canonical": -37.75, "quality_flags": 3},
        {"photon_id": 2, "timestamp_canonical": 9007199254741004.0, "quality_flags": 0},
    ]
    expected_dir, run_directory = _expected_case(tmp_path, rows)
    parquet_file = run_directory / _PARQUET_PATH
    pq.write_table(pa.Table.from_pylist(rows), parquet_file)
    before = parquet_file.read_bytes()

    assert _compare_case(expected_dir, run_directory) == []
    assert parquet_file.read_bytes() == before


@pytest.mark.parametrize(("expected", "actual"), [
    pytest.param(106.5, math.nextafter(106.5, math.inf), id="one-small-float64-step"),
    pytest.param(9007199254740994.0, 9007199254740992.0, id="one-large-float64-step"),
    pytest.param(-37.75, -37.0, id="lost-fraction"),
    pytest.param(106.5, float("nan"), id="nan"),
])
def test_parquet_comparison_detects_changed_photon_time(
    tmp_path: Path, expected: float, actual: float,
) -> None:
    expected_dir, run_directory = _expected_case(
        tmp_path, [{"timestamp_canonical": expected}],
    )
    pq.write_table(pa.table({"timestamp_canonical": [actual]}), run_directory / _PARQUET_PATH)

    problems = _compare_case(expected_dir, run_directory)
    assert len(problems) == 1
    assert "timestamp_canonical" in problems[0]
    assert "expected" in problems[0]


def test_parquet_comparison_requires_all_rows_and_columns(tmp_path: Path) -> None:
    expected_dir, run_directory = _expected_case(
        tmp_path, [{"photon_id": 0, "timestamp_canonical": 106.5},
                   {"photon_id": 1, "timestamp_canonical": 203.0}],
    )
    pq.write_table(pa.table({"photon_id": [0]}), run_directory / _PARQUET_PATH)

    problems = _compare_case(expected_dir, run_directory)
    assert any("length 1 != expected 2" in problem for problem in problems)
    assert any("timestamp_canonical: missing" in problem for problem in problems)


def test_missing_parquet_file_fails_the_case(tmp_path: Path) -> None:
    expected_dir, run_directory = _expected_case(tmp_path, [])

    assert _compare_case(expected_dir, run_directory) == [
        f"missing produced Parquet file: {_PARQUET_PATH}",
    ]


def test_unreadable_parquet_file_fails_the_case(tmp_path: Path) -> None:
    expected_dir, run_directory = _expected_case(tmp_path, [])
    (run_directory / _PARQUET_PATH).write_bytes(b"not a Parquet file")

    problems = _compare_case(expected_dir, run_directory)
    assert len(problems) == 1
    assert problems[0].startswith(f"cannot read Parquet file {_PARQUET_PATH}:")


def test_cases_without_parquet_expectations_keep_existing_behavior(tmp_path: Path) -> None:
    expected_dir = tmp_path / "expected"
    expected_dir.mkdir()
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    (run_directory / "uncompared.parquet").write_bytes(b"not a Parquet file")

    assert _compare_case(expected_dir, run_directory) == []
