from __future__ import annotations

from hashlib import sha256
from json import loads
from pathlib import Path

import pytest

from hermes.state.models.payloads import ExternalPayloadRef
from hermes.state_service.payload_store import PayloadStore
from hermes.state_service.shared_types import PayloadStoreError


def test_payload_store_writes_bytes_under_logs_payloads(tmp_path: Path) -> None:
    store = PayloadStore(tmp_path)
    payload = b"pixel-config-bytes"
    digest = sha256(payload).hexdigest()

    payload_ref = store.store_bytes(
        payload,
        name="detector_pixel_config.bpc",
        media_type="application/octet-stream",
        description=" TPX3 pixel config ",
    )

    assert isinstance(payload_ref, ExternalPayloadRef)
    assert payload_ref.path == Path(
        f"logs/payloads/detector_pixel_config_{digest[:12]}.bpc"
    )
    assert payload_ref.media_type == "application/octet-stream"
    assert payload_ref.sha256 == digest
    assert payload_ref.size_bytes == len(payload)
    assert payload_ref.description == "TPX3 pixel config"
    assert payload_ref.source_path is None
    assert not payload_ref.path.is_absolute()
    assert (tmp_path / payload_ref.path).read_bytes() == payload


def test_payload_store_writes_json_with_stable_content(tmp_path: Path) -> None:
    store = PayloadStore(tmp_path)
    payload = {"threshold": 4, "chips": [{"id": 1, "enabled": True}]}

    payload_ref = store.store_json(payload, name="detector_dacs.json")

    content = (tmp_path / payload_ref.path).read_text(encoding="utf-8")
    assert loads(content) == payload
    assert content.endswith("\n")
    assert payload_ref.media_type == "application/json"
    assert payload_ref.size_bytes == len(content.encode("utf-8"))
    assert payload_ref.sha256 == sha256(content.encode("utf-8")).hexdigest()


def test_payload_store_copies_source_file_and_records_source_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "tpx3-demo.dacs"
    source.parent.mkdir()
    source.write_bytes(b'{"dac": 10}\n')
    store = PayloadStore(tmp_path / "run-001")

    payload_ref = store.store_file(
        source,
        media_type="application/json",
        description="DAC settings",
    )

    assert payload_ref.path.name.startswith("tpx3-demo_")
    assert payload_ref.path.suffix == ".dacs"
    assert payload_ref.source_path == source
    stored_payload = store.working_dir / payload_ref.path
    assert stored_payload.read_bytes() == source.read_bytes()


@pytest.mark.parametrize(
    "name",
    [
        "",
        " ",
        "../detector_dacs.json",
        "payloads/detector_dacs.json",
        ".json",
    ],
)
def test_payload_store_rejects_invalid_payload_names(
    tmp_path: Path,
    name: str,
) -> None:
    store = PayloadStore(tmp_path)

    with pytest.raises(PayloadStoreError, match="payload name"):
        store.store_bytes(b"{}", name=name, media_type="application/json")


def test_payload_store_rejects_blank_media_type(tmp_path: Path) -> None:
    store = PayloadStore(tmp_path)

    with pytest.raises(PayloadStoreError, match="media_type"):
        store.store_bytes(b"{}", name="detector_dacs.json", media_type=" ")


def test_payload_store_rejects_non_bytes_payload(tmp_path: Path) -> None:
    store = PayloadStore(tmp_path)

    with pytest.raises(PayloadStoreError, match="bytes"):
        store.store_bytes("not bytes", name="payload.txt", media_type="text/plain")


def test_payload_store_rejects_non_json_payload(tmp_path: Path) -> None:
    store = PayloadStore(tmp_path)

    with pytest.raises(PayloadStoreError, match="JSON-compatible"):
        store.store_json({"bad": object()}, name="bad.json")


def test_payload_store_wraps_missing_source_file_errors(tmp_path: Path) -> None:
    store = PayloadStore(tmp_path)

    with pytest.raises(PayloadStoreError, match="read") as exc_info:
        store.store_file(tmp_path / "missing.dacs")

    assert isinstance(exc_info.value.__cause__, OSError)
