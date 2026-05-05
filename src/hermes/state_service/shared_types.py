from __future__ import annotations

from typing import Literal, TypeAlias

from hermes.state.models.shared_models import StrictBaseModel

ChangeOrigin: TypeAlias = Literal["user", "ai", "trusted_workflow"]
ChangeStatus: TypeAlias = Literal[
    "pending",
    "approved",
    "rejected",
    "applied",
    "failed",
]
StatePath: TypeAlias = str
ChangeId: TypeAlias = str
ActorName: TypeAlias = str

CHANGE_ORIGINS: tuple[ChangeOrigin, ...] = ("user", "ai", "trusted_workflow")
CHANGE_STATUSES: tuple[ChangeStatus, ...] = (
    "pending",
    "approved",
    "rejected",
    "applied",
    "failed",
)


class StateServiceConfig(StrictBaseModel):
    """Configuration for state-service approval and mutation behavior."""

    allow_trusted_workflow_bypass: bool = False


class StateServiceError(Exception):
    """Base exception for state-service failures."""


class StatePathError(StateServiceError):
    """Raised when a state path cannot be resolved or mutated."""


class ChangeRequestError(StateServiceError):
    """Raised when a change request cannot move through its lifecycle."""


class ChangeValidationError(ChangeRequestError):
    """Raised when a proposed state change fails validation."""


class ChangeApprovalError(ChangeRequestError):
    """Raised when approval policy prevents a state change from being applied."""


class PayloadStoreError(StateServiceError):
    """Raised when an external state payload cannot be stored."""
