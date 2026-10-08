from __future__ import annotations

import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hermes.mcp.server import OutputFilesRequest, describe_output_files

_TEST_DATA = Path(__file__).resolve().parents[3] / "data"
_PIXEL_HITS = _TEST_DATA / "pixel_hits" / "Tantalum_IronPowder.parquet"
_PHOTONS = _TEST_DATA / "photons" / "Tantalum_IronPowder.parquet"
_TICK_SECONDS = 25e-9 / 12_288


def _copy(source: Path, folder: Path, name: str | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy(source, folder / (name or source.name)))


@pytest.fixture
def analysis(tmp_path: Path) -> Path:
    """An analysis folder with the test pixel hits and photons in it."""
    folder = tmp_path / "analysis"
    _copy(_PIXEL_HITS, folder / "pixel_hits")
    _copy(_PHOTONS, folder / "photons")
    return folder


def _describe(folder: Path):
    return describe_output_files(OutputFilesRequest(analysis_directory=folder))


def test_describes_pixel_hits_and_photons(analysis: Path) -> None:
    result = _describe(analysis)

    assert result.analysis_directory == analysis.resolve()
    assert result.tick_seconds == pytest.approx(_TICK_SECONDS)
    assert [summary.folder for summary in result.folders] == [
        "photons",
        "pixel_hits",
    ]
    photons, pixel_hits = result.folders

    assert pixel_hits.file_count == 1
    assert pixel_hits.total_bytes == _PIXEL_HITS.stat().st_size
    assert pixel_hits.row_count == 505_721
    assert pixel_hits.columns == {
        "chunk_index": "uint64",
        "packet_index": "uint64",
        "local_x": "uint16",
        "local_y": "uint16",
        "tot_raw": "uint16",
        "timestamp_canonical": "uint64",
    }
    assert pixel_hits.first_timestamp_canonical == 384_070_656
    assert pixel_hits.last_timestamp_canonical == 2_452_555_401_216
    assert pixel_hits.time_span_seconds == pytest.approx(
        (2_452_555_401_216 - 384_070_656) * _TICK_SECONDS
    )
    assert pixel_hits.example_file == "Tantalum_IronPowder.parquet"
    assert len(pixel_hits.example_rows) == 3
    assert set(pixel_hits.example_rows[0]) == set(pixel_hits.columns)
    assert pixel_hits.problems == []

    assert photons.row_count == 99_909
    assert photons.columns["timestamp_canonical"] == "double"
    assert photons.first_timestamp_canonical == pytest.approx(9_829_920_222.65438)
    assert photons.last_timestamp_canonical == pytest.approx(2_452_555_394_984.3145)
    assert len(photons.example_rows) == 3

    assert "Found 2 Parquet file(s) in 2 folder(s): photons, pixel_hits" in (
        result.message
    )
    assert "hermes-config-and-files skill" in result.message
    assert "output_files.md" in result.message
    assert "had problems" not in result.message


def test_adds_up_every_file_in_a_folder(analysis: Path) -> None:
    second = _copy(_PHOTONS, analysis / "photons", "second.parquet")

    photons = _describe(analysis).folders[0]

    assert photons.file_count == 2
    assert photons.row_count == 2 * 99_909
    assert photons.total_bytes == 2 * second.stat().st_size


def test_an_unreadable_file_is_left_out_and_named(analysis: Path) -> None:
    (analysis / "photons" / "still_writing.parquet").write_bytes(b"not parquet")

    result = _describe(analysis)

    photons = result.folders[0]
    assert photons.file_count == 1
    assert photons.row_count == 99_909
    assert len(photons.problems) == 1
    assert "still_writing.parquet" in photons.problems[0]
    assert "1 file(s) had problems" in result.message


def test_a_folder_without_timestamp_canonical(analysis: Path) -> None:
    (analysis / "events").mkdir()
    pq.write_table(
        pa.table({"event_id": pa.array([], pa.uint64())}),
        analysis / "events" / "empty.parquet",
    )
    (analysis / "unrecognized_packets").mkdir()

    result = _describe(analysis)

    assert [summary.folder for summary in result.folders] == [
        "events",
        "photons",
        "pixel_hits",
    ]
    events = result.folders[0]
    assert events.row_count == 0
    assert events.columns == {"event_id": "uint64"}
    assert events.first_timestamp_canonical is None
    assert events.time_span_seconds is None
    assert events.example_rows == []


def test_a_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        _describe(tmp_path / "missing")


def test_a_folder_with_no_parquet_files(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir()

    with pytest.raises(ValueError, match="no folders with Parquet files"):
        _describe(tmp_path)


def test_a_file_with_no_timestamp_statistics(analysis: Path) -> None:
    table = pq.read_table(_PHOTONS).slice(0, 10)
    pq.write_table(
        table, analysis / "photons" / "no_statistics.parquet", write_statistics=False
    )

    photons = _describe(analysis).folders[0]

    assert photons.file_count == 2
    assert photons.row_count == 99_909 + 10
    assert photons.first_timestamp_canonical is None
    assert photons.last_timestamp_canonical is None
    assert photons.time_span_seconds is None
    assert len(photons.problems) == 1
    assert "no_statistics.parquet has no timestamp_canonical statistics" in (
        photons.problems[0]
    )


def test_a_timestamp_column_with_only_empty_values(analysis: Path) -> None:
    pq.write_table(
        pa.table({"timestamp_canonical": pa.array([None, None], pa.uint64())}),
        analysis / "photons" / "only_empty.parquet",
    )

    photons = _describe(analysis).folders[0]

    assert photons.first_timestamp_canonical == pytest.approx(9_829_920_222.65438)
    assert photons.problems == []
