"""One mapping review for a global conversation, with project-scoped receipts."""
import copy
import json
from hashlib import sha256
from time import time
from uuid import UUID, uuid4
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, text
from .auth import Authenticated, Database, current_principal, require_csrf
from .models import Conversation, MappingProposal, WorkflowRun, ChatTurn
from .column_mappings import propose_sheet, mapping_errors, reuse_approved_formats
from .documents import resolve_documents
from .audit import audit

router=APIRouter(prefix='/api/global-mappings')


def fingerprint(documents):
    return sha256(json.dumps(sorted((f.id,f.sha256) for f,_ in documents)).encode()).hexdigest()


def proposals(db,principal,conversation,documents,project_ids,create=False):
    digest=fingerprint(documents)
    sheets=[propose_sheet(file,sheet,i) for file,record in documents for i,sheet in enumerate(record.sheets)]
    result=[]
    for project in sorted(project_ids):
        principal.require('timesheets.view',project)
        item=db.scalar(select(MappingProposal).where(MappingProposal.conversation_id==conversation.id,
            MappingProposal.actor_id==principal.user.id,MappingProposal.project_id==project,
            MappingProposal.fingerprint==digest).order_by(MappingProposal.version.desc()))
        if item is None and create:
            version=(db.scalar(select(func.max(MappingProposal.version)).where(
                MappingProposal.conversation_id==conversation.id)) or 0)+1
            confirmed=reuse_approved_formats(db,principal.user.id,project,sheets)
            automatic=False
            if not confirmed and sheets and not mapping_errors(sheets) and all(
                    sheet.get('confidence')=='high' for sheet in sheets):
                # Fully confident header mapping: apply it and keep a correction
                # path (confirmed_by stays empty until a human re-confirms).
                confirmed=copy.deepcopy(sheets);automatic=True
            item=MappingProposal(conversation_id=conversation.id,actor_id=principal.user.id,project_id=project,
                fingerprint=digest,version=version,sheets=confirmed or copy.deepcopy(sheets),created_at=int(time()),
                status='confirmed' if confirmed else 'proposed',confirmed_by=principal.user.id if confirmed and not automatic else None,
                confirmed_at=int(time()) if confirmed else None)
            db.add(item);db.flush()
            if automatic:
                audit(db,'global_mapping_auto_confirmed',principal.user.id,resource_type='mapping_proposal',
                      resource_id=item.id,outcome='high_confidence_header_mapping_no_review_required')
        if item:result.append(item)
    return result


def planning_format_candidates(db, documents, sheets, project_ids):
    """Propose only from confirmed planning columns, never evidence labels."""
    import re
    from .models import projects
    names={row.id:row for row in db.execute(select(projects.c.id,projects.c.project_code,projects.c.name).where(projects.c.id.in_(project_ids)))}
    originals={f.id:(f,r) for f,r in documents}
    result=[]
    for pid in project_ids:
        project=names[pid]; evidence=[]
        for selection in sheets:
            if selection['kind']!='planning':continue
            file,record=originals[selection['file_id']]
            sheet=record.sheets[selection['sheet_index']];columns=selection['columns']
            for row in sheet['rows'][1:]:
                def value(field):
                    index=columns.get(field)
                    return str(row['values'][index] or '').strip() if index is not None and index<len(row['values']) else ''
                if value('project_code')==project.project_code:
                    evidence.append(dict(file_id=file.id,filename=file.original_filename,sha256=file.sha256,
                        sheet=sheet['name'],row=row['row'],activity_code=value('activity_code')))
        codes=sorted({e['activity_code'] for e in evidence if e['activity_code']})
        matches=[re.fullmatch(r'([A-Za-z0-9_/-]*?)([0-9]+)',code) for code in codes]
        pattern=''
        if codes and len(codes)==len({e['activity_code'] for e in evidence}) and all(matches):
            shapes={(m[1],len(m[2])) for m in matches}
            if len(shapes)==1:
                prefix,length=next(iter(shapes));pattern=prefix+'[0-9]{'+str(length)+'}'
        ref=('planning:'+fingerprint(documents)+':'+str(pid)) if evidence else ''
        result.append(dict(project_id=pid,project_code=project.project_code,project_name=project.name,
            version='source-v1',code_pattern=pattern,sample_code=codes[0] if codes else '',source_ref=ref,
            evidence=evidence,review_required=not bool(pattern) or any(not e['activity_code'] for e in evidence)))
    return result


def view(db,principal,conversation,documents):
    from .project_discovery import discover_projects
    project_ids=[p['project_id'] for p in discover_projects(db,principal,documents)['projects'] if p['matched_rows']]
    items=proposals(db,principal,conversation,documents,project_ids)
    if not items:return None
    from .column_mappings import REQUIRED
    from .models import PlanningCodeContract
    missing_contracts=[pid for pid in project_ids if db.get(PlanningCodeContract,pid) is None]
    return dict(contract_candidates=planning_format_candidates(db,documents,items[0].sheets,missing_contracts) if all(x.status=='confirmed' for x in items) else [],missing_contracts=missing_contracts,categories={k:sorted(v) for k,v in REQUIRED.items()},fingerprint=fingerprint(documents),project_ids=project_ids,
                confirmed=all(x.status=='confirmed' for x in items),
                automatic=all(x.status=='confirmed' and x.confirmed_by is None for x in items),
                sheets=items[0].sheets,errors=mapping_errors(items[0].sheets))


@router.get('/{conversation_id}')
def get(conversation_id:UUID,principal:Authenticated,db:Database):
    conversation=db.get(Conversation,str(conversation_id))
    if conversation is None or conversation.owner_id!=principal.user.id:raise HTTPException(404,'Conversation unavailable')
    docs=resolve_documents(db,principal,conversation.id,None,[])
    return view(db,principal,conversation,docs)


class Mapping(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    file_id:str
    sheet_index:int=Field(ge=0,le=11)
    kind:str
    columns:dict[str,int]=Field(max_length=20)


class Confirmation(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    fingerprint:str=Field(pattern='^[a-f0-9]{64}$')
    sheets:list[Mapping]=Field(min_length=1,max_length=240)


@router.post('/{conversation_id}/confirm')
def confirm(conversation_id:UUID,body:Confirmation,request:Request,principal:Authenticated,db:Database):
    require_csrf(request,principal)
    db.rollback();db.execute(text('BEGIN IMMEDIATE'))
    principal=current_principal(request,db);require_csrf(request,principal);principal.require('projects:manage')
    conversation=db.get(Conversation,str(conversation_id))
    if conversation is None or conversation.owner_id!=principal.user.id:raise HTTPException(404,'Conversation unavailable')
    docs=resolve_documents(db,principal,conversation.id,None,[])
    from .conversation_workflow import check_integrity
    check_integrity(request.app.state.config,docs)
    if fingerprint(docs)!=body.fingerprint:raise HTTPException(409,'Source scope changed; review current mappings')
    from .project_discovery import discover_projects
    project_ids=[p['project_id'] for p in discover_projects(db,principal,docs)['projects'] if p['matched_rows']]
    items=proposals(db,principal,conversation,docs,project_ids)
    if len(items)!=len(project_ids) or not items:raise HTTPException(409,'Request processing to create the current review')
    supplied={(s.file_id,s.sheet_index):s for s in body.sheets}
    expected={(s['file_id'],s['sheet_index']) for s in items[0].sheets}
    if set(supplied)!=expected or len(supplied)!=len(body.sheets):raise HTTPException(422,'Confirm every original sheet exactly once')
    for item in items:
        principal.require('timesheets.view',item.project_id)
        candidate=copy.deepcopy(item.sheets)
        for sheet in candidate:
            chosen=supplied[sheet['file_id'],sheet['sheet_index']]
            sheet.update(kind=chosen.kind,columns=chosen.columns,conflicts=[])
        errors=mapping_errors(candidate)
        if errors:raise HTTPException(422,' '.join(errors))
        if item.status=='confirmed' and item.confirmed_by is not None and candidate!=item.sheets:
            raise HTTPException(409,'Confirmed mappings are immutable')
        item.sheets=candidate;item.status='confirmed';item.confirmed_by=principal.user.id;item.confirmed_at=int(time())
        audit(db,'global_mapping_confirmed',principal.user.id,resource_type='mapping_proposal',resource_id=item.id,outcome='format_only_not_financial_approval')
    db.flush()
    goal=db.scalar(select(WorkflowRun.workflow_id).where(WorkflowRun.actor_id==principal.user.id,
        WorkflowRun.request_key.like(f'global:{conversation.id}:%'),WorkflowRun.workflow_id!='show_issues').order_by(WorkflowRun.id.desc()).limit(1)) or 'process_activity'
    from .global_workflow import run_global_workflow
    request_id=str(uuid4())
    reply=run_global_workflow(db,principal,request.app.state.config,conversation,docs,workflow_id=goal,request_id=request_id)
    db.add(ChatTurn(conversation_id=conversation.id,request_id=request_id,prompt='Confirmed source column mappings for all matched projects.',
        reply=reply,created_at=int(time()),context={'request':{'project_id':None},'source_ids':[f.id for f,_ in docs]}))
    db.commit()
    return {'message':reply,'mapping':view(db,principal,conversation,docs)}


def resume_after_evidence(db,principal,config,conversation,documents):
    goal=db.scalar(select(WorkflowRun.workflow_id).where(WorkflowRun.actor_id==principal.user.id,
        WorkflowRun.request_key.like(f'global:{conversation.id}:%'),WorkflowRun.workflow_id!='show_issues').order_by(WorkflowRun.id.desc()).limit(1))
    if not goal or goal in {'analyze_intake','show_issues'}:return None
    principal.require('projects:manage')
    from .global_workflow import run_global_workflow
    request_id=str(uuid4())
    reply=run_global_workflow(db,principal,config,conversation,documents,workflow_id=goal,request_id=request_id)
    db.add(ChatTurn(conversation_id=conversation.id,request_id=request_id,prompt='Continue the previously requested workflow after evidence confirmation.',
        reply=reply,created_at=int(time()),context={'request':{'project_id':None},'source_ids':[f.id for f,_ in documents]}))
    db.flush()
    return reply


class SourceFormat(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    version:str=Field(min_length=1,max_length=80)
    code_pattern:str=Field(min_length=1,max_length=128)
    sample_code:str=Field(min_length=1,max_length=88)
    source_ref:str=Field(min_length=5,max_length=500)
    approved_source_format:bool
    conversation_id:str
    source_fingerprint:str|None=None


@router.post('/contracts/{project_id}')
def source_contract(project_id:int,body:SourceFormat,request:Request,principal:Authenticated,db:Database):
    from .models import PlanningCodeContract
    from .planning_activities import valid_activity_code
    from types import SimpleNamespace
    require_csrf(request,principal);principal.require('settings:read');principal.require('projects:manage')
    principal.require('timesheets.view',project_id)
    if not body.approved_source_format or not valid_activity_code(SimpleNamespace(code_pattern=body.code_pattern),body.sample_code):
        raise HTTPException(422,'An approved bounded source format matching the source example is required')
    conversation=db.get(Conversation,body.conversation_id)
    if conversation is None or conversation.owner_id!=principal.user.id:raise HTTPException(404,'Conversation unavailable')
    documents=resolve_documents(db,principal,conversation.id,None,[])
    from .conversation_workflow import check_integrity
    check_integrity(request.app.state.config,documents)
    if body.source_fingerprint is not None and body.source_fingerprint!=fingerprint(documents):
        raise HTTPException(409,'Source scope changed; review the current proposal')
    items=proposals(db,principal,conversation,documents,[project_id])
    if not items or items[0].status!='confirmed':raise HTTPException(409,'Confirm planning column mappings first')
    candidate=planning_format_candidates(db,documents,items[0].sheets,[project_id])[0]
    codes=[e['activity_code'] for e in candidate['evidence']]
    if not codes or body.sample_code not in codes or any(not valid_activity_code(SimpleNamespace(code_pattern=body.code_pattern),code) for code in codes):
        raise HTTPException(422,'The approved format and example must match every original planning activity code for this project')
    current=db.get(PlanningCodeContract,project_id)
    if current and (current.code_pattern!=body.code_pattern or current.version!=body.version or current.source_ref!=body.source_ref):
        raise HTTPException(409,'Existing approved source format differs; historical activity identities require explicit administrative reconciliation')
    if current is None:
        db.add(PlanningCodeContract(project_id=project_id,version=body.version,code_pattern=body.code_pattern,
            source_ref=body.source_ref,approved_by=principal.user.id,approved_at=int(time())))
        audit(db,'planning_code_contract_approved',principal.user.id,resource_type='project',resource_id=str(project_id),outcome=body.version)
        db.flush()
    documents=resolve_documents(db,principal,conversation.id,None,[])
    resumed=resume_after_evidence(db,principal,request.app.state.config,conversation,documents)
    db.commit();return {'project_id':project_id,'version':body.version,'message':resumed}
