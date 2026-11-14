"""Read-only, scoped views of the isolated workbook demonstration."""
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from .auth import Authenticated, Database
from .models import WorkflowRun, projects

router = APIRouter(prefix="/api/demo-workbook")


def records(db, principal):
    ids = [pid for pid, permissions in principal.project_permissions.items()
           if {"timesheets.view", "payments.view"} <= set(permissions)]
    rows = db.execute(select(WorkflowRun, projects.c.name).join(
        projects, WorkflowRun.project_id == projects.c.id).where(
        WorkflowRun.project_id.in_(ids), WorkflowRun.workflow_id == "demo_workbook"
    ).order_by(WorkflowRun.id))
    return [{"project_id": run.project_id, "name": name, "status": run.status,
             **{key: run.snapshot[key] for key in ("results", "obligations", "reconciliation")}}
            for run, name in rows if run.snapshot.get("environment") == "DEMO"]


def summary(records):
    totals = {}
    for row in records:
        for reference, obligation in row["obligations"].items():
            currency = obligation["currency"]
            entry = totals.setdefault(currency, dict(calculated=Decimal(0), net=Decimal(0),
                                                     outstanding=Decimal(0), overpaid=Decimal(0)))
            entry["calculated"] += Decimal(obligation["amount"])
            if reconciled := row["reconciliation"].get(reference):
                entry["net"] += Decimal(reconciled["net"])
                balance = Decimal(reconciled["balance"])
                entry["outstanding"] += max(Decimal(0), balance)
                entry["overpaid"] += max(Decimal(0), -balance)
    return {currency: {key: str(value) for key, value in entry.items()} for currency, entry in totals.items()}


@router.get("")
def get_demo(request: Request, principal: Authenticated, db: Database):
    if not request.app.state.config.demo_mode:
        raise HTTPException(404, "Demo workbook unavailable")
    rows = records(db, principal)
    return {"projects": rows, "totals": summary(rows)}
