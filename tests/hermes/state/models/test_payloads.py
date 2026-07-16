from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes.state.models.payloads import ExternalPayloadRef


HASH = "a" * 64


def test_external_payload_ref_requires_relative_path() -> None:
    with pytest.raises(ValidationError, match="relative to the run bundle"):
        ExternalPayloadRef(
            path="/tmp/payloads/pixel-config.bpc",
            media_type="application/octet-stream",
            sha256=HASH,
            size_bytes=8,
        )

    payload = ExternalPayloadRef(
        path="logs/payloads/pixel-config.bpc",
        media_type="application/octet-stream",
        sha256=HASH,
        size_bytes=8,
    )

    assert payload.path == Path("logs/payloads/pixel-config.bpc")
