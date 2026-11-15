"""Fixed payment-policy families: project choice only, no per-project rule editing.

Session rules remain in the approved session-policy contract and deterministic
services. Hours-based rules are approved in docs/policies/fixed_hours_policy_contract_v1.0.md,
but source/identity/report/payment adapters remain separately gated.
Selecting 'hours' never creates a payable result.
The old payment_policies table is retained for historical references only.
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from .auth import Authenticated, Database
from .models import projects

router = APIRouter(prefix="/api/payment-policies")


@router.get("/{project_id}")
def selected_policy(project_id: int, principal: Authenticated, db: Database):
    principal.require("projects:read", project_id)
    row = db.execute(select(projects.c.policy_family).where(
        projects.c.id == project_id
    )).one_or_none()
    if row is None:
        raise HTTPException(404, "Project unavailable")
    family = row[0]
    return {
        "family": family,
        "configuration_editable": False,
        "status": ("unassigned_legacy" if family is None else
                   "fixed_hours_contract" if family == "hours" else
                   "fixed_session_contract"),
    }
