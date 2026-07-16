from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_core import PydanticSerializationError

from hermes.state.models.shared_models import JsonValue, utc_now
from hermes.state.state import HermesRecord
from hermes.state_service.change_requests import ChangeRequest
from hermes.state_service.shared_types import (
    ActorName,
    ChangeApprovalError,
    ChangeId,
    ChangeOrigin,
    ChangeRequestError,
    ChangeValidationError,
    StatePath,
    StatePathError,
    StateServiceConfig,
)
from hermes.state_service.state_logger import StateLogger

_ANY_ADAPTER = TypeAdapter(Any)
_JSON_VALUE_ADAPTER = TypeAdapter(JsonValue)


class StateAuditLogger(Protocol):
    def log_change(self, change_request: ChangeRequest) -> None: ...

    def log_validation_failure(
        self,
        path: StatePath,
        error: str,
        *,
        change_id: str | None = None,
        proposed_value: JsonValue = None,
    ) -> None: ...


class StateManager:
    """Mutation gate for a single durable HermesRecord."""

    def __init__(
        self,
        record: HermesRecord,
        *,
        config: StateServiceConfig | None = None,
        state_logger: StateAuditLogger | None = None,
    ) -> None:
        self._record = record.model_copy(deep=True)
        self._config = config or StateServiceConfig()
        self._state_logger = state_logger or StateLogger()
        self._changes: dict[ChangeId, ChangeRequest] = {}

    def get_state(self) -> HermesRecord:
        return self._record.model_copy(deep=True)

    def get_value(self, path: StatePath) -> Any:
        return _copy_value(_get_path_value(self._record, path))

    def get_change(self, change_id: ChangeId) -> ChangeRequest:
        return self._get_change(change_id).model_copy(deep=True)

    def list_pending_changes(self) -> list[ChangeRequest]:
        return [
            change.model_copy(deep=True)
            for change in self._changes.values()
            if change.status == "pending"
        ]

    def propose_change(
        self,
        path: StatePath,
        new_value: Any,
        *,
        origin: ChangeOrigin,
        proposer: ActorName,
        justification: str | None = None,
    ) -> ChangeRequest:
        previous_value = _to_json_value(_get_path_value(self._record, path))

        try:
            validated_record = _record_with_change(self._record, path, new_value)
        except StatePathError:
            raise
        except ValidationError as exc:
            proposed_value = _best_effort_json_value(new_value)
            self._state_logger.log_validation_failure(
                path,
                str(exc),
                proposed_value=proposed_value,
            )
            msg = f"proposed change failed validation for {path}"
            raise ChangeValidationError(msg) from exc

        proposed_value = _to_json_value(_get_path_value(validated_record, path))
        change = ChangeRequest(
            path=path,
            previous_value=previous_value,
            proposed_value=proposed_value,
            origin=origin,
            proposer=proposer,
            justification=justification,
        )
        return self._store_and_log_change(change)

    def approve_change(
        self,
        change_id: ChangeId,
        *,
        approver: ActorName,
        justification: str | None = None,
    ) -> ChangeRequest:
        change = self._get_change(change_id)
        if change.status != "pending":
            msg = f"only pending changes can be approved: {change_id}"
            raise ChangeRequestError(msg)

        approved = _replace_change(
            change,
            status="approved",
            approved_by=approver,
            approved_at=utc_now(),
            justification=justification or change.justification,
        )
        return self._store_and_log_change(approved)

    def reject_change(
        self,
        change_id: ChangeId,
        *,
        rejected_by: ActorName,
        reason: str | None = None,
    ) -> ChangeRequest:
        change = self._get_change(change_id)
        if change.status not in {"pending", "approved"}:
            msg = f"only pending or approved changes can be rejected: {change_id}"
            raise ChangeRequestError(msg)

        rejected = _replace_change(
            change,
            status="rejected",
            rejected_by=rejected_by,
            rejected_at=utc_now(),
            rejection_reason=reason,
        )
        return self._store_and_log_change(rejected)

    def apply_change(self, change_id: ChangeId) -> ChangeRequest:
        change = self._get_change(change_id)
        approval_bypassed = False

        if change.status == "approved":
            pass
        elif (
            change.status == "pending"
            and change.origin == "trusted_workflow"
            and self._config.allow_trusted_workflow_bypass
        ):
            approval_bypassed = True
        elif change.status == "pending":
            msg = f"change requires approval before apply: {change_id}"
            raise ChangeApprovalError(msg)
        else:
            msg = (
                "only pending trusted workflow or approved changes can be applied: "
                f"{change_id}"
            )
            raise ChangeRequestError(msg)

        try:
            updated_record = _record_with_change(
                self._record,
                change.path,
                change.proposed_value,
            )
        except ValidationError as exc:
            failed = self._mark_failed(change, str(exc))
            self._state_logger.log_validation_failure(
                change.path,
                str(exc),
                change_id=change.change_id,
                proposed_value=change.proposed_value,
            )
            self._store_and_log_change(failed)
            msg = f"approved change failed validation during apply: {change_id}"
            raise ChangeValidationError(msg) from exc

        self._record = updated_record
        applied = _replace_change(
            change,
            status="applied",
            applied_at=utc_now(),
            approval_bypassed=approval_bypassed,
        )
        return self._store_and_log_change(applied)

    def _get_change(self, change_id: ChangeId) -> ChangeRequest:
        try:
            return self._changes[change_id]
        except KeyError as exc:
            msg = f"unknown change request: {change_id}"
            raise ChangeRequestError(msg) from exc

    def _store_and_log_change(self, change: ChangeRequest) -> ChangeRequest:
        self._changes[change.change_id] = change
        self._state_logger.log_change(change)
        return change.model_copy(deep=True)

    def _mark_failed(self, change: ChangeRequest, reason: str) -> ChangeRequest:
        return _replace_change(
            change,
            status="failed",
            failure_reason=reason,
            failed_at=utc_now(),
        )


def _replace_change(change: ChangeRequest, **updates: Any) -> ChangeRequest:
    data = change.model_dump(mode="json")
    data.update(updates)
    return ChangeRequest.model_validate(data)


def _record_with_change(
    record: HermesRecord,
    path: StatePath,
    value: Any,
) -> HermesRecord:
    updated = record.model_copy(deep=True)
    _set_path_value(updated, path, value)
    return HermesRecord.model_validate(updated.model_dump(mode="json"))


def _get_path_value(record: HermesRecord, path: StatePath) -> Any:
    current: Any = record
    segments = _path_segments(path)
    for index, segment in enumerate(segments):
        if not isinstance(current, BaseModel):
            msg = f"state path cannot traverse non-model value at {segment}: {path}"
            raise StatePathError(msg)
        if segment not in current.__class__.model_fields:
            msg = f"unknown state path segment {segment}: {path}"
            raise StatePathError(msg)
        current = getattr(current, segment)
        if current is None and index < len(segments) - 1:
            msg = f"state path cannot traverse unset value at {segment}: {path}"
            raise StatePathError(msg)
    return current


def _set_path_value(record: HermesRecord, path: StatePath, value: Any) -> None:
    segments = _path_segments(path)
    parent: Any = record
    for segment in segments[:-1]:
        if not isinstance(parent, BaseModel):
            msg = f"state path cannot traverse non-model value at {segment}: {path}"
            raise StatePathError(msg)
        if segment not in parent.__class__.model_fields:
            msg = f"unknown state path segment {segment}: {path}"
            raise StatePathError(msg)
        parent = getattr(parent, segment)
        if parent is None:
            msg = f"state path cannot traverse unset value at {segment}: {path}"
            raise StatePathError(msg)

    leaf = segments[-1]
    if not isinstance(parent, BaseModel):
        msg = f"state path parent is not a model: {path}"
        raise StatePathError(msg)
    if leaf not in parent.__class__.model_fields:
        msg = f"unknown state path segment {leaf}: {path}"
        raise StatePathError(msg)
    setattr(parent, leaf, value)


def _path_segments(path: StatePath) -> tuple[str, ...]:
    try:
        normalized = ChangeRequest(
            path=path,
            previous_value=None,
            proposed_value=None,
            origin="trusted_workflow",
            proposer="state_manager",
        ).path
    except ValidationError as exc:
        msg = f"invalid state path: {path}"
        raise StatePathError(msg) from exc
    return tuple(normalized.split("."))


def _to_json_value(value: Any) -> JsonValue:
    dumped = _ANY_ADAPTER.dump_python(value, mode="json")
    return _JSON_VALUE_ADAPTER.validate_python(dumped)


def _best_effort_json_value(value: Any) -> JsonValue:
    try:
        return _to_json_value(value)
    except (PydanticSerializationError, ValidationError):
        return repr(value)


def _copy_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_copy(deep=True)
    return deepcopy(value)
