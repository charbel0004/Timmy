"""Safe diagnostic codes for workflow failures.

This classifier never returns exception messages: they may contain source rows,
private staff IDs, destinations or credentials. References are opaque and are
used to correlate errors with controlled operational logs.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError


@dataclass(frozen=True)
class Diagnostic:
    code: str
    correlation_id: str
    exception_type: str


def classify(error: Exception, *, step: str) -> Diagnostic:
    """Classify a failed handler without serializing private exception data."""
    if not step or not step.replace('_', '').isalnum() or step != step.upper():
        raise ValueError("Diagnostic step must be an uppercase identifier")
    if isinstance(error, HTTPException):
        suffix = f"HTTP_{error.status_code}"
    elif isinstance(error, SQLAlchemyError):
        suffix = "DATABASE_ERROR"
    elif isinstance(error, OSError):
        suffix = "STORAGE_ERROR"
    elif isinstance(error, (ValueError, TypeError)):
        suffix = "INPUT_ERROR"
    else:
        suffix = "UNEXPECTED_ERROR"
    return Diagnostic(
        code=f"{step}_{suffix}",
        correlation_id=str(uuid4()),
        exception_type=type(error).__name__,
    )
