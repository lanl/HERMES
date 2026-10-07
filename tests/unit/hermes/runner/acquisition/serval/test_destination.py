from __future__ import annotations

from pathlib import Path

from hermes.runner.acquisition.serval.destination import (
    _base_points_to,
    configure_raw_destination,
    raw_destination_points_to,
)
from hermes.state.models.acquisition.serval import (
    DestinationConfiguration,
    ServalRawDestination,
)


class _FakeDestinationClient:
    """Records the destination it is given and echoes it back on read."""

    def __init__(self, *, echo: DestinationConfiguration | None = None) -> None:
        self.put_destination_arg: DestinationConfiguration | None = None
        self._echo = echo

    def put_destination(self, destination: DestinationConfiguration) -> None:
        self.put_destination_arg = destination

    def get_destination(self) -> DestinationConfiguration:
        # By default echo exactly what was set, as a real server would.
        return self._echo if self._echo is not None else self.put_destination_arg


def test_configure_raw_destination_sets_creates_and_confirms(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    client = _FakeDestinationClient()

    applied = configure_raw_destination(client, raw_dir)

    assert raw_dir.is_dir()
    requested = client.put_destination_arg
    assert requested is not None
    assert requested.raw[0].base == raw_dir.as_uri()
    assert requested.raw[0].split_strategy == "FRAME"
    assert requested.raw[0].file_pattern is not None
    # Applied is the read-back and points at the same directory.
    assert applied.raw[0].base == raw_dir.as_uri()


def test_configure_raw_destination_returns_what_serval_reports_on_mismatch(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    mismatched = DestinationConfiguration(
        raw=[ServalRawDestination(base="file:///somewhere/else")]
    )
    client = _FakeDestinationClient(echo=mismatched)

    applied = configure_raw_destination(client, raw_dir)

    # It returns what the server reported, so the run can record it and then
    # refuse to measure.
    assert applied.raw[0].base == "file:///somewhere/else"
    assert raw_destination_points_to(applied, raw_dir) is False


def test_raw_destination_points_to_wants_only_the_one_raw_output(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    ours = ServalRawDestination(base=raw_dir.as_uri())
    elsewhere = ServalRawDestination(base="file:///somewhere/else")

    assert raw_destination_points_to(
        DestinationConfiguration(raw=[ours]), raw_dir
    ) is True
    # An extra raw output would also write raw data somewhere else.
    assert raw_destination_points_to(
        DestinationConfiguration(raw=[elsewhere, ours]), raw_dir
    ) is False
    assert raw_destination_points_to(
        DestinationConfiguration(raw=[ours, ours]), raw_dir
    ) is False
    assert raw_destination_points_to(DestinationConfiguration(), raw_dir) is False


def test_base_points_to_accepts_equivalent_file_uris(tmp_path: Path) -> None:
    directory = tmp_path / "raw"
    directory.mkdir()

    assert _base_points_to(directory.as_uri(), directory) is True
    assert _base_points_to(f"file:{directory}", directory) is True
    assert _base_points_to(f"file://{directory}", directory) is True
    assert _base_points_to("file:///not/the/same", directory) is False
