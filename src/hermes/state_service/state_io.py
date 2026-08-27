from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateIOError
from hermes.state_service.state_logger import StateLogger


class _NoAliasSafeDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


# Input-file lists longer than this are written to a sibling text file and
# referenced by the ``{file_list: <path>}`` form the loader expands, so the
# record stays short when a run has many input files.
MAX_INLINE_FILE_ENTRIES = 10

# The analysis stage and list field for each input-file list that can be moved
# out to a sibling text file.
_OFFLOADABLE_FILE_LISTS = (
    ("unpacking", "tpx3_files"),
    ("photon_reconstruction", "pixel_files"),
    ("event_reconstruction", "photon_parquet_files"),
)


def _offload_long_file_lists(data: dict[str, Any], record_directory: Path) -> None:
    """Move long input-file lists into sibling text files.

    Each list with more than ``MAX_INLINE_FILE_ENTRIES`` entries is written to a
    text file in the record's directory, one path per line, and replaced in the
    record with a ``{"file_list": <path>}`` reference that the loader expands.
    """

    analysis = data.get("analysis")
    if not isinstance(analysis, dict):
        return

    for stage_name, field_name in _OFFLOADABLE_FILE_LISTS:
        stage = analysis.get(stage_name)
        if not isinstance(stage, dict):
            continue
        entries = stage.get(field_name)
        if (
            not isinstance(entries, list)
            or len(entries) <= MAX_INLINE_FILE_ENTRIES
        ):
            continue
        list_path = record_directory / f"{field_name}.txt"
        list_path.write_text(
            "".join(f"{entry['path']}\n" for entry in entries),
            encoding="utf-8",
        )
        stage[field_name] = {"file_list": str(list_path)}


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
        record = HermesRecord.model_validate(data)
    except ValidationError as exc:
        msg = f"failed to validate HermesRecord YAML from {path}"
        raise StateIOError(msg) from exc

    StateLogger().log_state_loaded(record, path)
    return record


def save_hermes_record_to_yaml(record: HermesRecord, file_path: str | Path) -> Path:
    """Save a HermesRecord to a readable YAML file and return the written path."""

    path = Path(file_path)
    # exclude_none keeps fields with no value out of the file so the record only
    # shows what was actually set.
    data = record.model_dump(mode="json", by_alias=False, exclude_none=True)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _offload_long_file_lists(data, path.parent)
        content = yaml.dump(
            data,
            Dumper=_NoAliasSafeDumper,
            sort_keys=False,
            allow_unicode=True,
        )
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        msg = f"failed to write HermesRecord YAML to {path}"
        raise StateIOError(msg) from exc

    StateLogger().log_state_saved(record, path)
    return path
