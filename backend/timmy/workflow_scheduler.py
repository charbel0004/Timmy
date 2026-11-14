"""Monday 04:00 Asia/Beirut; explicit identity/scope and once-per-week receipts."""
import asyncio
import logging
from hashlib import sha256
from time import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .auth import principal_for
from .models import Role, User, WorkflowRun
from .audit import audit
from .workflows import run_workflow, knowledge

logger = logging.getLogger(__name__)


def persist_failed_attempt(db, *, actor_id: int, project_id: int,
                           request_key: str, code: str, status: str) -> None:
    """Persist a failed schedule key so the next poll cannot retry its handler.

    The original workflow transaction MUST be rolled back before this call.
    Store only safe codes; never serialize exception messages or source rows.
    """
    db.execute(text("BEGIN IMMEDIATE"))
    existing = db.scalar(select(WorkflowRun.id).where(
        WorkflowRun.actor_id == actor_id, WorkflowRun.request_key == request_key))
    if existing is not None:
        return
    marker = WorkflowRun(
        actor_id=actor_id, project_id=project_id, request_key=request_key,
        fingerprint=sha256(request_key.encode()).hexdigest(),
        workflow_id="weekly_cycle", knowledge_version=knowledge().version,
        created_at=int(time()), status=status,
        snapshot={"source_ids": [], "steps": [{
            "step": "scheduler_preflight", "status": status,
            "issue_codes": [code], "attempted": True, "executed": False,
        }], "execution": {"mode": "scheduled", "attempt_status": "operator_required"}},
    )
    db.add(marker)
    db.flush()
    audit(db, "scheduled_workflow_failed", actor_id,
          resource_type="workflow_run", resource_id=str(marker.id), outcome=status,
          trigger="weekly_cycle")
    db.commit()


def run_due(engine, config, now=None):
    if not config.weekly_enabled:
        return []
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo('Asia/Beirut'))
    # A restart later on Monday catches up; never repeat a recorded weekly run.
    if local.weekday() != 0 or local.hour < 4:
        return []
    year, week, _ = local.isocalendar()
    recorded = []
    actor_id = config.weekly_actor_id
    if actor_id is None or not config.weekly_project_ids:
        logger.warning("Weekly run requires an explicit actor and project list")
        return []
    for project_id in sorted(set(config.weekly_project_ids)):
        with Session(engine) as db:
            db.execute(text('BEGIN IMMEDIATE'))
            user = db.get(User, actor_id)
            role = db.get(Role, user.role_id) if user and user.active else None
            if not role or user.must_change_password:
                logger.warning('Weekly run disabled: configured actor unavailable')
                break
            principal = principal_for(db, user, role.name, None)
            key = f'weekly:{year}-W{week:02}:{project_id}'
            try:
                principal.require('projects:manage')
                principal.require('timesheets.view', project_id)
                existing = db.scalar(select(WorkflowRun.id).where(
                    WorkflowRun.actor_id == user.id, WorkflowRun.request_key == key))
                if existing:
                    continue
                run = run_workflow(db, principal, config, workflow_id='weekly_cycle',
                                   project_id=project_id, request_key=key)
                db.commit()
                recorded.append(run.id)
            except HTTPException as error:
                db.rollback()
                persist_failed_attempt(db, actor_id=user.id, project_id=project_id,
                                       request_key=key, code=f'SCHEDULED_HTTP_{error.status_code}',
                                       status='blocked')
                logger.warning('Weekly project %s stopped (HTTP %s); manual review required',
                               project_id, error.status_code)
            except Exception as error:
                db.rollback()
                persist_failed_attempt(db, actor_id=user.id, project_id=project_id,
                                       request_key=key, code='SCHEDULED_EXECUTION_FAILED',
                                       status='failed')
                logger.error('Weekly project %s stopped; error_type=%s; manual review required',
                             project_id, type(error).__name__)
    return recorded


async def scheduler_loop(engine, config):
    while True:
        try:
            await asyncio.to_thread(run_due, engine, config)
        except Exception as error:
            # Without durable DB receipts, retrying on the next poll is unsafe.
            # Halt this scheduler process until operator inspection/restart.
            logger.error('Weekly scheduler halted; error_type=%s; manual intervention required',
                         type(error).__name__)
            return
        await asyncio.sleep(30)
