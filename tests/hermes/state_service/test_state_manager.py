from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hermes.state.models.acquisition.serval import (
    ServalAcquisitionResult,
    ServalAcquisitionState,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.state import HermesRecord
from hermes.state_service.change_requests import ChangeRequest
from hermes.state_service.shared_types import (
    ChangeApprovalError,
    ChangeRequestError,
    ChangeValidationError,
    StatePathError,
    StateServiceConfig,
)
from hermes.state_service.state_manager import StateManager


class CapturingStateLogger:
    def __init__(self) -> None:
        self.changes: list[ChangeRequest] = []
        self.validation_failures: list[dict[str, Any]] = []

    def log_change(self, change_request: ChangeRequest) -> None:
        self.changes.append(change_request.model_copy(deep=True))

    def log_validation_failure(
        self,
        path: str,
        error: str,
        *,
        change_id: str | None = None,
        proposed_value: Any = None,
    ) -> None:
        self.validation_failures.append(
            {
                "path": path,
                "error": error,
                "change_id": change_id,
                "proposed_value": proposed_value,
            }
        )


def _record(tmp_path: Path, *, acquisition: bool = True) -> HermesRecord:
    return HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id="LC-20260505",
            run_number=1,
        ),
        environment=RuntimeEnvironment(working_dir=tmp_path / "run-001"),
        acquisition=(
            ServalAcquisitionState(
                result=ServalAcquisitionResult(status="planned", frames=0)
            )
            if acquisition
            else None
        ),
    )


def test_state_manager_returns_defensive_state_copy(tmp_path: Path) -> None:
    manager = StateManager(_record(tmp_path), state_logger=CapturingStateLogger())

    state = manager.get_state()
    state.measurement_info.measurement_id = "changed"

    assert manager.get_state().measurement_info.measurement_id == "LC-20260505"


def test_state_manager_get_value_returns_defensive_copy(tmp_path: Path) -> None:
    manager = StateManager(_record(tmp_path), state_logger=CapturingStateLogger())

    result = manager.get_value("acquisition.result")
    result.status = "failed"

    current_result = manager.get_value("acquisition.result")
    assert current_result.status == "planned"
    assert manager.get_value("acquisition.result.status") == "planned"


def test_state_manager_proposes_valid_change_without_mutating_record(
    tmp_path: Path,
) -> None:
    state_logger = CapturingStateLogger()
    manager = StateManager(_record(tmp_path), state_logger=state_logger)

    change = manager.propose_change(
        "acquisition.result.status",
        "completed",
        origin="trusted_workflow",
        proposer="serval_workflow",
        justification="measurement completed",
    )

    assert change.status == "pending"
    assert change.previous_value == "planned"
    assert change.proposed_value == "completed"
    assert manager.get_value("acquisition.result.status") == "planned"
    assert manager.list_pending_changes()[0].change_id == change.change_id
    assert state_logger.changes[-1].change_id == change.change_id


def test_state_manager_approve_and_apply_user_change(tmp_path: Path) -> None:
    state_logger = CapturingStateLogger()
    manager = StateManager(_record(tmp_path), state_logger=state_logger)
    change = manager.propose_change(
        "acquisition.result.status",
        "completed",
        origin="user",
        proposer="operator",
    )

    with pytest.raises(ChangeApprovalError, match="requires approval"):
        manager.apply_change(change.change_id)

    approved = manager.approve_change(change.change_id, approver="lead_operator")
    applied = manager.apply_change(change.change_id)

    assert approved.status == "approved"
    assert approved.approved_by == "lead_operator"
    assert applied.status == "applied"
    assert applied.approved_by == "lead_operator"
    assert applied.approval_bypassed is False
    assert manager.get_value("acquisition.result.status") == "completed"
    assert manager.list_pending_changes() == []
    assert [change.status for change in state_logger.changes[-3:]] == [
        "pending",
        "approved",
        "applied",
    ]


def test_state_manager_rejects_pending_ai_change(tmp_path: Path) -> None:
    manager = StateManager(_record(tmp_path), state_logger=CapturingStateLogger())
    change = manager.propose_change(
        "acquisition.result.status",
        "failed",
        origin="ai",
        proposer="agent",
    )

    rejected = manager.reject_change(
        change.change_id,
        rejected_by="operator",
        reason="not consistent with acquisition logs",
    )

    assert rejected.status == "rejected"
    assert rejected.rejected_by == "operator"
    assert rejected.rejection_reason == "not consistent with acquisition logs"
    assert manager.list_pending_changes() == []
    with pytest.raises(ChangeRequestError, match="can be applied"):
        manager.apply_change(change.change_id)


def test_state_manager_trusted_workflow_bypass_is_disabled_by_default(
    tmp_path: Path,
) -> None:
    manager = StateManager(_record(tmp_path), state_logger=CapturingStateLogger())
    change = manager.propose_change(
        "acquisition.result.status",
        "completed",
        origin="trusted_workflow",
        proposer="serval_workflow",
    )

    with pytest.raises(ChangeApprovalError, match="requires approval"):
        manager.apply_change(change.change_id)


def test_state_manager_applies_trusted_workflow_change_when_bypass_is_enabled(
    tmp_path: Path,
) -> None:
    manager = StateManager(
        _record(tmp_path),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=CapturingStateLogger(),
    )
    change = manager.propose_change(
        "acquisition.result.status",
        "completed",
        origin="trusted_workflow",
        proposer="serval_workflow",
    )

    applied = manager.apply_change(change.change_id)

    assert applied.status == "applied"
    assert applied.approval_bypassed is True
    assert applied.approved_by is None
    assert manager.get_value("acquisition.result.status") == "completed"


def test_state_manager_can_initialize_optional_top_level_acquisition(
    tmp_path: Path,
) -> None:
    manager = StateManager(
        _record(tmp_path, acquisition=False),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        state_logger=CapturingStateLogger(),
    )
    change = manager.propose_change(
        "acquisition",
        {"mode": "serval", "result": {"status": "planned"}},
        origin="trusted_workflow",
        proposer="serval_workflow",
    )

    manager.apply_change(change.change_id)

    acquisition = manager.get_value("acquisition")
    assert acquisition is not None
    assert acquisition.mode == "serval"
    assert acquisition.result.status == "planned"


def test_state_manager_rejects_invalid_paths(tmp_path: Path) -> None:
    manager = StateManager(_record(tmp_path), state_logger=CapturingStateLogger())

    with pytest.raises(StatePathError, match="unknown"):
        manager.get_value("acquisition.result.not_a_field")

    with pytest.raises(StatePathError, match="invalid state path"):
        manager.get_value("acquisition.result.artifacts[0]")

    with pytest.raises(StatePathError, match="unset value"):
        StateManager(
            _record(tmp_path, acquisition=False),
            state_logger=CapturingStateLogger(),
        ).propose_change(
            "acquisition.result.status",
            "completed",
            origin="trusted_workflow",
            proposer="serval_workflow",
        )


def test_state_manager_rejects_invalid_values_and_logs_failure(
    tmp_path: Path,
) -> None:
    state_logger = CapturingStateLogger()
    manager = StateManager(_record(tmp_path), state_logger=state_logger)

    with pytest.raises(ChangeValidationError, match="failed validation"):
        manager.propose_change(
            "acquisition.result.frames",
            -1,
            origin="trusted_workflow",
            proposer="serval_workflow",
        )

    assert state_logger.validation_failures
    assert state_logger.validation_failures[0]["path"] == (
        "acquisition.result.frames"
    )
    assert state_logger.validation_failures[0]["proposed_value"] == -1


def test_state_manager_change_accessors_return_defensive_copies(
    tmp_path: Path,
) -> None:
    manager = StateManager(_record(tmp_path), state_logger=CapturingStateLogger())
    change = manager.propose_change(
        "acquisition.result.status",
        "completed",
        origin="user",
        proposer="operator",
    )

    returned_change = manager.get_change(change.change_id)
    returned_change.proposer = "changed"
    pending_change = manager.list_pending_changes()[0]
    pending_change.proposer = "changed"

    assert manager.get_change(change.change_id).status == "pending"
    assert manager.get_change(change.change_id).proposer == "operator"
    assert manager.list_pending_changes()[0].status == "pending"
    assert manager.list_pending_changes()[0].proposer == "operator"


def test_state_manager_raises_for_unknown_change_ids(tmp_path: Path) -> None:
    manager = StateManager(_record(tmp_path), state_logger=CapturingStateLogger())

    with pytest.raises(ChangeRequestError, match="unknown change request"):
        manager.get_change("change-missing")
