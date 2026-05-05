from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from hermes.state_service.shared_types import (
    CHANGE_ORIGINS,
    CHANGE_STATUSES,
    ActorName,
    ChangeApprovalError,
    ChangeId,
    ChangeOrigin,
    ChangeRequestError,
    ChangeStatus,
    ChangeValidationError,
    PayloadStoreError,
    StateIOError,
    StatePath,
    StatePathError,
    StateServiceConfig,
    StateServiceError,
)


@pytest.mark.parametrize("origin", CHANGE_ORIGINS)
def test_change_origin_accepts_known_origins(origin: ChangeOrigin) -> None:
    assert TypeAdapter(ChangeOrigin).validate_python(origin) == origin


def test_change_origin_rejects_unknown_origin() -> None:
    with pytest.raises(ValidationError, match="workflow"):
        TypeAdapter(ChangeOrigin).validate_python("workflow")


@pytest.mark.parametrize("status", CHANGE_STATUSES)
def test_change_status_accepts_known_statuses(status: ChangeStatus) -> None:
    assert TypeAdapter(ChangeStatus).validate_python(status) == status


def test_change_status_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError, match="accepted"):
        TypeAdapter(ChangeStatus).validate_python("accepted")


def test_state_service_config_disables_trusted_workflow_bypass_by_default() -> None:
    config = StateServiceConfig()

    assert config.allow_trusted_workflow_bypass is False


def test_state_service_config_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra"):
        StateServiceConfig(allow_trusted_workflow_bypass=True, state_dir="logs")


def test_state_service_exception_hierarchy() -> None:
    assert issubclass(StatePathError, StateServiceError)
    assert issubclass(ChangeRequestError, StateServiceError)
    assert issubclass(ChangeValidationError, ChangeRequestError)
    assert issubclass(ChangeApprovalError, ChangeRequestError)
    assert issubclass(StateIOError, StateServiceError)
    assert issubclass(PayloadStoreError, StateServiceError)


def test_state_service_scalar_aliases_are_plain_strings() -> None:
    path: StatePath = "acquisition.result.status"
    change_id: ChangeId = "change-001"
    actor: ActorName = "operator"

    assert path == "acquisition.result.status"
    assert change_id == "change-001"
    assert actor == "operator"
