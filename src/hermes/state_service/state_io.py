from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateIOError


class _NoAliasSafeDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def load_hermes_record_from_yaml(file_path: str | Path) -> HermesRecord:
    """Load and validate a HermesRecord from a YAML file."""

    path = Path(file_path)

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"failed to read HermesRecord YAML from {path}"
        raise StateIOError(msg) from exc
    except yaml.YAMLError as exc:
        msg = f"failed to parse HermesRecord YAML from {path}"
        raise StateIOError(msg) from exc

    if not isinstance(data, dict):
        msg = f"HermesRecord YAML must contain a top-level mapping: {path}"
        raise StateIOError(msg)

    try:
        return HermesRecord.model_validate(data)
    except ValidationError as exc:
        msg = f"failed to validate HermesRecord YAML from {path}"
        raise StateIOError(msg) from exc


def save_hermes_record_to_yaml(record: HermesRecord, file_path: str | Path) -> Path:
    """Save a HermesRecord to a readable YAML file and return the written path."""

    path = Path(file_path)
    data = record.model_dump(mode="json", by_alias=False)
    content = yaml.dump(
        data,
        Dumper=_NoAliasSafeDumper,
        sort_keys=False,
        allow_unicode=True,
    )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        msg = f"failed to write HermesRecord YAML to {path}"
        raise StateIOError(msg) from exc

    return path
