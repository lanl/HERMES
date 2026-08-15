"""Exceptions raised while preparing and running EMPIR programs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermes.runner.analysis.empir._process import EmpirProcessOutcome


class EmpirError(Exception):
    """Base exception for EMPIR analysis failures."""


class EmpirPreflightError(EmpirError):
    """Raised when an EMPIR process cannot safely start."""


class EmpirNotInstalledError(EmpirPreflightError):
    """Raised when EMPIR itself is not installed or not on PATH.

    HERMES can control EMPIR but does not ship or install it. When a config
    names an EMPIR program that is not on PATH, HERMES warns the user and exits
    rather than failing with a traceback.
    """


class EmpirExecutionError(EmpirError):
    """Raised when an EMPIR process cannot launch or exits with an error."""

    def __init__(self, message: str, outcome: EmpirProcessOutcome) -> None:
        super().__init__(message)
        self.outcome = outcome


class EmpirOutputError(EmpirExecutionError):
    """Raised when a successful EMPIR process leaves no requested file."""
