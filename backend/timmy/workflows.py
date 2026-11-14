"""Knowledge-driven workflow selection and durable, capability-honest execution.

A workflow is a server-owned ordered procedure. The model chooses its ID, never
supplies code, permissions or financial authority. Unimplemented adapters block.
"""
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from time import time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text

from .audit import audit
from .auth import Authenticated, Database, current_principal, require_csrf
from .documents import project_report_cutoffs, resolve_documents
from .models import WorkflowRun, projects
from .session_preview import preview

WorkflowID = Literal['analyze_intake', 'process_activity', 'weekly_cycle', 'payment_return',
                     'prepare_payment', 'show_issues', 'resolve_issues']


class Definition(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: WorkflowID
    label: str
    trigger_pattern: str
    instructions: str
    steps: list[str] = Field(min_length=1)


class Knowledge(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    version: str
    system: str
    workflows: list[Definition]

    @model_validator(mode='after')
    def unique(self):
        if len({w.id for w in self.workflows}) != len(self.workflows):
            raise ValueError('Duplicate workflow')
        for item in self.workflows:
            re.compile(item.trigger_pattern)
        return self


@lru_cache(maxsize=1)
def knowledge():
    return Knowledge.model_validate_json(Path(__file__).with_name('workflow_knowledge.json').read_bytes())


def choose_workflow(message):
    """Conservative shortcuts; uncertain language is clarified or model-proposed."""
    # Never infer a write from quoted material, negation or a hypothetical.
    if re.search(r"\b(don't|do not|never|not yet|if|suppose)\b|[\"`]|لا تعالج|لا ترسل", message, re.I):
        read = next(w for w in knowledge().workflows if w.id == 'show_issues')
        return 'show_issues' if re.search(read.trigger_pattern, message, re.I) else 'clarify'
    if re.search(r'\bprocess payments?\b', message, re.I):
        return 'clarify'
    matches = [w.id for w in knowledge().workflows if re.search(w.trigger_pattern, message, re.I)]
    if len(matches) > 1:
        return 'clarify'
    return matches[0] if matches else None


def clarification():
    return ('What would you like me to do?\n'
            '1. Analyze: import/store files, then offer processing.\n'
            '2. Process: check activity reports and flag discrepancies.\n'
            '3. Prepare a payment request for approval and file export.\n'
            '4. Reconcile a returned payment report.\n'
            'Reply with the action name; no step-by-step instructions are needed.')


def step_result(step, status, issues=(), **data):
    return dict(step=step, status=status, issue_codes=list(issues), **data)


def run_workflow(db, principal, config, *, workflow_id, project_id, request_key,
                 conversation_id=None, document_ids=(), prepared_documents=None, mapping_ref=None, structural_snapshot=None):
    """Shared entry for chat and authenticated weekly/event automation.

    The caller owns the transaction. No delivery provider, approval or external
    financial state can be supplied by a chat message. Retries with new evidence
    require a new run key; exact replay is read-only and rechecks current scope.
    """
    definitions = {w.id: w for w in knowledge().workflows}
    if workflow_id not in definitions:
        raise HTTPException(422, 'Unknown stored workflow')
    principal.require('timesheets.view', project_id)
    if workflow_id != 'show_issues':
        principal.require('projects:manage')
    if db.scalar(select(projects.c.status).where(projects.c.id == project_id)) != 'active':
        raise HTTPException(409, 'Select an active project')
    documents = resolve_documents(db, principal, conversation_id, project_id, document_ids)
    # Validate original bytes before trusting cached parsed claims.
    damaged = False
    for file, _ in documents:
        try:
            data = (config.document_root.expanduser() / file.id).read_bytes()
            damaged |= len(data) != file.size_bytes or sha256(data).hexdigest() != file.sha256
        except OSError:
            damaged = True
    project_code = db.scalar(select(projects.c.project_code).where(projects.c.id == project_id))
    cutoffs = project_report_cutoffs(db, project_id)
    signature = dict(workflow=workflow_id, version=knowledge().model_dump(), project=project_id,
                     conversation=conversation_id, selected=sorted(str(x) for x in document_ids),
                     documents=sorted((f.id, f.sha256) for f, _ in documents), cutoffs=[[list(key), value] for key, value in sorted(cutoffs.items())], mapping_ref=mapping_ref)
    if workflow_id != "analyze_intake":
        signature["project_code_scope"] = project_code
    fingerprint = sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    previous = db.scalar(select(WorkflowRun).where(WorkflowRun.actor_id == principal.user.id,
                                                  WorkflowRun.request_key == request_key))
    if previous:
        if previous.fingerprint != fingerprint:
            raise HTTPException(409, 'Run key already used with different scope or evidence')
        if damaged:
            raise HTTPException(409, 'Stored evidence failed integrity verification')
        return previous
    if workflow_id == 'analyze_intake' and not damaged:
        # A new chat UUID does not constitute new imported evidence.
        existing = db.scalar(select(WorkflowRun).where(
            WorkflowRun.actor_id == principal.user.id, WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.fingerprint == fingerprint).order_by(WorkflowRun.id.desc()).limit(1))
        if existing:
            return existing
    snapshot = {'claims': [], 'activities': []} if structural_snapshot is None else structural_snapshot
    result_text = preview(prepared_documents if prepared_documents is not None else documents,
                          snapshot=snapshot, report_cutoffs=cutoffs,
                          project_codes={project_id: project_code}) if not damaged else None
    activities = snapshot['activities']
    results = []
    # All plans are loaded from knowledge. Known steps have explicit implementations;
    # missing adapters never fall through to successful or financial execution.
    for step in definitions[workflow_id].steps:
        if damaged:
            result = step_result(step, 'blocked', ['SOURCE_INTEGRITY_FAILED'])
        elif not documents:
            result = step_result(step, 'blocked', ['NO_VISIBLE_DOCUMENTS'])
        elif step == 'verify_intake':
            result = step_result(step, 'completed', files=len(documents),
                                 source_rows=sum(r.row_count for _, r in documents))
        elif step == 'check_planning':
            result = step_result(step, 'needs_review', ['PLANNING_AUTHORITY_REQUIRED'],
                                 activities=len(activities))
        elif step == 'check_reports':
            missing = any((project_id, a['project_code'], a['activity_code']) not in cutoffs for a in activities)
            result = step_result(step, 'blocked' if missing or not activities else 'completed',
                                 ['REPORT_VALIDATION_EVIDENCE_REQUIRED'] if missing or not activities else [],
                                 frozen_reports=len(cutoffs))
        elif step == 'select_timesheets':
            result = step_result(step, 'needs_review', ['APPROVED_PLANNED_REPORTED_SELECTION_REQUIRED'],
                                 candidate_claims=len(snapshot['claims']))
        elif step in {'validate_activity', 'show_discrepancies'}:
            codes = sorted({code for activity in activities for code in activity['issues']})
            result = step_result(step, 'completed' if step == 'show_discrepancies' else 'needs_review',
                                 [] if step == 'show_discrepancies' else ['AUTHORITATIVE_VALIDATION_ADAPTER_REQUIRED'],
                                 activities=activities, structural_issue_codes=codes)
        elif step == 'resolve_discrepancies':
            result = step_result(step, 'needs_review', ['POLICY_RESOLUTION_ADAPTER_REQUIRED'],
                                 recommendation='Review the recorded rule and source evidence. Apply only an explicitly policy-authorized correction; otherwise request an authorized human decision.')
        else:
            blockers = {
                'prepare_payment_request': ['ELIGIBLE_CREDIT_ADAPTER_REQUIRED', 'EXACT_BATCH_APPROVAL_REQUIRED'],
                'export_payment_request': ['APPROVED_PAYMENT_REQUEST_FILE_ADAPTER_REQUIRED', 'EXACT_BATCH_APPROVAL_REQUIRED'],
                'receive_payment_report': ['TRUSTED_PAYMENT_REPORT_ADAPTER_REQUIRED'],
                'reconcile_payments': ['PAYMENT_RECONCILIATION_ADAPTER_REQUIRED'],
                'map_payments': ['VERIFIED_BATCH_MAPPING_REQUIRED'],
                'archive_payment_evidence': ['RECONCILED_EVIDENCE_ARCHIVE_REQUIRED'],
                'raise_payment_issues': ['PAYMENT_ISSUE_ADAPTER_REQUIRED'],
            }
            result = step_result(step, 'blocked', blockers.get(step, ['UNREGISTERED_WORKFLOW_STEP']))
        results.append(result)
    status = ('blocked' if any(r['status'] == 'blocked' for r in results) else
              'needs_review' if any(r['status'] == 'needs_review' for r in results) else 'completed')
    run = WorkflowRun(actor_id=principal.user.id, project_id=project_id, request_key=request_key,
                      fingerprint=fingerprint, workflow_id=workflow_id, knowledge_version=knowledge().version,
                      created_at=int(time()), status=status,
                      snapshot={'steps': results, 'source_ids': [f.id for f, _ in documents], 'mapping_ref': mapping_ref,
                                'execution': {'mode': 'synchronous', 'completed_at': datetime.now(timezone.utc).isoformat()},
                                'preview': result_text if workflow_id in {'process_activity', 'show_issues'} else None})
    db.add(run)
    db.flush()
    audit(db, 'workflow_run_recorded', principal.user.id, resource_type='workflow_run',
          resource_id=str(run.id), outcome=status, trigger=workflow_id)
    return run


def render_run(run):
    label = next(w.label for w in knowledge().workflows if w.id == run.workflow_id)
    lines = [f'{label}: {run.status.replace("_", " ")} (run #{run.id}).']
    for item in run.snapshot['steps']:
        lines.append(f"- {item['step'].replace('_', ' ')}: {item['status'].replace('_', ' ')}"
                     + (f" — {', '.join(item['issue_codes'])}" if item['issue_codes'] else ''))
        if 'recommendation' in item:
            lines.append(item['recommendation'])
        if item['step'] == 'verify_intake' and item['status'] == 'completed':
            lines.append(f"Stored evidence verified: {item['files']} files, {item['source_rows']} source rows. Process these against the activity reports next?")
    if run.snapshot.get('preview'):
        lines.append(run.snapshot['preview'])
    if run.workflow_id == 'weekly_cycle':
        lines.append('Each step is recorded in the stored order. Blocked prerequisites have not been bypassed; no payment request file was exported.')
    return '\n'.join(lines)


router = APIRouter(prefix='/api/workflows')


class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    workflow_id: WorkflowID
    project_id: int = Field(gt=0)


@router.post('/runs', status_code=201)
def start(payload: RunRequest, request: Request, principal: Authenticated, db: Database):
    require_csrf(request, principal)
    db.rollback()
    db.execute(text('BEGIN IMMEDIATE'))
    principal = current_principal(request, db)
    require_csrf(request, principal)
    run = run_workflow(db, principal, request.app.state.config, workflow_id=payload.workflow_id,
                       project_id=payload.project_id, request_key=f'api:{payload.request_id}')
    db.commit()
    return {'id': run.id, 'status': run.status, 'steps': run.snapshot['steps']}


@router.get('/last-run/{project_id}')
def last_run(project_id: int, principal: Authenticated, db: Database, workflow_id: WorkflowID | None = None):
    principal.require('timesheets.view', project_id)
    query = select(WorkflowRun).where(WorkflowRun.actor_id == principal.user.id, WorkflowRun.project_id == project_id)
    if workflow_id:
        query = query.where(WorkflowRun.workflow_id == workflow_id)
    run = db.scalar(query.order_by(WorkflowRun.id.desc()).limit(1))
    if not run:
        return None
    return {'id': run.id, 'workflow_id': run.workflow_id, 'status': run.status,
            'recorded_at': datetime.fromtimestamp(run.created_at, timezone.utc).isoformat(),
            'knowledge_version': run.knowledge_version}
