"""Synthetic transition tests: unsupported stage pairs and malformed holds fail closed."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from timmy.workflow_state_machine import validate_state_change
from timmy.conversation_workflow import save_state


def state(stage, *, pending=None, mapping_id=None, validation=None):
    return {"stage": stage, "scope": {"source_ids": ["synthetic-file"]},
            "pending": pending, "mapping_id": mapping_id,
            "validation": validation}


def test_expected_analyze_to_mapping_to_review():
    start = state("INTAKE_VERIFIED", pending="process")
    mapping = state("MAPPING_UNDER_REVIEW", pending="confirm_mapping", mapping_id="synthetic")
    running = state("VALIDATION_RUNNING", pending="confirm_mapping",
                    mapping_id="synthetic", validation={"status": "running"})
    review = state("HUMAN_REVIEW_REQUIRED", mapping_id="synthetic",
                   validation={"status": "completed"})
    validate_state_change(None, start)
    validate_state_change(start, mapping)
    validate_state_change(mapping, running)
    validate_state_change(running, review)


@pytest.mark.parametrize("origin,target", [
    ("INTAKE_VERIFIED", "VALIDATION_RUNNING"),
    ("VALIDATION_RUNNING", "INTAKE_VERIFIED"),
    ("MAPPING_UNDER_REVIEW", "VALIDATION_FAILED"),
    ("NOT_AN_APPROVED_STATE", "INTAKE_VERIFIED"),
])
def test_illegal_transitions_are_denied(origin, target):
    with pytest.raises(HTTPException) as e:
        validate_state_change(state(origin), state(target))
    assert e.value.status_code == 409


def test_review_cannot_silently_keep_confirmation_pending():
    with pytest.raises(HTTPException) as e:
        validate_state_change(state("MAPPING_UNDER_REVIEW"),
                              state("HUMAN_REVIEW_REQUIRED", pending="confirm_mapping"))
    assert e.value.detail == "CONVERSATION_REVIEW_STATE_INVALID"


def test_save_state_does_not_mutate_on_failed_transition():
    obj = SimpleNamespace(workflow_state=state("INTAKE_VERIFIED", pending="process"))
    with pytest.raises(HTTPException):
        save_state(obj, state("VALIDATION_FAILED", validation={"status":"failed"}))
    assert obj.workflow_state["stage"] == "INTAKE_VERIFIED"
