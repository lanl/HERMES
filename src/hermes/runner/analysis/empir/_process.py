"""Shared EMPIR-only subprocess timing and output checks."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter

from hermes.runner.analysis.empir._errors import (
    EmpirExecutionError,
    EmpirOutputError,
    EmpirPreflightError,
)
from hermes.state.models.shared_models import utc_now

_LOG_TEXT_LIMIT = 4_000


@dataclass(frozen=True, slots=True)
class EmpirProcessOutcome:
    """Measured process details used for results, logs, and failures."""

    started_at: datetime
    completed_at: datetime
    elapsed_seconds: float
    exit_code: int | None
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""


def validate_step_paths(
    step_name: str,
    input_paths: list[Path],
    requested_output_path: Path,
) -> None:
    """Check immediate inputs and reject an existing requested output."""
    for input_path in input_paths:
        if not input_path.is_file():
            raise EmpirPreflightError(
                f"{step_name} input is not a regular file: {input_path}"
            )
    if requested_output_path.exists():
        raise EmpirPreflightError(
            f"{step_name} output already exists: {requested_output_path}"
        )


def run_process(
    step_name: str,
    command: list[str],
    requested_output_path: Path,
    started_at: datetime,
) -> EmpirProcessOutcome:
    """Run one EMPIR command, measure it, and verify its requested file."""
    started = perf_counter()
    try:
        process = subprocess.run(
            command,
            shell=False,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        outcome = EmpirProcessOutcome(
            started_at=started_at,
            completed_at=utc_now(),
            elapsed_seconds=perf_counter() - started,
            exit_code=None,
        )
        raise EmpirExecutionError(
            f"{step_name} failed to launch: {exc}", outcome
        ) from exc

    outcome = EmpirProcessOutcome(
        started_at=started_at,
        completed_at=utc_now(),
        elapsed_seconds=perf_counter() - started,
        exit_code=process.returncode,
        stdout_excerpt=_bounded_text(process.stdout),
        stderr_excerpt=_bounded_text(process.stderr),
    )
    if process.returncode != 0:
        raise EmpirExecutionError(
            f"{step_name} exited with code {process.returncode}", outcome
        )
    if not requested_output_path.is_file():
        raise EmpirOutputError(
            f"{step_name} did not create the requested output file: "
            f"{requested_output_path}",
            outcome,
        )

    return outcome


def _bounded_text(text: str) -> str:
    """Return at most the first 4,000 characters of process text."""
    return text[:_LOG_TEXT_LIMIT]
