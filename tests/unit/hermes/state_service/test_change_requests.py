from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from hermes.state_service.change_requests import ChangeRequest


NOW = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)


def test_change_request_defaults_to_pending_with_generated_id() -> None:
    request = ChangeRequest(
        path="acquisition.result.status",
        previous_value="running",
        proposed_value="completed",
        origin="trusted_workflow",
        proposer=" serval_workflow ",
        justification=" mark acquisition complete ",
    )

    assert request.change_id.startswith("change-")
    assert request.path == "acquisition.result.status"
    assert request.proposer == "serval_workflow"
    assert request.status == "pending"
    assert request.approval_bypassed is False
    assert request.justification == "mark acquisition complete"
    assert request.requested_at.tzinfo is not None


@pytest.mark.parametrize(
    "path",
    [
        "",
        " ",
        "acquisition..result",
        "acquisition.result.output_files[0]",
        "acquisition.result.status-code",
    ],
)
def test_change_request_rejects_invalid_state_paths(path: str) -> None:
    with pytest.raises(ValidationError, match="state path"):
        ChangeRequest(
            path=path,
            previous_value=None,
            proposed_value="completed",
            origin="user",
            proposer="operator",
        )


def test_change_request_rejects_invalid_origin_and_status() -> None:
    with pytest.raises(ValidationError, match="origin"):
        ChangeRequest(
            path="acquisition.result.status",
            previous_value="running",
            proposed_value="completed",
            origin="workflow",
            proposer="operator",
        )

    with pytest.raises(ValidationError, match="status"):
        ChangeRequest(
            path="acquisition.result.status",
            previous_value="running",
            proposed_value="completed",
            origin="user",
            proposer="operator",
            status="accepted",
        )


def test_change_request_rejects_unserialized_values() -> None:
    with pytest.raises(ValidationError):
        ChangeRequest(
            path="acquisition.result.status",
            previous_value=None,
            proposed_value=object(),
            origin="user",
            proposer="operator",
        )


def test_approved_change_requires_approval_metadata() -> None:
    with pytest.raises(ValidationError, match="approved_by and approved_at"):
        ChangeRequest(
            path="acquisition.result.status",
            previous_value="running",
            proposed_value="completed",
            origin="user",
            proposer="operator",
            status="approved",
        )

    request = ChangeRequest(
        path="acquisition.result.status",
        previous_value="running",
        proposed_value="completed",
        origin="user",
        proposer="operator",
        status="approved",
        approved_by=" lead operator ",
        approved_at=NOW,
    )

    assert request.approved_by == "lead operator"
    assert request.approved_at == NOW


def test_rejected_change_requires_rejection_metadata() -> None:
    with pytest.raises(ValidationError, match="rejected_by and rejected_at"):
        ChangeRequest(
            path="acquisition.result.status",
            previous_value="running",
            proposed_value="completed",
            origin="ai",
            proposer="agent",
            status="rejected",
        )

    request = ChangeRequest(
        path="acquisition.result.status",
        previous_value="running",
        proposed_value="completed",
        origin="ai",
        proposer="agent",
        status="rejected",
        rejected_by="operator",
        rejected_at=NOW,
        rejection_reason=" not consistent with acquisition logs ",
    )

    assert request.rejected_by == "operator"
    assert request.rejected_at == NOW
    assert request.rejection_reason == "not consistent with acquisition logs"


def test_applied_change_requires_application_and_approval_metadata() -> None:
    with pytest.raises(ValidationError, match="applied_at"):
        ChangeRequest(
            path="acquisition.result.status",
            previous_value="running",
            proposed_value="completed",
            origin="user",
            proposer="operator",
            status="applied",
            approved_by="operator",
            approved_at=NOW,
        )

    request = ChangeRequest(
        path="acquisition.result.status",
        previous_value="running",
        proposed_value="completed",
        origin="user",
        proposer="operator",
        status="applied",
        approved_by="operator",
        approved_at=NOW,
        applied_at=NOW,
    )

    assert request.status == "applied"
    assert request.approval_bypassed is False


def test_bypassed_change_must_be_applied_trusted_workflow_change() -> None:
    with pytest.raises(ValidationError, match="trusted_workflow"):
        ChangeRequest(
            path="acquisition.result.status",
            previous_value="running",
            proposed_value="completed",
            origin="user",
            proposer="operator",
            status="applied",
            approval_bypassed=True,
            applied_at=NOW,
        )

    request = ChangeRequest(
        path="acquisition.result.status",
        previous_value="running",
        proposed_value="completed",
        origin="trusted_workflow",
        proposer="serval_workflow",
        status="applied",
        approval_bypassed=True,
        applied_at=NOW,
    )

    assert request.approval_bypassed is True
    assert request.approved_by is None


def test_failed_change_requires_failure_metadata() -> None:
    with pytest.raises(ValidationError, match="failure_reason and failed_at"):
        ChangeRequest(
            path="acquisition.result.status",
            previous_value="running",
            proposed_value="completed",
            origin="trusted_workflow",
            proposer="serval_workflow",
            status="failed",
        )

    request = ChangeRequest(
        path="acquisition.result.status",
        previous_value="running",
        proposed_value="completed",
        origin="trusted_workflow",
        proposer="serval_workflow",
        status="failed",
        failure_reason=" validation failed ",
        failed_at=NOW,
    )

    assert request.failure_reason == "validation failed"
    assert request.failed_at == NOW


def test_change_request_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra"):
        ChangeRequest(
            path="acquisition.result.status",
            previous_value="running",
            proposed_value="completed",
            origin="user",
            proposer="operator",
            state_dir="logs",
        )
