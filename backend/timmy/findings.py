"""Persisted end-of-run flag decisions over one immutable validation snapshot.

Findings are derived from the deterministic structural snapshot only. A decision
can exclude affected records from the payment request, or escalate/require
corrected source evidence. It can never add money, invent a correction, or clear
a whole-project authority gate; excluded records are simply not paid here.
"""
import json
from hashlib import sha256
from time import time
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text

from .audit import audit
from .auth import Authenticated, Database, current_principal, require_csrf
from .models import (Conversation, StructuralValidation, WorkflowFinding, WorkflowRun, projects)

router = APIRouter(prefix='/api/workflow-findings')

DECISIONS = {'invalidate': 'invalidated', 'escalate': 'escalated',
             'correct_source': 'corrected_requires_reprocess'}
BLOCKING_STATES = frozenset({'open', 'escalated', 'corrected_requires_reprocess'})
MAX_REFS = 20


def _key(scope, subject, code):
    return scope, subject, code


def derive(structural, *, project_id, project_code, cutoffs):
    """One finding per affected unit and rule, with original source references."""
    specs = []
    claims_by_activity = {}
    for claim in structural.get('claims', []):
        reference = f"{claim.get('file_id')}:{claim.get('sheet')}:{claim.get('row')}"
        claims_by_activity.setdefault(claim.get('activity_code'), set()).add(reference)

    def add(scope, subject, code, refs=(), detail=None):
        specs.append(dict(scope=scope, subject=str(subject), code=str(code),
                          source_refs=sorted({str(ref) for ref in refs if ref})[:MAX_REFS],
                          detail=dict(detail or {})))

    for activity in structural.get('activities', []):
        code = activity['activity_code']
        references = claims_by_activity.get(code, ())
        for issue, count in sorted((activity.get('issues') or {}).items()):
            add('activity', code, issue, references, {'affected_claims': count})
        if (project_id, project_code, code) not in cutoffs:
            add('activity', code, 'REPORT_VALIDATION_EVIDENCE_REQUIRED', references,
                {'evidence': 'validated external report version and frozen cutoff'})
    for candidate in structural.get('hourly_candidates', []):
        blockers = list(candidate.get('blockers') or [])
        if not blockers:
            continue
        subject = f"{candidate['staff_id']}|{candidate['year']}-{candidate['month']:02d}"
        for blocker in blockers:
            add('hours_month', subject, blocker, candidate.get('source_ids', ()), {
                'blockers': blockers,
                'actual_unique_minutes': candidate['actual_unique_minutes'],
                'rounded_minutes': candidate['rounded_minutes'],
                'amount_usd': candidate['amount_usd']})
    for issue in structural.get('hourly_parse_issues', []):
        add('project', '', 'HOURS_SHIFT_PARSE_REVIEW_REQUIRED', (), {'evidence': str(issue)[:400]})
    for issue in structural.get('policy_issues', []):
        add('project', '', issue, ())
    return specs


def sync(db, *, project_id, conversation_id, validation, structural, project_code, cutoffs):
    """Create/refresh the decision round; existing decisions are never rewritten."""
    rows = list(db.scalars(select(WorkflowFinding).where(
        WorkflowFinding.validation_id == validation.id,
        WorkflowFinding.conversation_id == conversation_id)))
    known = {(row.scope, row.subject, row.code): row for row in rows}
    for spec in derive(structural, project_id=project_id, project_code=project_code, cutoffs=cutoffs):
        row = known.get(_key(spec['scope'], spec['subject'], spec['code']))
        if row is None:
            row = WorkflowFinding(id=str(uuid4()), project_id=project_id,
                                  conversation_id=conversation_id, validation_id=validation.id,
                                  created_at=int(time()), state='open', **spec)
            db.add(row)
            known[_key(spec['scope'], spec['subject'], spec['code'])] = row
            rows.append(row)
        elif row.state == 'open':
            row.source_refs = spec['source_refs']
            row.detail = spec['detail']
    db.flush()
    return rows


def excluded_activities(rows):
    return {row.subject for row in rows if row.scope == 'activity' and row.state == 'invalidated'}


def excluded_months(rows):
    return {row.subject for row in rows if row.scope == 'hours_month' and row.state == 'invalidated'}


def unresolved_codes(rows):
    return sorted({row.code for row in rows if row.state in BLOCKING_STATES})


def decisions_digest(rows):
    payload = sorted((row.id, row.scope, row.subject, row.code, row.state,
                      row.decision or '', row.evidence_ref or '') for row in rows)
    return sha256(json.dumps(payload, separators=(',', ':')).encode()).hexdigest()


def digest_for_validation(db, validation_id, conversation_id):
    rows = list(db.scalars(select(WorkflowFinding).where(
        WorkflowFinding.validation_id == validation_id,
        WorkflowFinding.conversation_id == conversation_id)))
    return decisions_digest(rows)


def _view(row):
    return dict(id=row.id, code=row.code, scope=row.scope, subject=row.subject, state=row.state,
                decision=row.decision, evidence_ref=row.evidence_ref, note=row.note,
                source_refs=row.source_refs or [], detail=row.detail or {},
                options=list(DECISIONS) if row.scope != 'project' else ['escalate', 'correct_source'],
                evidence_required=row.scope == 'project')


def round_for_conversation(db, principal, conversation):
    principal.require('projects:read')
    runs = db.scalars(select(WorkflowRun).where(
        WorkflowRun.actor_id == principal.user.id,
        WorkflowRun.request_key.like(f'global:{conversation.id}:%'),
    ).order_by(WorkflowRun.id.desc()).limit(100)).all()
    latest = {}
    for run in runs:
        latest.setdefault(run.project_id, run)
    projects_view = []
    for project_id, run in sorted(latest.items()):
        if 'discrepancies.view' not in principal.project_permissions.get(project_id, ()):
            continue
        validation_id = run.snapshot.get('structural_validation_id')
        if validation_id is None:
            continue
        code = db.scalar(select(projects.c.project_code).where(projects.c.id == project_id))
        rows = list(db.scalars(select(WorkflowFinding).where(
            WorkflowFinding.validation_id == validation_id,
            WorkflowFinding.conversation_id == conversation.id).order_by(
            WorkflowFinding.scope, WorkflowFinding.subject, WorkflowFinding.code)))
        if not rows:
            continue
        projects_view.append(dict(
            project_id=project_id, project_code=code, validation_id=validation_id,
            run_id=run.id, open=sum(row.state in BLOCKING_STATES for row in rows),
            decided=sum(row.state not in BLOCKING_STATES for row in rows),
            findings=[_view(row) for row in rows]))
    open_total = sum(item['open'] for item in projects_view)
    return dict(projects=projects_view, open_total=open_total,
                ready_for_payment=bool(projects_view) and open_total == 0,
                assurance='deterministic_rules_with_explicit_human_dispositions')


@router.get('/conversations/{conversation_id}')
def conversation_round(conversation_id: UUID, principal: Authenticated, db: Database):
    conversation = db.get(Conversation, str(conversation_id))
    if conversation is None or conversation.owner_id != principal.user.id:
        raise HTTPException(404, 'Conversation unavailable')
    return round_for_conversation(db, principal, conversation)


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    decision: str = Field(pattern='^(invalidate|escalate|correct_source)$')
    evidence_ref: str = Field(min_length=5, max_length=500)
    note: str | None = Field(default=None, max_length=1000)


@router.post('/{finding_id}/decide')
def decide(finding_id: UUID, body: Decision, request: Request,
           principal: Authenticated, db: Database):
    require_csrf(request, principal)
    db.rollback()
    db.execute(text('BEGIN IMMEDIATE'))
    principal = current_principal(request, db)
    require_csrf(request, principal)
    item = db.get(WorkflowFinding, str(finding_id))
    if item is None:
        raise HTTPException(404, 'Finding unavailable')
    conversation = db.get(Conversation, item.conversation_id)
    if conversation is None or conversation.owner_id != principal.user.id:
        raise HTTPException(404, 'Finding unavailable')
    principal.require('discrepancies.view', item.project_id)
    if body.decision == 'invalidate':
        principal.require('payments.allocate', item.project_id)
        if item.scope == 'project':
            raise HTTPException(409, 'PROJECT_SCOPE_FINDING_REQUIRES_EVIDENCE_OR_ESCALATION')
    else:
        principal.require('timesheets.view', item.project_id)
    latest = db.scalar(select(StructuralValidation.id).where(
        StructuralValidation.project_id == item.project_id).order_by(StructuralValidation.id.desc()).limit(1))
    if latest != item.validation_id:
        raise HTTPException(409, 'REPROCESS_REQUIRED: this decision round belongs to an older snapshot')
    state = DECISIONS[body.decision]
    siblings = [item] if body.decision != 'invalidate' else list(db.scalars(select(WorkflowFinding).where(
        WorkflowFinding.validation_id == item.validation_id,
        WorkflowFinding.scope == item.scope, WorkflowFinding.subject == item.subject)))
    for row in siblings:
        if row.state != 'open':
            if (row.state == state and row.decision == body.decision
                    and row.evidence_ref == body.evidence_ref):
                continue
            raise HTTPException(409, 'FLAG_ALREADY_DECIDED: reprocess the sources for a new round')
    for row in siblings:
        row.state = state
        row.decision = body.decision
        row.decided_by = principal.user.id
        row.decided_at = int(time())
        row.evidence_ref = body.evidence_ref
        row.note = body.note
        audit(db, 'workflow_finding_decided', principal.user.id, resource_type='workflow_finding',
              resource_id=row.id, outcome=f'{body.decision}:{row.scope}:{row.subject}')
    db.flush()
    db.commit()
    from .documents import resolve_documents
    from .global_mappings import resume_after_evidence
    documents = resolve_documents(db, principal, conversation.id, None, [])
    resumed = resume_after_evidence(db, principal, request.app.state.config, conversation, documents)
    db.commit()
    return dict(id=item.id, state=item.state, decision=item.decision,
                decided=len(siblings), resumed=bool(resumed), resumed_message=resumed)
