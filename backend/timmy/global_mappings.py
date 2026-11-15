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
            item=MappingProposal(conversation_id=conversation.id,actor_id=principal.user.id,project_id=project,
                fingerprint=digest,version=version,sheets=confirmed or copy.deepcopy(sheets),created_at=int(time()),
                status='confirmed' if confirmed else 'proposed',confirmed_by=principal.user.id if confirmed else None,
                confirmed_at=int(time()) if confirmed else None)
            db.add(item);db.flush()
        if item:result.append(item)
    return result


def view(db,principal,conversation,documents):
    from .project_discovery import discover_projects
    project_ids=[p['project_id'] for p in discover_projects(db,principal,documents)['projects'] if p['matched_rows']]
    items=proposals(db,principal,conversation,documents,project_ids)
    if not items:return None
    from .column_mappings import REQUIRED
    from .models import PlanningCodeContract
    missing_contracts=[pid for pid in project_ids if db.get(PlanningCodeContract,pid) is None]
    return dict(missing_contracts=missing_contracts,categories={k:sorted(v) for k,v in REQUIRED.items()},fingerprint=fingerprint(documents),project_ids=project_ids,
                confirmed=all(x.status=='confirmed' for x in items),
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
        if item.status=='confirmed' and candidate!=item.sheets:raise HTTPException(409,'Confirmed mappings are immutable')
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
