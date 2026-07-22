from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger as loguru_logger

from hermes.state.models.shared_models import JsonValue
from hermes.state.state import HermesRecord
from hermes.state_service.change_requests import ChangeRequest
from hermes.state_service.shared_types import StatePath


class StateLogger:
    """Thin structured logger for HERMES record audit events."""

    def __init__(self, logger: Any | None = None, **context: Any) -> None:
        base_logger = logger if logger is not None else loguru_logger
        self._logger = base_logger.bind(domain="state", **context)

    def log_initial_state(self, record: HermesRecord) -> None:
        self._logger.info(
            "state.initial_record",
            event_type="state.initial_record",
            record=_serialize_record(record),
            **_record_context(record),
        )

    def log_state_loaded(self, record: HermesRecord, path: str | Path) -> None:
        self._logger.info(
            "state.loaded",
            event_type="state.loaded",
            record_path=str(path),
            **_record_context(record),
        )

    def log_state_saved(self, record: HermesRecord, path: str | Path) -> None:
        self._logger.info(
            "state.saved",
            event_type="state.saved",
            record_path=str(path),
            **_record_context(record),
        )

    def log_change(self, change_request: ChangeRequest) -> None:
        change = change_request.model_dump(mode="json")
        self._logger.info(
            "state.change",
            event_type="state.change",
            change=change,
            change_id=change_request.change_id,
            path=change_request.path,
            status=change_request.status,
            origin=change_request.origin,
            proposer=change_request.proposer,
            approved_by=change_request.approved_by,
            rejected_by=change_request.rejected_by,
            rejection_reason=change_request.rejection_reason,
            approval_bypassed=change_request.approval_bypassed,
            failure_reason=change_request.failure_reason,
            previous_value_summary=_value_summary(change_request.previous_value),
            proposed_value_summary=_value_summary(change_request.proposed_value),
        )

    def log_validation_failure(
        self,
        path: StatePath,
        error: str,
        *,
        change_id: str | None = None,
        proposed_value: JsonValue = None,
    ) -> None:
        self._logger.error(
            "state.validation_failed",
            event_type="state.validation_failed",
            change_id=change_id,
            path=path,
            error=error,
            proposed_value_summary=_value_summary(proposed_value),
        )


def _serialize_record(record: HermesRecord) -> dict[str, Any]:
    return record.model_dump(mode="json", by_alias=False)


def _record_context(record: HermesRecord) -> dict[str, Any]:
    return {
        "measurement_id": record.measurement_info.measurement_id,
        "run_number": record.measurement_info.run_number,
    }


def _value_summary(value: JsonValue) -> dict[str, Any]:
    if value is None or isinstance(value, str | int | float | bool):
        return {"kind": "inline_scalar", "value": value}

    if isinstance(value, list):
        return {"kind": "inline_list", "length": len(value)}

    if isinstance(value, dict):
        return {
            "kind": "inline_mapping",
            "size": len(value),
            "keys": sorted(value.keys())[:10],
        }

    return {"kind": "unknown"}
