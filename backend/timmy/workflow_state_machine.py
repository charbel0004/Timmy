"""Explicit, fail-closed transitions for the existing conversation workflow.

No new business approvals are authorized here. The state validator controls
only persisted conversation progression; source/role/finance authority remains
with existing backend services. Unknown stages never silently advance.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

STAGES = frozenset({
    "FILES_RECEIVED", "INTAKE_VERIFIED", "MAPPING_UNDER_REVIEW",
    "VALIDATION_RUNNING", "HUMAN_REVIEW_REQUIRED", "VALIDATION_FAILED",
})

ALLOWED = {
    None: frozenset({"INTAKE_VERIFIED", "MAPPING_UNDER_REVIEW"}),
    "FILES_RECEIVED": frozenset({"INTAKE_VERIFIED", "MAPPING_UNDER_REVIEW"}),
    "INTAKE_VERIFIED": frozenset({"INTAKE_VERIFIED", "MAPPING_UNDER_REVIEW"}),
    "MAPPING_UNDER_REVIEW": frozenset({
        "MAPPING_UNDER_REVIEW", "VALIDATION_RUNNING", "HUMAN_REVIEW_REQUIRED",
        "INTAKE_VERIFIED",
    }),
    "VALIDATION_RUNNING": frozenset({
        "HUMAN_REVIEW_REQUIRED", "VALIDATION_FAILED",
    }),
    "HUMAN_REVIEW_REQUIRED": frozenset({
        "HUMAN_REVIEW_REQUIRED", "VALIDATION_RUNNING", "MAPPING_UNDER_REVIEW",
        "INTAKE_VERIFIED",
    }),
    "VALIDATION_FAILED": frozenset({
        "VALIDATION_FAILED", "MAPPING_UNDER_REVIEW", "VALIDATION_RUNNING",
        "INTAKE_VERIFIED",
    }),
}


def validate_state_change(previous: dict[str, Any] | None,
                          proposed: dict[str, Any]) -> None:
    """Validate a proposed saved state without mutating its source evidence."""
    source = (previous or {}).get("stage")
    target = proposed.get("stage")
    if source not in ALLOWED or target not in STAGES or target not in ALLOWED[source]:
        raise HTTPException(409, "CONVERSATION_TRANSITION_DENIED")
    if not isinstance(proposed.get("scope"), dict) or not proposed["scope"].get("source_ids"):
        raise HTTPException(409, "CONVERSATION_SCOPE_REQUIRED")
    if target == "INTAKE_VERIFIED":
        if proposed.get("pending") != "process" or proposed.get("mapping_id") is not None:
            raise HTTPException(409, "CONVERSATION_STATE_INCONSISTENT")
    elif target == "MAPPING_UNDER_REVIEW":
        if proposed.get("pending") != "confirm_mapping" or not proposed.get("mapping_id"):
            raise HTTPException(409, "CONVERSATION_MAPPING_REQUIRED")
    elif target == "VALIDATION_RUNNING":
        if not proposed.get("mapping_id") or (proposed.get("validation") or {}).get("status") != "running":
            raise HTTPException(409, "CONVERSATION_VALIDATION_STATE_INVALID")
    elif target == "VALIDATION_FAILED":
        if proposed.get("pending") is not None or (proposed.get("validation") or {}).get("status") != "failed":
            raise HTTPException(409, "CONVERSATION_VALIDATION_STATE_INVALID")
    elif target == "HUMAN_REVIEW_REQUIRED":
        if proposed.get("pending") is not None:
            raise HTTPException(409, "CONVERSATION_REVIEW_STATE_INVALID")
