"""Monday 04:00 Asia/Beirut; explicit identity/scope and once-per-week receipts."""
import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .auth import principal_for
from .models import Role, User, WorkflowRun
from .workflows import run_workflow

logger = logging.getLogger(__name__)


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
                logger.warning('Weekly project %s blocked (HTTP %s)', project_id, error.status_code)
    return recorded


async def scheduler_loop(engine, config):
    while True:
        try:
            await asyncio.to_thread(run_due, engine, config)
        except Exception:
            # Keep the scheduler alive without logging evidence/credential values.
            logger.error('Weekly workflow check failed; inspect run receipts and configuration')
        await asyncio.sleep(30)
