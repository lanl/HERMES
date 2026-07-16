from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.state import HermesRecord
from hermes.state_service.change_requests import ChangeRequest
from hermes.state_service.state_logger import StateLogger


NOW = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)


class CapturingLogger:
    def __init__(
        self,
        events: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.events = events if events is not None else []
        self.context = context if context is not None else {}
        self.bind_calls: list[dict[str, Any]] = []

    def bind(self, **context: Any) -> CapturingLogger:
        self.bind_calls.append(context)
        return CapturingLogger(
            events=self.events,
            context={**self.context, **context},
        )

    def info(self, message: str, **fields: Any) -> None:
        self.events.append(
            {
                "level": "info",
                "message": message,
                "fields": {**self.context, **fields},
            }
        )

    def error(self, message: str, **fields: Any) -> None:
        self.events.append(
            {
                "level": "error",
                "message": message,
                "fields": {**self.context, **fields},
            }
        )

    def add(self, *_args: Any, **_kwargs: Any) -> None:
        msg = "StateLogger must not configure Loguru sinks"
        raise AssertionError(msg)


def _record(tmp_path: Path) -> HermesRecord:
    return HermesRecord(
        measurement_info=MeasurementInfo(
            measurement_id="LC-20260505",
            run_number=7,
        ),
        environment=RuntimeEnvironment(working_dir=tmp_path / "run-007"),
    )


def test_state_logger_binds_state_domain_and_context() -> None:
    logger = CapturingLogger()

    StateLogger(logger, run_id="run-007")

    assert logger.bind_calls == [{"domain": "state", "run_id": "run-007"}]
    assert logger.events == []


def test_state_logger_logs_initial_state_record(tmp_path: Path) -> None:
    logger = CapturingLogger()
    state_logger = StateLogger(logger, run_id="run-007")

    state_logger.log_initial_state(_record(tmp_path))

    event = logger.events[0]
    fields = event["fields"]
    assert event["level"] == "info"
    assert event["message"] == "state.initial_record"
    assert fields["domain"] == "state"
    assert fields["run_id"] == "run-007"
    assert fields["event_type"] == "state.initial_record"
    assert fields["measurement_id"] == "LC-20260505"
    assert fields["run_number"] == 7
    assert fields["record"]["measurement_info"]["measurement_id"] == "LC-20260505"


def test_state_logger_logs_state_load_and_save_events(tmp_path: Path) -> None:
    logger = CapturingLogger()
    state_logger = StateLogger(logger)
    record = _record(tmp_path)
    record_path = tmp_path / "run-007/logs/hermes-record.final.yaml"

    state_logger.log_state_loaded(record, record_path)
    state_logger.log_state_saved(record, record_path)

    loaded, saved = logger.events
    assert loaded["message"] == "state.loaded"
    assert loaded["fields"]["event_type"] == "state.loaded"
    assert loaded["fields"]["record_path"] == str(record_path)
    assert saved["message"] == "state.saved"
    assert saved["fields"]["event_type"] == "state.saved"
    assert saved["fields"]["record_path"] == str(record_path)


def test_state_logger_logs_change_with_value_summaries() -> None:
    logger = CapturingLogger()
    state_logger = StateLogger(logger)
    change = ChangeRequest(
        change_id="change-001",
        path="acquisition.result.status",
        previous_value="running",
        proposed_value="completed",
        origin="trusted_workflow",
        proposer="serval_workflow",
    )

    state_logger.log_change(change)

    fields = logger.events[0]["fields"]
    assert logger.events[0]["message"] == "state.change"
    assert fields["change_id"] == "change-001"
    assert fields["path"] == "acquisition.result.status"
    assert fields["status"] == "pending"
    assert fields["origin"] == "trusted_workflow"
    assert fields["proposer"] == "serval_workflow"
    assert fields["approval_bypassed"] is False
    assert fields["change"]["change_id"] == "change-001"
    assert fields["previous_value_summary"] == {
        "kind": "inline_scalar",
        "value": "running",
    }
    assert fields["proposed_value_summary"] == {
        "kind": "inline_scalar",
        "value": "completed",
    }


def test_state_logger_logs_rejected_and_failed_change_metadata() -> None:
    logger = CapturingLogger()
    state_logger = StateLogger(logger)
    rejected = ChangeRequest(
        change_id="change-rejected",
        path="acquisition.result.status",
        previous_value="running",
        proposed_value="failed",
        origin="ai",
        proposer="agent",
        status="rejected",
        rejected_by="operator",
        rejected_at=NOW,
        rejection_reason="not consistent with acquisition logs",
    )
    failed = ChangeRequest(
        change_id="change-failed",
        path="acquisition.result.frames",
        previous_value=0,
        proposed_value=-1,
        origin="trusted_workflow",
        proposer="serval_workflow",
        status="failed",
        failure_reason="frame count must be non-negative",
        failed_at=NOW,
    )

    state_logger.log_change(rejected)
    state_logger.log_change(failed)

    rejected_fields = logger.events[0]["fields"]
    failed_fields = logger.events[1]["fields"]
    assert rejected_fields["status"] == "rejected"
    assert rejected_fields["rejected_by"] == "operator"
    assert rejected_fields["rejection_reason"] == (
        "not consistent with acquisition logs"
    )
    assert failed_fields["status"] == "failed"
    assert failed_fields["failure_reason"] == "frame count must be non-negative"


def test_state_logger_summarizes_external_payload_refs() -> None:
    logger = CapturingLogger()
    state_logger = StateLogger(logger)
    payload_ref = {
        "kind": "external_payload_ref",
        "path": "logs/payloads/detector_dacs_abc123.json",
        "media_type": "application/json",
        "sha256": "a" * 64,
        "size_bytes": 128,
        "created_at": "2026-05-05T12:00:00Z",
    }
    change = ChangeRequest(
        change_id="change-002",
        path="acquisition.applied_detector_config.dacs",
        previous_value=None,
        proposed_value=payload_ref,
        origin="trusted_workflow",
        proposer="serval_workflow",
        status="applied",
        approval_bypassed=True,
        applied_at=NOW,
    )

    state_logger.log_change(change)

    assert logger.events[0]["fields"]["proposed_value_summary"] == {
        "kind": "external_payload_ref",
        "path": "logs/payloads/detector_dacs_abc123.json",
        "media_type": "application/json",
        "sha256": "a" * 64,
        "size_bytes": 128,
    }


def test_state_logger_logs_validation_failure() -> None:
    logger = CapturingLogger()
    state_logger = StateLogger(logger)

    state_logger.log_validation_failure(
        "acquisition.result.status",
        "invalid status",
        change_id="change-003",
        proposed_value={"status": "bad"},
    )

    event = logger.events[0]
    fields = event["fields"]
    assert event["level"] == "error"
    assert event["message"] == "state.validation_failed"
    assert fields["event_type"] == "state.validation_failed"
    assert fields["change_id"] == "change-003"
    assert fields["path"] == "acquisition.result.status"
    assert fields["error"] == "invalid status"
    assert fields["proposed_value_summary"] == {
        "kind": "inline_mapping",
        "size": 1,
        "keys": ["status"],
    }
