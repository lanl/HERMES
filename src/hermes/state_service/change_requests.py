from __future__ import annotations

from datetime import datetime
from re import Pattern, compile
from typing import Self
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from hermes.state.models.shared_models import JsonValue, StrictBaseModel, utc_now
from hermes.state_service.shared_types import (
    ActorName,
    ChangeId,
    ChangeOrigin,
    ChangeStatus,
    StatePath,
)

_STATE_PATH_SEGMENT: Pattern[str] = compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _new_change_id() -> str:
    return f"change-{uuid4().hex}"


class ChangeRequest(StrictBaseModel):
    """Auditable request to change one durable HermesRecord field."""

    change_id: ChangeId = Field(default_factory=_new_change_id, min_length=1)
    path: StatePath
    previous_value: JsonValue = None
    proposed_value: JsonValue
    origin: ChangeOrigin
    proposer: ActorName = Field(min_length=1)
    status: ChangeStatus = "pending"
    requested_at: datetime = Field(default_factory=utc_now)
    approved_by: ActorName | None = None
    approved_at: datetime | None = None
    rejected_by: ActorName | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    applied_at: datetime | None = None
    approval_bypassed: bool = False
    justification: str | None = None
    failure_reason: str | None = None
    failed_at: datetime | None = None

    @field_validator("path")
    @classmethod
    def validate_dotted_state_path(cls, value: str) -> str:
        path = value.strip()
        if not path:
            msg = "state path must not be blank"
            raise ValueError(msg)
        if "[" in path or "]" in path:
            msg = "state path must use dotted model field names without list indexes"
            raise ValueError(msg)

        segments = path.split(".")
        if any(segment == "" for segment in segments):
            msg = "state path must not contain empty segments"
            raise ValueError(msg)
        if any(
            _STATE_PATH_SEGMENT.fullmatch(segment) is None
            for segment in segments
        ):
            msg = "state path segments must be Python field names"
            raise ValueError(msg)
        return path

    @field_validator("proposer", "approved_by", "rejected_by")
    @classmethod
    def strip_actor_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            msg = "actor names must not be blank"
            raise ValueError(msg)
        return stripped

    @field_validator("justification", "rejection_reason", "failure_reason")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def validate_lifecycle_metadata(self) -> Self:
        if self.status == "pending":
            self._reject_pending_lifecycle_metadata()
        elif self.status == "approved":
            self._require_approval_metadata()
        elif self.status == "rejected":
            self._require_rejection_metadata()
        elif self.status == "applied":
            self._require_application_metadata()
        elif self.status == "failed":
            self._require_failure_metadata()

        if self.approval_bypassed:
            if self.origin != "trusted_workflow":
                msg = "only trusted_workflow changes may use approval_bypassed"
                raise ValueError(msg)
            if self.status != "applied":
                msg = "approval_bypassed is only valid for applied changes"
                raise ValueError(msg)
            if self.approved_by is not None or self.approved_at is not None:
                msg = "approval_bypassed changes must not include explicit approval metadata"
                raise ValueError(msg)

        return self

    def _reject_pending_lifecycle_metadata(self) -> None:
        if any(
            value is not None
            for value in (
                self.approved_by,
                self.approved_at,
                self.rejected_by,
                self.rejected_at,
                self.rejection_reason,
                self.applied_at,
                self.failure_reason,
                self.failed_at,
            )
        ):
            msg = "pending changes must not include lifecycle completion metadata"
            raise ValueError(msg)

    def _require_approval_metadata(self) -> None:
        if self.approval_bypassed:
            msg = "approved changes must use explicit approval metadata"
            raise ValueError(msg)
        if self.approved_by is None or self.approved_at is None:
            msg = "approved changes require approved_by and approved_at"
            raise ValueError(msg)

    def _require_rejection_metadata(self) -> None:
        if self.approval_bypassed:
            msg = "rejected changes must not use approval_bypassed"
            raise ValueError(msg)
        if self.rejected_by is None or self.rejected_at is None:
            msg = "rejected changes require rejected_by and rejected_at"
            raise ValueError(msg)

    def _require_application_metadata(self) -> None:
        if self.applied_at is None:
            msg = "applied changes require applied_at"
            raise ValueError(msg)
        if not self.approval_bypassed:
            self._require_approval_metadata()

    def _require_failure_metadata(self) -> None:
        if self.approval_bypassed:
            msg = "failed changes must not use approval_bypassed"
            raise ValueError(msg)
        if self.failure_reason is None or self.failed_at is None:
            msg = "failed changes require failure_reason and failed_at"
            raise ValueError(msg)
