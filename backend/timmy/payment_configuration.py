"""Project policy versions and example arithmetic. No payable records are created here."""
from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_UP, localcontext
from time import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, insert, select, text, update

from .audit import audit
from .auth import Authenticated, Database, current_principal, require_csrf
from .models import payment_policies, projects

router = APIRouter(prefix="/api/payment-policies")
ROUNDING = {"down": ROUND_DOWN, "up": ROUND_UP, "half_up": ROUND_HALF_UP, "half_even": ROUND_HALF_EVEN}


class PolicyConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    family: Literal["hours", "session"]
    rate: Decimal = Field(gt=0, max_digits=14, decimal_places=6)
    currency: Literal["USD", "LBP"]
    start: date
    end: date | None = None
    precision: int = Field(ge=0, le=6)
    monetary_rounding: Literal["down", "up", "half_up", "half_even"]
    eligibility: Literal["approved_evidence_only"]
    duration_rounding: Literal["exact", "down", "up", "half_up"] | None = None
    increment_minutes: int | None = Field(default=None, ge=1, le=60)
    overnight: Literal["continuous", "reject"] | None = None
    daily_cap: int | None = Field(default=None, gt=0, le=1440)
    activity_cap: int | None = Field(default=None, gt=0, le=1000000)
    period_cap: int | None = Field(default=None, gt=0, le=1000000)
    period: Literal["calendar_month"] | None = None

    @model_validator(mode="after")
    def validate_rules(self):
        if self.end and self.end < self.start:
            raise ValueError("Expiration must be on or after the effective date")
        if bool(self.period_cap) != bool(self.period):
            raise ValueError("A period cap requires an explicit payment period")
        if self.family == "hours":
            if not self.duration_rounding or not self.overnight or self.daily_cap is None:
                raise ValueError("Hours require duration rounding, an overnight rule, and a daily cap")
            if (self.duration_rounding == "exact") == (self.increment_minutes is not None):
                raise ValueError("A rounding increment is required only for rounded durations")
        elif any(value is not None for value in (self.duration_rounding, self.increment_minutes, self.overnight, self.activity_cap)):
            raise ValueError("Hourly settings cannot be applied to a per-session policy")
        return self


def example_calculation(policy: PolicyConfiguration, raw_quantity: int):
    """One example line within one day, activity and period; never a payable result."""
    with localcontext() as ctx:
        ctx.prec = 40
        eligible = Decimal(raw_quantity)
        if policy.increment_minutes:
            increment = Decimal(policy.increment_minutes)
            eligible = (eligible / increment).quantize(Decimal(1), rounding=ROUNDING[policy.duration_rounding]) * increment
        for cap in (policy.daily_cap, policy.activity_cap, policy.period_cap):
            if cap is not None:
                eligible = min(eligible, Decimal(cap))
        divisor = 60 if policy.family == "hours" else 1
        quantum = Decimal(1).scaleb(-policy.precision)
        amount = (eligible * policy.rate / divisor).quantize(quantum, rounding=ROUNDING[policy.monetary_rounding])
        return {"raw_quantity": raw_quantity, "eligible_quantity": str(eligible), "amount": str(amount),
                "currency": policy.currency, "unit": "minutes" if divisor == 60 else "sessions"}


def save_draft(db, project_id, actor_id, policy):
    version = db.scalar(select(func.max(payment_policies.c.version)).where(payment_policies.c.project_id == project_id)) or 0
    identifier = db.execute(insert(payment_policies).values(project_id=project_id, version=version + 1,
                            configuration=policy.model_dump(mode="json"), created_by=actor_id,
                            created_at=int(time()))).inserted_primary_key[0]
    audit(db, "payment_policy_drafted", actor_id, resource_type="payment_policy", resource_id=str(identifier))
    return identifier


def policy_history(db, project_id):
    return [dict(row) for row in db.execute(select(payment_policies).where(
        payment_policies.c.project_id == project_id).order_by(payment_policies.c.version.desc())).mappings()]


def lock_manager(db, request, principal, project_id):
    require_csrf(request, principal)
    db.rollback()
    db.execute(text("BEGIN IMMEDIATE"))
    principal = current_principal(request, db)
    require_csrf(request, principal)
    principal.require("projects:manage")
    principal.require("projects:read", project_id)
    status = db.scalar(select(projects.c.status).where(projects.c.id == project_id))
    if status not in {"active", "draft"}:
        raise HTTPException(409, "Policy changes require an active or draft project")
    return principal


@router.get("/{project_id}")
def list_policies(project_id: int, principal: Authenticated, db: Database):
    principal.require("projects:read", project_id)
    return policy_history(db, project_id)


@router.post("/{project_id}", status_code=201)
def create_policy(project_id: int, policy: PolicyConfiguration, request: Request, principal: Authenticated, db: Database):
    principal = lock_manager(db, request, principal, project_id)
    identifier = save_draft(db, project_id, principal.user.id, policy)
    db.commit()
    return {"id": identifier}


class ActivatePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: Literal[True]
    supersede_policy_id: int | None = Field(default=None, gt=0)


@router.post("/{project_id}/{policy_id}/activate")
def activate(project_id: int, policy_id: int, body: ActivatePolicy, request: Request,
             principal: Authenticated, db: Database):
    principal = lock_manager(db, request, principal, project_id)
    history = policy_history(db, project_id)
    row = next((item for item in history if item["id"] == policy_id), None)
    if not row or not row["configuration"] or row["status"] != "draft":
        raise HTTPException(409, "Select a configured draft policy")
    proposed = PolicyConfiguration.model_validate(row["configuration"])
    replacement = next((item for item in history if item["id"] == body.supersede_policy_id
                        and item["status"] == "active"), None)
    if body.supersede_policy_id and not replacement:
        raise HTTPException(409, "Select an active policy in this project to supersede")
    for other in history:
        if other["status"] != "active" or other == replacement:
            continue
        active = PolicyConfiguration.model_validate(other["configuration"])
        if proposed.start <= (active.end or date.max) and active.start <= (proposed.end or date.max):
            raise HTTPException(409, "Effective dates overlap an active payment policy")
    if replacement:
        db.execute(update(payment_policies).where(payment_policies.c.id == replacement["id"])
                   .values(status="superseded"))
        audit(db, "payment_policy_superseded", principal.user.id, resource_type="payment_policy",
              resource_id=str(replacement["id"]))
    db.execute(update(payment_policies).where(payment_policies.c.id == policy_id)
               .values(status="active", activated_at=int(time()), activated_by=principal.user.id))
    audit(db, "payment_policy_activated", principal.user.id, resource_type="payment_policy", resource_id=str(policy_id))
    db.commit()
    return {"id": policy_id, "status": "active"}


@router.post("/{project_id}/example")
def preview_policy(project_id: int, policy: PolicyConfiguration, principal: Authenticated):
    principal.require("projects:read", project_id)
    return example_calculation(policy, 90 if policy.family == "hours" else 3)


@router.post("/{project_id}/{policy_id}/archive")
def archive(project_id: int, policy_id: int, body: ActivatePolicy, request: Request,
            principal: Authenticated, db: Database):
    principal = lock_manager(db, request, principal, project_id)
    if body.supersede_policy_id is not None:
        raise HTTPException(422, "Archiving does not replace a policy")
    changed = db.execute(update(payment_policies).where(
        payment_policies.c.id == policy_id, payment_policies.c.project_id == project_id,
        payment_policies.c.status.in_(("draft", "superseded")),
    ).values(status="archived"))
    if changed.rowcount != 1:
        raise HTTPException(409, "Only draft or superseded policies can be archived")
    audit(db, "payment_policy_archived", principal.user.id, resource_type="payment_policy", resource_id=str(policy_id))
    db.commit()
    return {"id": policy_id, "status": "archived"}
