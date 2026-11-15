"""Knowledge-driven workflow selection and durable, capability-honest execution.

A workflow is a server-owned ordered procedure. The model chooses its ID, never
supplies code, permissions or financial authority. Unimplemented adapters block.
"""
from .observability import instrument

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
from .models import WorkflowRun, WorkflowStepReceipt, StoredFile, projects
from .session_preview import preview
from .workflow_graph import execute_graph

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
    if (re.search(r'\bprocess\b', message, re.I) and re.search(r'\bpayment request\b', message, re.I)):
        return 'weekly_cycle'
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
    # A successful service outcome is the only case marked executed.
    # A failed guard is attempted but must not be presented as an action.
    return dict(step=step, status=status, issue_codes=list(issues),
                attempted=True, executed=status == 'completed', **data)


@instrument("workflow.run", "internal_tool")
def run_workflow(db, principal, config, *, workflow_id, project_id, request_key,
                 conversation_id=None, document_ids=(), prepared_documents=None, mapping_ref=None,
                 structural_snapshot=None, payment_return_file_id=None):
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
    if payment_return_file_id is not None and workflow_id != 'payment_return':
        raise HTTPException(422, 'Payment-return evidence cannot be used for another workflow')
    payment_file = None
    if payment_return_file_id is not None:
        principal.require('payments.view', project_id)
        payment_file = db.get(StoredFile, str(payment_return_file_id))
        if (payment_file is None or payment_file.project_id != project_id
                or payment_file.purpose != 'payment_return'):
            raise HTTPException(404, 'Payment return unavailable')
    # Payment-return evidence never enters ordinary timesheet selection.
    documents = ([] if workflow_id == 'payment_return'
                 else resolve_documents(db, principal, conversation_id, project_id, document_ids))
    # Validate original bytes before trusting cached parsed claims.
    damaged = False
    for file, _ in documents:
        try:
            data = (config.document_root.expanduser() / file.id).read_bytes()
            damaged |= len(data) != file.size_bytes or sha256(data).hexdigest() != file.sha256
        except OSError:
            damaged = True
    # A request-key replay is checked BEFORE any planning source registration.
    # The existing input fingerprint is still recomputed below; preflight changes
    # on a replay are confined to a rolled-back SQLite savepoint.
    previous = db.scalar(select(WorkflowRun).where(
        WorkflowRun.actor_id == principal.user.id, WorkflowRun.request_key == request_key))
    if payment_file is not None:
        try:
            raw = (config.document_root.expanduser() / payment_file.id).read_bytes()
            if len(raw) != payment_file.size_bytes or sha256(raw).hexdigest() != payment_file.sha256:
                damaged = True
        except OSError:
            damaged = True
    planning_receipts=[]
    preflight_issues=[]
    if prepared_documents is None and not damaged and documents and workflow_id in {'weekly_cycle','process_activity'}:
        from .column_mappings import propose_sheet, reuse_approved_formats, mapped_documents
        from .planning_activities import register_planning
        candidates=[propose_sheet(file,sheet,index) for file,record in documents for index,sheet in enumerate(record.sheets)]
        accepted=reuse_approved_formats(db,principal.user.id,project_id,candidates)
        if not accepted:
            preflight_issues=['MAPPING_CONFIRMATION_REQUIRED']
        else:
            try:
                with db.begin_nested() as savepoint:
                    prepared_documents,planning_receipts=register_planning(db,principal,
                        mapped_documents(documents,accepted),accepted,None)
                    if previous is not None:
                        # Replay cannot register planning rows or audit changes.
                        savepoint.rollback()
                mapping_ref='formats:'+sha256(json.dumps(sorted({s['verified_format_ref'] for s in accepted})).encode()).hexdigest()
            except HTTPException as error:
                preflight_issues=['PLANNING_REGISTRATION_BLOCKED: '+str(error.detail)]
    cutoffs = project_report_cutoffs(db, project_id)
    from .planning_activities import registry
    activity_registry = registry(db, [project_id])
    project_codes = dict(db.execute(select(projects.c.id, projects.c.project_code).where(projects.c.id == project_id)).all())
    signature = dict(workflow=workflow_id, version=knowledge().model_dump(), project=project_id,
                     conversation=conversation_id, selected=sorted(str(x) for x in document_ids),
                     documents=sorted((f.id, f.sha256) for f, _ in documents), cutoffs=[[list(key), value] for key, value in sorted(cutoffs.items())], mapping_ref=mapping_ref,
                     activity_registry=[[list(key), value] for key,value in sorted(activity_registry.items())],
                     preflight_issues=preflight_issues,
                     payment_return_source=([payment_file.id, payment_file.sha256] if payment_file else None))
    if workflow_id != 'analyze_intake':
        signature['project_code_scope'] = project_codes.get(project_id)
    fingerprint = sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
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
                          snapshot=snapshot, report_cutoffs=cutoffs, activity_registry=activity_registry,
                          project_codes=project_codes) if not damaged else None
    activities = snapshot['activities']
    # LangGraph orchestrates reviewed backend handlers; it does not implement
    # business policies, invent unavailable adapters, or invoke downstream steps.
    def evaluate(step):
        if damaged:
            return step_result(step, 'blocked', ['SOURCE_INTEGRITY_FAILED'])
        if not documents and workflow_id not in {'payment_return','prepare_payment','resolve_issues','show_issues'}:
            return step_result(step, 'blocked', ['NO_VISIBLE_DOCUMENTS'])
        if preflight_issues:
            return step_result(step, 'blocked', preflight_issues)
        if step == 'receive_payment_report':
            if payment_file is None:
                return step_result(step, 'needs_review', ['PAYMENT_REPORT_SUBMISSION_REQUIRED'])
            return step_result(step, 'completed', report_file_id=payment_file.id,
                               report_sha256=payment_file.sha256,
                               authority='UNVERIFIED_UPLOAD_ONLY')
        if step == 'verify_intake':
            return step_result(step, 'completed', files=len(documents),
                               source_rows=sum(record.row_count for _, record in documents))
        if step == 'check_planning':
            return step_result(step, 'needs_review', ['PLANNING_AUTHORITY_REQUIRED'],
                               activities=len(activities))
        if step == 'check_reports':
            missing = any((project_id, a['project_code'], a['activity_code']) not in cutoffs for a in activities)
            return step_result(step, 'blocked' if missing or not activities else 'completed',
                               ['REPORT_VALIDATION_EVIDENCE_REQUIRED'] if missing or not activities else [],
                               frozen_reports=len(cutoffs))
        if step == 'select_timesheets':
            return step_result(step, 'needs_review', ['APPROVED_PLANNED_REPORTED_SELECTION_REQUIRED'],
                               candidate_claims=len(snapshot['claims']))
        if step in {'validate_activity', 'show_discrepancies'}:
            codes = sorted({code for activity in activities for code in activity['issues']})
            return step_result(step, 'completed' if step == 'show_discrepancies' else 'needs_review',
                               [] if step == 'show_discrepancies' else ['AUTHORITATIVE_VALIDATION_ADAPTER_REQUIRED'],
                               activities=activities, structural_issue_codes=codes,
                               evidence_kind='provisional_structural_preview')
        if step == 'resolve_discrepancies':
            return step_result(step, 'needs_review', ['POLICY_RESOLUTION_ADAPTER_REQUIRED'],
                               recommendation='Review the recorded rule and source evidence. Apply only an explicitly policy-authorized correction; otherwise request an authorized human decision.')
        # No handler exists for payment authority or settlement. Their catalog
        # entries are *not* automatically executable LangGraph tools.
        blockers = {
            'prepare_payment_request': ['ELIGIBLE_CREDIT_ADAPTER_REQUIRED', 'EXACT_BATCH_APPROVAL_REQUIRED'],
            'export_payment_request': ['APPROVED_PAYMENT_REQUEST_FILE_ADAPTER_REQUIRED', 'EXACT_BATCH_APPROVAL_REQUIRED'],
            'receive_payment_report': ['TRUSTED_PAYMENT_REPORT_ADAPTER_REQUIRED'],
            'reconcile_payments': ['TRUSTED_PAYMENT_REPORT_ADAPTER_REQUIRED',
                                   'PAYMENT_RECONCILIATION_ADAPTER_REQUIRED'],
            'map_payments': ['VERIFIED_BATCH_MAPPING_REQUIRED'],
            'archive_payment_evidence': ['RECONCILED_EVIDENCE_ARCHIVE_REQUIRED'],
            'raise_payment_issues': ['PAYMENT_ISSUE_ADAPTER_REQUIRED'],
        }
        return step_result(step, 'blocked', blockers.get(step, ['UNREGISTERED_WORKFLOW_STEP']))

    # Legacy structural consumers need the previously parsed preview even when
    # the protected validation step did not run. Its receipt remains BLOCKED,
    # with attempted/executed=false and explicit provisional evidence labeling.
    # Known prerequisites are informational, NOT claims of guard evaluation.
    def held_context(step):
        if step == 'validate_activity':
            return {'activities': activities, 'structural_preview_only': True,
                    'evidence_kind': 'provisional_structural_preview'}
        if step in {'prepare_payment_request', 'export_payment_request'}:
            return {'unverified_requirements': ['EXACT_BATCH_APPROVAL_REQUIRED']}
        return {}

    results = execute_graph(definitions[workflow_id].steps, evaluate,
                            blocked_context=held_context)
    status = ('blocked' if any(r['status'] == 'blocked' for r in results) else
              'needs_review' if any(r['status'] == 'needs_review' for r in results) else 'completed')
    run = WorkflowRun(actor_id=principal.user.id, project_id=project_id, request_key=request_key,
                      fingerprint=fingerprint, workflow_id=workflow_id, knowledge_version=knowledge().version,
                      created_at=int(time()), status=status,
                      snapshot={'steps': results, 'source_ids': [f.id for f, _ in documents],
                                'payment_return_file_id': payment_file.id if payment_file else None,
                                'mapping_ref': mapping_ref,
                                'planning_activities': planning_receipts,
                                'execution': {'mode': 'synchronous', 'completed_at': datetime.now(timezone.utc).isoformat()},
                                'preview': result_text if workflow_id in {'process_activity', 'show_issues'} else None})
    db.add(run)
    db.flush()
    # Persist typed step receipts in the SAME SQLite transaction as the run
    # and planning preflight. Never let a receipt outlive an uncommitted action.
    for index, result in enumerate(results):
        db.add(WorkflowStepReceipt(
            run_id=run.id, step_index=index, step_id=result['step'],
            status=result['status'], attempted=bool(result.get('attempted', True)),
            executed=bool(result.get('executed', False)),
            blocked_by=result.get('blocked_by'),
            issue_codes=result['issue_codes'], recorded_at=int(time()),
        ))
    db.flush()
    audit(db, 'workflow_run_recorded', principal.user.id, resource_type='workflow_run',
          resource_id=str(run.id), outcome=status, trigger=workflow_id)
    return run


def render_run(run):
    label = next(w.label for w in knowledge().workflows if w.id == run.workflow_id)
    lines = [f'{label}: {run.status.replace("_", " ")} (run #{run.id}).']
    if run.snapshot.get('planning_activities'):
        codes=sorted({item['activity_code'] for item in run.snapshot['planning_activities']})
        lines.append('Planning activities registered: '+', '.join(codes)+'.')
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


@router.get('/definitions')
def definitions(principal: Authenticated):
    principal.require('projects:read')
    from .workflow_contracts import catalog
    return {'version': knowledge().version, 'workflows': catalog()}


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


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    document_ids: list[UUID] | None = Field(default=None, max_length=20)


@router.post('/runs/{run_id}/resume', status_code=201)
def resume_run(run_id: int, body: ResumeRequest, request: Request,
               principal: Authenticated, db: Database):
    """Explicit human-driven revalidation linked to the original held run.

    A continuation creates a new immutable receipt set after fresh scope and
    authority checks. It never retries an uncertain side effect; future
    financial handlers must have their own separately approved resume protocol.
    """
    require_csrf(request, principal)
    db.rollback()
    db.execute(text('BEGIN IMMEDIATE'))
    principal = current_principal(request, db)
    require_csrf(request, principal)
    original = db.get(WorkflowRun, run_id)
    if original is None or original.actor_id != principal.user.id:
        raise HTTPException(404, 'Workflow run unavailable')
    principal.require('timesheets.view', original.project_id)
    if original.workflow_id != 'show_issues':
        principal.require('projects:manage')
    if original.status not in {'blocked', 'needs_review', 'failed'}:
        raise HTTPException(409, 'Only halted workflows can be continued')
    key = f'resume:{body.request_id}'
    replay = db.scalar(select(WorkflowRun).where(
        WorkflowRun.actor_id == principal.user.id, WorkflowRun.request_key == key))
    if replay and replay.snapshot.get('resumed_from_run_id') != original.id:
        raise HTTPException(409, 'Resume identifier already used for another run')
    selected = (body.document_ids if body.document_ids is not None
                else original.snapshot.get('source_ids', []))
    run = run_workflow(
        db, principal, request.app.state.config,
        workflow_id=original.workflow_id, project_id=original.project_id,
        request_key=key, document_ids=selected,
    )
    if replay is None:
        run.snapshot = {**run.snapshot, 'resumed_from_run_id': original.id,
                        'resume_mode': 'fresh_evidence_revalidation'}
        audit(db, 'workflow_run_continued', principal.user.id,
              resource_type='workflow_run', resource_id=str(run.id),
              outcome=run.status, trigger=original.workflow_id)
    db.commit()
    return {'id': run.id, 'status': run.status, 'steps': run.snapshot['steps'],
            'resumed_from_run_id': original.id}


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
