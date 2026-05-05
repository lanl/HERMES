from __future__ import annotations

from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter, ValidationError

from hermes.state.models.payloads import ExternalPayloadRef
from hermes.state.models.shared_models import JsonValue
from hermes.state_service.shared_types import PayloadStoreError

_JSON_VALUE_ADAPTER: Final = TypeAdapter(JsonValue)
_PAYLOAD_ROOT: Final = Path("logs") / "payloads"


class PayloadStore:
    """Store externalized state payloads under a run's logs/payloads directory."""

    def __init__(self, working_dir: str | Path) -> None:
        self.working_dir = Path(working_dir).expanduser().resolve(strict=False)
        self.payload_dir = self.working_dir / _PAYLOAD_ROOT

    def store_bytes(
        self,
        payload: bytes,
        *,
        name: str,
        media_type: str,
        description: str | None = None,
        source_path: str | Path | None = None,
    ) -> ExternalPayloadRef:
        """Write bytes and return a relative ExternalPayloadRef."""

        if not isinstance(payload, bytes):
            msg = "payload must be bytes"
            raise PayloadStoreError(msg)

        media_type = _require_media_type(media_type)
        digest = sha256(payload).hexdigest()
        file_name = _hashed_file_name(name, digest)
        absolute_path = self.payload_dir / file_name

        try:
            absolute_path.parent.mkdir(parents=True, exist_ok=True)
            absolute_path.write_bytes(payload)
        except OSError as exc:
            msg = f"failed to write external payload to {absolute_path}"
            raise PayloadStoreError(msg) from exc

        return ExternalPayloadRef(
            path=_PAYLOAD_ROOT / file_name,
            media_type=media_type,
            sha256=digest,
            size_bytes=len(payload),
            description=_strip_optional_text(description),
            source_path=Path(source_path) if source_path is not None else None,
        )

    def store_json(
        self,
        payload: JsonValue,
        *,
        name: str,
        media_type: str = "application/json",
        description: str | None = None,
    ) -> ExternalPayloadRef:
        """Write a JSON state payload and return a relative ExternalPayloadRef."""

        try:
            validated_payload = _JSON_VALUE_ADAPTER.validate_python(payload)
        except ValidationError as exc:
            msg = "JSON payload must contain only JSON-compatible state values"
            raise PayloadStoreError(msg) from exc

        encoded = (
            dumps(
                validated_payload,
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
        return self.store_bytes(
            encoded,
            name=name,
            media_type=media_type,
            description=description,
        )

    def store_file(
        self,
        source_path: str | Path,
        *,
        name: str | None = None,
        media_type: str = "application/octet-stream",
        description: str | None = None,
    ) -> ExternalPayloadRef:
        """Copy an existing file and return an ExternalPayloadRef."""

        source = Path(source_path).expanduser()
        try:
            payload = source.read_bytes()
        except OSError as exc:
            msg = f"failed to read external payload source file {source}"
            raise PayloadStoreError(msg) from exc

        return self.store_bytes(
            payload,
            name=name or source.name,
            media_type=media_type,
            description=description,
            source_path=source,
        )


def _require_media_type(value: str) -> str:
    media_type = value.strip()
    if not media_type:
        msg = "media_type must not be blank"
        raise PayloadStoreError(msg)
    return media_type


def _strip_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _hashed_file_name(name: str, digest: str) -> str:
    requested = name.strip()
    if not requested:
        msg = "payload name must not be blank"
        raise PayloadStoreError(msg)

    path = Path(requested)
    if (
        path.name != requested
        or requested in {".", ".."}
        or requested.startswith(".")
    ):
        msg = "payload name must be a file name, not a path"
        raise PayloadStoreError(msg)

    suffix = "".join(path.suffixes)
    stem = path.name[: -len(suffix)] if suffix else path.name
    if not stem:
        msg = "payload name must include a file stem"
        raise PayloadStoreError(msg)

    return f"{stem}_{digest[:12]}{suffix}"
