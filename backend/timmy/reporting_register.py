"""Manually uploaded designated Excel evidence. Declaration != authentication."""
import json
from datetime import datetime, timezone
from hashlib import sha256
from time import time
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text

from .auth import Authenticated, Database, require_csrf, current_principal
from .audit import audit
from .column_mappings import propose_sheet, mapping_errors
from .documents import resolve_documents
from .models import (ReportingRegisterSource, ReportingRegisterImport, ReportingRegisterDecision,
                     ExternalReportVersion, activities, projects, Conversation)
from .observability import span, reference

router = APIRouter(prefix='/api/reporting-register')
ASSURANCE = 'coordinator_declared_not_independently_authenticated'
STATUSES = {
    'NOT_SUBMITTED':'NOT_SUBMITTED', 'NOT SUBMITTED':'NOT_SUBMITTED', 'DRAFT':'NOT_SUBMITTED',
    'SUBMITTED':'AWAITING_VALIDATION', 'AWAITING_VALIDATION':'AWAITING_VALIDATION',
    'AWAITING VALIDATION':'AWAITING_VALIDATION', 'UNDER_REVIEW':'AWAITING_VALIDATION',
    'PENDING':'AWAITING_VALIDATION', 'VALIDATED':'VALIDATED',
    'REJECTED':'REJECTED', 'REQUIRES_CORRECTION':'REQUIRES_CORRECTION',
    'REQUIRES CORRECTION':'REQUIRES_CORRECTION', 'CORRECTION_REQUIRED':'REQUIRES_CORRECTION',
}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


class Designation(Strict):
    name: str = Field(min_length=3, max_length=160)
    project_ids: list[int] = Field(min_length=1, max_length=100)
    approved_source: bool


class SheetMapping(Strict):
    sheet_index: int = Field(ge=0, le=11)
    columns: dict[str, int] = Field(max_length=20)


class Declaration(Strict):
    source_id: str = Field(min_length=36, max_length=36)
    file_id: str = Field(min_length=36, max_length=36)
    sha256: str = Field(pattern='^[0-9a-f]{64}$')
    official_export_declared: bool
    sheets: list[SheetMapping] = Field(min_length=1, max_length=12)


def require_projects(principal, ids):
    for identifier in ids:
        principal.require('projects:read', identifier)
        principal.require('timesheets.view', identifier)


@router.post('/sources', status_code=201)
def designate(body: Designation, request: Request, principal: Authenticated, db: Database):
    require_csrf(request, principal)
    principal.require('settings:read')
    principal.require('projects:manage')
    if not body.approved_source or len(set(body.project_ids)) != len(body.project_ids):
        raise HTTPException(422, 'Explicit designation and distinct project scopes required')
    require_projects(principal, body.project_ids)
    if set(db.scalars(select(projects.c.id).where(projects.c.id.in_(body.project_ids)))) != set(body.project_ids):
        raise HTTPException(422, 'Unknown project scope')
    item=ReportingRegisterSource(id=str(uuid4()), name=body.name.strip(), project_ids=sorted(body.project_ids),
                                  approved_by=principal.user.id, approved_at=int(time()))
    db.add(item); db.flush()
    audit(db, 'report_register_designated', principal.user.id, resource_type='reporting_register_source',resource_id=item.id,outcome='approved_source_designation')
    db.commit()
    return source_view(item)


def source_view(source):
    return dict(id=source.id,name=source.name,project_ids=source.project_ids,approved_by=source.approved_by,
                approved_at=source.approved_at,assurance=ASSURANCE)


@router.get('/sources')
def sources(principal: Authenticated, db: Database):
    principal.require('projects:read')
    return [source_view(s) for s in db.scalars(select(ReportingRegisterSource).order_by(ReportingRegisterSource.approved_at))
            if all('timesheets.view' in principal.project_permissions.get(pid,[]) for pid in s.project_ids)]


def candidates(db, principal, conversation_id, config):
    conversation=db.get(Conversation,str(conversation_id))
    if conversation is None or conversation.owner_id != principal.user.id:
        raise HTTPException(404,'Conversation unavailable')
    documents=resolve_documents(db,principal,conversation.id,None,[])
    result=[]
    for file, record in documents:
        mappings=[propose_sheet(file,sheet,i) for i,sheet in enumerate(record.sheets)]
        reports=[sheet for sheet in mappings if sheet['kind']=='reports']
        if not reports: continue
        prior=db.scalar(select(ReportingRegisterImport).where(ReportingRegisterImport.actor_id==principal.user.id,
                           ReportingRegisterImport.sha256==file.sha256).order_by(ReportingRegisterImport.confirmed_at.desc()))
        decision=db.scalar(select(ReportingRegisterDecision).where(ReportingRegisterDecision.import_id==prior.id).order_by(ReportingRegisterDecision.id.desc())) if prior else None
        result.append(dict(evaluation=decision.snapshot if decision else None,file_id=file.id,filename=file.original_filename,sha256=file.sha256,uploaded_at=file.uploaded_at,
                           sheets=reports,errors=mapping_errors(reports),confirmed_import_id=prior.id if prior else None,
                           assurance=prior.assurance if prior else 'unconfirmed',
                           declaration_required=not bool(prior)))
    return result


@router.get('/conversations/{conversation_id}')
def pending(conversation_id: UUID, request: Request, principal: Authenticated, db: Database):
    return candidates(db,principal,conversation_id,request.app.state.config)


def timestamp(value):
    value=str(value or '').strip()
    if not value: return None
    parsed=datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        # The approved register contract uses Asia/Beirut wall time.
        zone=ZoneInfo('Asia/Beirut')
        if parsed.replace(tzinfo=zone,fold=0).utcoffset()!=parsed.replace(tzinfo=zone,fold=1).utcoffset():
            raise ValueError('AMBIGUOUS_REGISTER_TIME')
        parsed=parsed.replace(tzinfo=zone)
    return parsed


def parse_rows(documents, declaration, source, principal):
    file, record=next((f,r) for f,r in documents if f.id==declaration.file_id)
    proposals=[propose_sheet(file,s,i) for i,s in enumerate(record.sheets)]
    expected={s['sheet_index'] for s in proposals if s['kind']=='reports'}
    supplied={s.sheet_index:s for s in declaration.sheets}
    if set(supplied)!=expected or len(supplied)!=len(declaration.sheets):
        raise HTTPException(422,'Confirm every reporting sheet exactly once; no omissions or duplicate sheets')
    normalized=[]
    for index in sorted(expected):
        proposal=proposals[index]
        proposal['columns']=supplied[index].columns
        proposal['conflicts']=[]
        errors=mapping_errors([proposal])
        if errors: raise HTTPException(422, '; '.join(errors))
        for row in record.sheets[index]['rows'][1:]:
            normalized.append(dict(sheet_index=index,source_row=row['row'],values={
                field:row['values'][column] if column<len(row['values']) else None
                for field,column in proposal['columns'].items()}))
    return normalized


@router.post('/conversations/{conversation_id}/confirm')
def confirm(conversation_id: UUID, body: Declaration, request: Request, principal: Authenticated, db: Database):
    require_csrf(request,principal)
    principal.require('projects:manage')
    db.rollback(); db.execute(text('BEGIN IMMEDIATE'))
    principal=current_principal(request,db); require_csrf(request,principal)
    principal.require('projects:manage')
    conversation=db.get(Conversation,str(conversation_id))
    if conversation is None or conversation.owner_id!=principal.user.id:
        raise HTTPException(404,'Conversation unavailable')
    source=db.get(ReportingRegisterSource,body.source_id)
    if source is None: raise HTTPException(404,'Approved reporting source unavailable')
    require_projects(principal,source.project_ids)
    if not body.official_export_declared:
        raise HTTPException(422,'Explicit provenance declaration is required; upload alone is insufficient')
    documents=resolve_documents(db,principal,conversation.id,None,[body.file_id])
    file, record=documents[0]
    if not file.original_filename.lower().endswith('.xlsx'):
        raise HTTPException(422,'The designated reporting register must be an Excel workbook')
    if file.sha256!=body.sha256:
        raise HTTPException(409,'Source hash changed; review the current original')
    from .conversation_workflow import check_integrity
    check_integrity(request.app.state.config,documents)
    rows=parse_rows(documents,body,source,principal)
    code_map=dict(db.execute(select(projects.c.project_code,projects.c.id).where(projects.c.id.in_(source.project_ids))).all())
    for row in rows:
        pid=code_map.get(str(row['values'].get('project_code') or '').strip())
        if pid is None:
            raise HTTPException(422,'Reporting row has an unknown or undesignated project acronym')
        row['project_id']=pid
    mappings=[s.model_dump() for s in sorted(body.sheets,key=lambda s:s.sheet_index)]
    digest=sha256(json.dumps(mappings,sort_keys=True).encode()).hexdigest()
    existing=db.scalar(select(ReportingRegisterImport).where(ReportingRegisterImport.source_id==source.id,
                       ReportingRegisterImport.actor_id==principal.user.id,ReportingRegisterImport.sha256==file.sha256))
    if existing and existing.mapping_digest!=digest:
        raise HTTPException(409,'This original already has an immutable confirmed mapping')
    item=existing or ReportingRegisterImport(id=str(uuid4()),source_id=source.id,file_id=file.id,actor_id=principal.user.id,
          sha256=file.sha256,mapping_digest=digest,mappings=mappings,rows=rows,confirmed_at=datetime.now(timezone.utc).isoformat(),assurance=ASSURANCE)
    if not existing:
        db.add(item); db.flush()
        audit(db,'report_register_provenance_declared',principal.user.id,resource_type='reporting_register_import',
              resource_id=item.id,outcome=ASSURANCE,evidence_file_id=file.id)
    result=evaluate(db,principal,item)
    from .global_mappings import resume_after_evidence
    all_documents=resolve_documents(db,principal,conversation.id,None,[])
    resumed=resume_after_evidence(db,principal,request.app.state.config,conversation,all_documents)
    db.commit()
    return dict(message=resumed,import_id=item.id,assurance=ASSURANCE,idempotent=bool(existing),evaluation=result)


def evaluate(db,principal,item):
    """Append observations and accept only complete, consistent designated evidence."""
    source=db.get(ReportingRegisterSource,item.source_id)
    require_projects(principal,source.project_ids)
    outcomes=[]
    keys={}
    for row in item.rows:
        v=row['values']; key=(row['project_id'],str(v.get('activity_code') or '').strip(),
                             str(v.get('report_id') or '').strip(),str(v.get('report_version') or '').strip())
        keys.setdefault(key,[]).append(row)
    with span('report_register.evaluate','validation'):
        def validation_order(pair):
            try:
                value=timestamp(pair[1][0]['values'].get('validated_at'))
            except (ValueError,TypeError,OverflowError):
                value=None
            return (value or datetime.max.replace(tzinfo=timezone.utc), pair[0])
        ordered=sorted(keys.items(), key=validation_order)
        validation_times={}
        for key, members in ordered:
            try:
                when=timestamp(members[0]['values'].get('validated_at'))
            except (ValueError,TypeError,OverflowError):
                when=None
            if when:
                validation_times.setdefault((key[0],key[1],when),set()).add(key[3])
        for key, members in ordered:
            pid,code,report_id,version=key
            for row in members:
                values=row['values']; issues=[]
                status=STATUSES.get(str(values.get('validation_status') or '').strip().upper())
                activity_id=db.scalar(select(activities.c.id).where(activities.c.project_id==pid,
                    activities.c.activity_code==code,activities.c.code_authority=='source_supplied'))
                if not activity_id: issues.append('ACTIVITY_REGISTRATION_REQUIRED')
                if not code or not report_id or not version: issues.append('REPORT_IDENTITY_REQUIRED')
                if status is None: issues.append('UNKNOWN_REPORT_STATUS')
                if len(members)>1: issues.append('DUPLICATE_REPORT_VERSION_IN_EXPORT')
                try:
                    submitted=timestamp(values.get('submitted_at')); validated=timestamp(values.get('validated_at'))
                except (ValueError,TypeError,OverflowError):
                    submitted=validated=None; issues.append('REGISTER_TIMESTAMP_REVIEW_REQUIRED')
                if validated and len(validation_times.get((pid,code,validated),set()))>1:
                    issues.append('AMBIGUOUS_FIRST_VALIDATION')
                evidence=str(values.get('evidence_ref') or '').strip()
                if status!='NOT_SUBMITTED' and submitted is None: issues.append('SUBMISSION_EVIDENCE_REQUIRED')
                if status=='NOT_SUBMITTED' and (submitted or validated): issues.append('CONTRADICTORY_REPORT_STATUS')
                if status=='VALIDATED' and (validated is None or not evidence): issues.append('VALIDATION_EVIDENCE_REQUIRED')
                if status!='VALIDATED' and validated: issues.append('CONTRADICTORY_REPORT_STATUS')
                if submitted and validated and validated<submitted: issues.append('VALIDATION_PREDATES_SUBMISSION')
                prior=list(db.scalars(select(ExternalReportVersion).where(ExternalReportVersion.project_id==pid,
                            ExternalReportVersion.activity_code==code)))
                existing=next((p for p in prior if p.version==version),None)
                if any(p.source!=f'excel-register:{source.id}' or p.report_id!=report_id for p in prior):
                    issues.append('CONFLICTING_REPORT_AUTHORITY')
                if existing and (not submitted or datetime.fromisoformat(existing.submitted_at)!=submitted or
                    (existing.validated_at and (status!='VALIDATED' or not validated or datetime.fromisoformat(existing.validated_at)!=validated))):
                    issues.append('CONFLICTING_REPORT_HISTORY')
                frozen=[p for p in prior if p.cutoff]
                if len(frozen)>1: issues.append('CONFLICTING_FROZEN_CUTOFFS')
                if frozen and validated and datetime.fromisoformat(frozen[0].validated_at)>validated and (not existing or existing.id!=frozen[0].id):
                    issues.append('EARLIER_VALIDATION_CONFLICTS_WITH_FROZEN_CUTOFF')
                if not issues and status in {'AWAITING_VALIDATION','VALIDATED','REJECTED','REQUIRES_CORRECTION'}:
                    if existing is None:
                        existing=ExternalReportVersion(project_id=pid,activity_id=activity_id,activity_code=code,
                            source=f'excel-register:{source.id}',report_id=report_id,version=version,
                            submitted_at=submitted.isoformat(),local_date=submitted.astimezone(ZoneInfo('Asia/Beirut')).date().isoformat(),
                            evidence_ref=f'{item.id}:{row["sheet_index"]}:{row["source_row"]}:{evidence}')
                        db.add(existing)
                    if status=='VALIDATED' and not existing.validated_at:
                        existing.evidence_ref=f'{item.id}:{row["sheet_index"]}:{row["source_row"]}:{evidence}'
                        existing.validated_at=validated.isoformat()
                        if not frozen:
                            existing.cutoff=existing.local_date
                    db.flush()
                outcomes.append(dict(project_id=pid,activity_code=code,report_id=report_id,version=version,
                    sheet_index=row['sheet_index'],source_row=row['source_row'],register_status=status or 'UNKNOWN',
                    issue_codes=sorted(set(issues)),accepted=not issues and status=='VALIDATED',
                    cutoff=next((p.cutoff for p in prior if p.cutoff), None) or (existing.cutoff if existing else None)))
                reference('excel-register:'+source.id,'executed',item.sha256,status='blocked' if issues else 'completed')
    snapshot=dict(assurance=item.assurance,source_id=source.id,file_id=item.file_id,sha256=item.sha256,rows=outcomes)
    fingerprint=sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()
    previous=db.scalar(select(ReportingRegisterDecision.id).where(ReportingRegisterDecision.import_id==item.id,
                                                                 ReportingRegisterDecision.fingerprint==fingerprint))
    if not previous:
        db.add(ReportingRegisterDecision(import_id=item.id,fingerprint=fingerprint,snapshot=snapshot,evaluated_at=int(time())))
        db.flush()
    return snapshot


def synchronize_confirmed(db,principal,config,documents):
    from .conversation_workflow import check_integrity
    check_integrity(config,documents)
    hashes={f.sha256 for f,_ in documents}
    results=[]
    for item in db.scalars(select(ReportingRegisterImport).where(ReportingRegisterImport.actor_id==principal.user.id,
                           ReportingRegisterImport.sha256.in_(hashes))):
        results.append(evaluate(db,principal,item))
    return results


def financial_register_blockers(db, project_id, activity_code):
    """Latest declaration of each version must not contradict accepted history."""
    decisions=db.execute(select(ReportingRegisterImport, ReportingRegisterDecision).join(
        ReportingRegisterDecision, ReportingRegisterDecision.import_id==ReportingRegisterImport.id
    ).order_by(ReportingRegisterImport.confirmed_at,ReportingRegisterImport.id,ReportingRegisterDecision.id)).all()
    latest={}
    for imported,decision in decisions:
        for row in decision.snapshot['rows']:
            if row['project_id']==project_id and row['activity_code']==activity_code:
                latest[imported.source_id,row['report_id'],row['version']]=row
    conflicts={'CONFLICTING_REPORT_AUTHORITY','CONFLICTING_REPORT_HISTORY','CONFLICTING_FROZEN_CUTOFFS',
               'EARLIER_VALIDATION_CONFLICTS_WITH_FROZEN_CUTOFF','CONTRADICTORY_REPORT_STATUS',
               'AMBIGUOUS_FIRST_VALIDATION','DUPLICATE_REPORT_VERSION_IN_EXPORT','VALIDATION_EVIDENCE_REQUIRED',
               'SUBMISSION_EVIDENCE_REQUIRED','UNKNOWN_REPORT_STATUS','REPORT_IDENTITY_REQUIRED','REGISTER_TIMESTAMP_REVIEW_REQUIRED'}
    return sorted({code for row in latest.values() for code in row['issue_codes'] if code in conflicts})
