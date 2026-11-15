"""Immutable deterministic drafts, explicit human allocation/approval, manual files."""
import copy
import csv
import io
import json
from collections import defaultdict
from hashlib import sha256
from time import time
from datetime import datetime,timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from .observability import instrument
from .auth import Authenticated, Database, current_principal, require_csrf
from .audit import audit
from .models import projects
from .models import (WorkflowPaymentDraft as Draft,WorkflowPaymentApproval as Approval,
                     WorkflowCreditReservation as Reservation,WorkflowPaymentExport as Export,
                     Conversation,EvidenceReview,MappingProposal)
from .session_compensation import session_compensation
from .documents import resolve_documents,project_report_cutoffs
from .global_mappings import fingerprint
from .findings import (decisions_digest, digest_for_validation, excluded_activities,
                       excluded_months, unresolved_codes)

router=APIRouter(prefix='/api/workflow-payments')


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def rules_digest(family):
    """Bind arithmetic AND eligibility/source adapters, not just the money rate."""
    from pathlib import Path
    common=('source_dates','column_mappings','global_source_views','planning_activities',
            'reporting_register','documents','global_workflow','workflow_payments','findings')
    policy=('session_rules','session_preview','session_compensation') if family=='session' else ('fixed_hours_policy','hourly_preview')
    root=Path(__file__).parent
    return digest({name:sha256((root/(name+'.py')).read_bytes()).hexdigest()
                   for name in common+policy})


def review_refs(db,validation):
    refs=[]
    for activity in validation.snapshot['activities']:
        for kind in ('planning','staff'):
            review=db.scalar(select(EvidenceReview).where(EvidenceReview.validation_id==validation.id,
                EvidenceReview.project_code==activity['project_code'],EvidenceReview.activity_code==activity['activity_code'],
                EvidenceReview.kind==kind).order_by(EvidenceReview.id.desc()).limit(1))
            if review is None or review.decision!='confirmed':raise HTTPException(409,'Current planning and staff reviews are required')
            refs.append(review.id)
    return sorted(refs)


@instrument("payment.prepare_immutable_draft", "rule")
def make_draft(db,principal,conversation,documents,project,proposal,validation,structural,findings_rows=()):
    principal.require('payments.view',project['project_id'])
    if validation is None:raise HTTPException(409,'Validation snapshot required')
    unresolved=unresolved_codes(findings_rows)
    if unresolved:raise HTTPException(409,'FLAG_DECISION_REQUIRED: '+', '.join(unresolved))
    excluded=excluded_activities(findings_rows);excluded_hours=excluded_months(findings_rows)
    eligible=[a for a in structural['activities'] if a['activity_code'] not in excluded]
    reviews=review_refs(db,validation)
    cutoffs=project_report_cutoffs(db,project['project_id'])
    if not eligible or any((project['project_id'],a['project_code'],a['activity_code']) not in cutoffs for a in eligible):
        raise HTTPException(409,'REPORT_VALIDATION_EVIDENCE_REQUIRED')
    lines=[]; reservations=[]
    if project['policy_family']=='session':
        by_staff=defaultdict(list)
        for claim in structural['claims']:
            if claim['activity_code'] in excluded:continue
            by_staff[claim['staff_id']].append(claim)
        for staff,claims in sorted(by_staff.items()):
            keys=sorted({digest({k:c[k] for k in ('project_code','activity_code','staff_id','role','session','work_date')}) for c in claims})
            if len(keys)!=len(claims):raise HTTPException(409,'Duplicate financial source credit')
            amount,remainder=session_compensation(len(keys))
            used=len(keys)-remainder
            if not used:continue
            # Preserve unused credits instead of silently consuming them.
            reservations.extend(keys[:used])
            lines.append(dict(staff_id=staff,quantity=str(used//3),unit='three-session group',rate='25.00',amount=str(amount),
                              currency='USD',source_credit_keys=keys[:used],remaining_credits=keys[used:],allocation=None))
    else:
        for candidate in structural.get('hourly_candidates',[]):
            subject=f"{candidate['staff_id']}|{candidate['year']}-{candidate['month']:02d}"
            if subject in excluded_hours:continue
            if candidate['blockers'] or candidate['amount_usd'] is None:raise HTTPException(409,'Unresolved hourly rules')
            if not candidate['payable_hours']:continue
            key=digest(dict(staff_id=candidate['staff_id'],project_code=candidate['project_code'],year=candidate['year'],month=candidate['month'],unit='hourly-month'))
            reservations.append(key)
            lines.append(dict(staff_id=candidate['staff_id'],quantity=str(candidate['payable_hours']),unit='hour',rate='5.00',
                amount=candidate['amount_usd'],currency='USD',year=candidate['year'],month=candidate['month'],
                source_credit_keys=[key],source_ids=list(candidate['source_ids']),allocation=None))
    if not lines:raise HTTPException(409,'No eligible payable units in the validated scope')
    snapshot=dict(rules_digest=rules_digest(project['policy_family']),report_provenance_assurance='coordinator_declared_not_independently_authenticated',project_id=project['project_id'],project_code=project['project_code'],policy_family=project['policy_family'],
        source_fingerprint=fingerprint(documents),source_ids=[f.id for f,_ in documents],mapping_id=proposal.id,
        validation_id=validation.id,review_ids=reviews,report_cutoffs=sorted((str(k),v) for k,v in project_report_cutoffs(db,project['project_id']).items()),
        exclusions=dict(activities=sorted(excluded),hours_months=sorted(excluded_hours)),
        findings_digest=decisions_digest(findings_rows),
        decisions=[dict(id=row.id,code=row.code,scope=row.scope,subject=row.subject,state=row.state,
                        decision=row.decision,decided_by=row.decided_by,evidence_ref=row.evidence_ref)
                   for row in sorted(findings_rows,key=lambda row:(row.scope,row.subject,row.code))],
        lines=lines,reservation_keys=sorted(reservations),settlement='external_not_executed')
    original=store(db,principal.user.id,conversation.id,project['project_id'],snapshot)
    for configured in db.scalars(select(Draft).where(Draft.actor_id==principal.user.id,Draft.conversation_id==conversation.id,
            Draft.project_id==project['project_id']).order_by(Draft.created_at.desc()).limit(100)):
        base=copy.deepcopy(configured.snapshot)
        for line in base['lines']:line['allocation']=None
        if digest(base)==original.digest:return configured
    return original


def store(db,actor,conversation,project,snapshot):
    checksum=digest(snapshot)
    item=db.scalar(select(Draft).where(Draft.actor_id==actor,Draft.digest==checksum))
    if item:return item
    item=Draft(id=str(uuid4()),actor_id=actor,conversation_id=conversation,project_id=project,digest=checksum,
               snapshot=snapshot,created_at=datetime.now(timezone.utc).isoformat())
    db.add(item);db.flush()
    audit(db,'workflow_payment_draft_created',actor,resource_type='workflow_payment_draft',resource_id=item.id,outcome='immutable_unapproved_snapshot')
    return item


def owned(db,principal,identifier):
    item=db.get(Draft,str(identifier))
    if item is None or item.actor_id!=principal.user.id:raise HTTPException(404,'Payment draft unavailable')
    principal.require('payments.view',item.project_id)
    return item


def fresh(db,principal,config,item):
    from .conversation_workflow import check_integrity
    from .models import StructuralValidation
    project=db.execute(select(projects.c.status,projects.c.policy_family).where(projects.c.id==item.project_id)).one_or_none()
    if project is None or project.status!='active' or project.policy_family!=item.snapshot['policy_family']:
        raise HTTPException(409,'Project lifecycle or policy family changed; reprocess')
    if rules_digest(project.policy_family)!=item.snapshot['rules_digest']:
        raise HTTPException(409,'Calculation rule version changed; reprocess the immutable draft')
    docs=resolve_documents(db,principal,item.conversation_id,None,[]);check_integrity(config,docs)
    if fingerprint(docs)!=item.snapshot['source_fingerprint']:raise HTTPException(409,'STALE_FINANCIAL_SNAPSHOT: source scope changed; reprocess')
    proposal=db.get(MappingProposal,item.snapshot['mapping_id'])
    if proposal is None or proposal.status!='confirmed':raise HTTPException(409,'Confirmed mapping required')
    validation=db.get(StructuralValidation,item.snapshot['validation_id'])
    if validation is None or review_refs(db,validation)!=item.snapshot['review_ids']:raise HTTPException(409,'STALE_FINANCIAL_SNAPSHOT: human reviews changed')
    if item.snapshot.get('findings_digest')!=digest_for_validation(db,validation.id,item.conversation_id):
        raise HTTPException(409,'STALE_FINANCIAL_SNAPSHOT: flag decisions changed; reprocess')
    current=sorted((str(k),v) for k,v in project_report_cutoffs(db,item.project_id).items())
    # JSON round trips turn tuples into arrays.
    if json.loads(json.dumps(current))!=item.snapshot['report_cutoffs']:raise HTTPException(409,'STALE_FINANCIAL_SNAPSHOT: report authority changed')
    if digest(item.snapshot)!=item.digest:raise HTTPException(409,'FINANCIAL_SNAPSHOT_INTEGRITY_FAILED')


@router.get('/conversations/{conversation_id}')
def list_drafts(conversation_id:UUID,principal:Authenticated,db:Database):
    principal.require('projects:read')
    rows=db.scalars(select(Draft).where(Draft.actor_id==principal.user.id,Draft.conversation_id==str(conversation_id)).order_by(Draft.created_at,Draft.id)).all()
    latest={}
    for item in rows:
        if 'payments.view' in principal.project_permissions.get(item.project_id,[]):latest[item.project_id]=item
    return [dict(id=d.id,digest=d.digest,snapshot=d.snapshot,approved=bool(db.scalar(select(Approval.id).where(Approval.draft_id==d.id)))) for d in latest.values()]


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,str_strip_whitespace=True)


class Allocation(Strict):
    payee_reference:str=Field(min_length=1,max_length=200)
    allocation_reference:str=Field(min_length=1,max_length=200)
    evidence_ref:str=Field(min_length=5,max_length=500)


class Allocate(Strict):
    digest:str=Field(pattern='^[a-f0-9]{64}$')
    verified_by_human:bool
    allocations:dict[str,Allocation]=Field(max_length=500)


@router.post('/{draft_id}/allocations')
def allocations(draft_id:UUID,body:Allocate,request:Request,principal:Authenticated,db:Database):
    require_csrf(request,principal);db.rollback();db.execute(text('BEGIN IMMEDIATE'))
    principal=current_principal(request,db);require_csrf(request,principal)
    item=owned(db,principal,draft_id);principal.require('payments.allocate',item.project_id)
    if body.digest!=item.digest or not body.verified_by_human:raise HTTPException(409,'Exact snapshot and explicit allocation verification required')
    fresh(db,principal,request.app.state.config,item)
    snapshot=copy.deepcopy(item.snapshot)
    expected={line['staff_id'] for line in snapshot['lines']}
    if set(body.allocations)!=expected:raise HTTPException(422,'Provide verified destination/allocation for every payee exactly once')
    for line in snapshot['lines']:
        line['allocation']={**body.allocations[line['staff_id']].model_dump(), 'verified_by':principal.user.id,'assurance':'authorized_human_declaration'}
    configured=store(db,principal.user.id,item.conversation_id,item.project_id,snapshot)
    audit(db,'workflow_payment_allocations_verified',principal.user.id,resource_type='workflow_payment_draft',resource_id=configured.id,outcome='new_snapshot_requires_exact_approval')
    db.commit();return {'id':configured.id,'digest':configured.digest}


class Approve(Strict):
    digest:str=Field(pattern='^[a-f0-9]{64}$')
    approve_exact_snapshot:bool


@router.post('/{draft_id}/approve')
def approve(draft_id:UUID,body:Approve,request:Request,principal:Authenticated,db:Database):
    require_csrf(request,principal);db.rollback();db.execute(text('BEGIN IMMEDIATE'))
    principal=current_principal(request,db);require_csrf(request,principal)
    item=owned(db,principal,draft_id);principal.require('payments.approve',item.project_id)
    if body.digest!=item.digest or not body.approve_exact_snapshot:raise HTTPException(409,'Exact snapshot approval required')
    fresh(db,principal,request.app.state.config,item)
    if any(not line['allocation'] for line in item.snapshot['lines']):raise HTTPException(409,'VERIFIED_DESTINATION_AND_ALLOCATION_REQUIRED')
    previous=db.scalar(select(Approval).where(Approval.draft_id==item.id))
    if previous:return {'id':previous.id,'draft_id':item.id,'digest':item.digest,'idempotent':True}
    approval=Approval(id=str(uuid4()),draft_id=item.id,digest=item.digest,actor_id=principal.user.id,approved_at=int(time()))
    db.add(approval)
    for key in item.snapshot['reservation_keys']:db.add(Reservation(credit_key=key,draft_id=item.id))
    audit(db,'workflow_payment_exact_batch_approved',principal.user.id,resource_type='workflow_payment_draft',resource_id=item.id,outcome=item.digest)
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'SOURCE_CREDIT_ALREADY_RESERVED: approved credits/months require reconciliation, not a second batch') from None
    resume(db,principal,request.app.state.config,item)
    return {'id':approval.id,'draft_id':item.id,'digest':item.digest,'idempotent':False}


def export_bytes(item,approval):
    output=io.StringIO(newline='');writer=csv.writer(output)
    writer.writerow(['batch_id','snapshot_hash','project','staff_id','quantity','unit','rate_USD','amount_USD','currency','payee_reference','allocation_reference','approval_id'])
    def cell(value):
        raw=str(value)
        return "'"+raw if raw.lstrip().startswith(('=','+','-','@')) or raw.startswith(('\t','\r','\n')) else raw
    for line in item.snapshot['lines']:
        writer.writerow([cell(v) for v in (item.id,item.digest,item.snapshot['project_code'],line['staff_id'],line['quantity'],line['unit'],line['rate'],line['amount'],line['currency'],line['allocation']['payee_reference'],line['allocation']['allocation_reference'],approval.id)])
    return output.getvalue().encode('utf-8-sig')


@router.post('/{draft_id}/export')
def export(draft_id:UUID,body:Approve,request:Request,principal:Authenticated,db:Database):
    require_csrf(request,principal);db.rollback();db.execute(text('BEGIN IMMEDIATE'))
    principal=current_principal(request,db);require_csrf(request,principal)
    item=owned(db,principal,draft_id);principal.require('payments.approve',item.project_id)
    if body.digest!=item.digest:raise HTTPException(409,'Export must match the approved snapshot')
    fresh(db,principal,request.app.state.config,item)
    approval=db.scalar(select(Approval).where(Approval.draft_id==item.id,Approval.digest==item.digest))
    if not approval:raise HTTPException(409,'EXACT_BATCH_APPROVAL_REQUIRED')
    data=export_bytes(item,approval);checksum=sha256(data).hexdigest()
    previous=db.scalar(select(Export).where(Export.draft_id==item.id))
    if previous and previous.sha256!=checksum:raise HTTPException(409,'EXPORTED_SNAPSHOT_CONFLICT')
    if not previous:
        db.add(Export(id=str(uuid4()),draft_id=item.id,approval_id=approval.id,sha256=checksum,created_at=int(time())))
        audit(db,'workflow_payment_file_exported',principal.user.id,resource_type='workflow_payment_draft',resource_id=item.id,outcome='file_only_no_transfer')
    db.commit()
    resume(db,principal,request.app.state.config,item)
    return Response(data,media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="payment-request-{item.id}.csv"','X-Content-Type-Options':'nosniff'})


def resume(db,principal,config,item):
    if 'projects:manage' not in principal.permissions:return
    conversation=db.get(Conversation,item.conversation_id)
    if conversation is None or conversation.owner_id!=principal.user.id:return
    from .global_mappings import resume_after_evidence
    documents=resolve_documents(db,principal,conversation.id,None,[])
    resume_after_evidence(db,principal,config,conversation,documents)
    db.commit()
