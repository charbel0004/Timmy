"""Persisted conversation progression, human mapping decisions and truthful status.

All calls run under the chat/API transaction and refreshed principal. The only
validation performed here is structural; source/identity/report/payment authority
remains separate. No background queue is created or claimed.
"""
import copy
import json
import re
from datetime import datetime, timezone
from hashlib import sha256
from time import time

from fastapi import HTTPException
from sqlalchemy import select, func

from .audit import audit
from .column_mappings import SCHEMA_VERSION, REQUIRED, OPTIONAL, propose_sheet, mapping_errors, mapped_documents, reuse_approved_formats
from .documents import resolve_documents, project_report_cutoffs
from .models import EvidenceReview, MappingProposal, StructuralValidation, WorkflowRun
from .workflows import run_workflow, render_run, choose_workflow
from .session_preview import escape

CONFIRM = re.compile(r'^(yes+s*|yess+|confirmed|confirm|ok(?:ay)?|proceed|continue|نعم|موافق|تم التأكيد)[.!\s]*$',re.I)
MAPPING_CONFIRM = re.compile(r'^(?:column )?mappings? confirmed[.!\s]*(?:proceed)?[.!\s]*$',re.I)
STATUS = re.compile(r'\b(status|progress|is it done|where is it|is it finished|still running|how long|processing ongoing)\b|هل انتهى|حالة المعالجة',re.I)


def utc_stamp():
    return datetime.now(timezone.utc).isoformat()


def fresh_documents(db, principal, conversation, project_id, document_ids):
    return resolve_documents(db,principal,conversation.id,project_id,document_ids)


def fingerprint(documents):
    return sha256(json.dumps([SCHEMA_VERSION,[(f.id,f.sha256,r.sheets) for f,r in sorted(documents,key=lambda row:row[0].id)]],
                             ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def check_integrity(config, documents):
    for file,_ in documents:
        try:
            data=(config.document_root.expanduser()/file.id).read_bytes()
        except OSError:
            raise HTTPException(409,'SOURCE_INTEGRITY_FAILED: original evidence is unavailable') from None
        if len(data)!=file.size_bytes or sha256(data).hexdigest()!=file.sha256:
            raise HTTPException(409,'SOURCE_INTEGRITY_FAILED: original evidence does not match its digest')


def save_state(conversation, state):
    # Assign a new JSON object so SQLAlchemy tracks every nested transition.
    conversation.workflow_state=copy.deepcopy(state)


def require_scope(db,principal,conversation,state):
    scope=state.get('scope')
    if not scope:
        return []
    documents=fresh_documents(db,principal,conversation,scope.get('selector_project_id',scope['project_id']),scope.get('document_ids',[]))
    if fingerprint(documents)!=scope['fingerprint']:
        raise HTTPException(409,'Mapping proposal is stale: files or scope changed. Request Process to review a new proposal.')
    return documents


def proposal_view(proposal):
    return dict(id=proposal.id,version=proposal.version,fingerprint=proposal.fingerprint,
                status=proposal.status,confirmation_method='verified_format_reuse' if any(s.get('verified_format_ref') for s in proposal.sheets) else 'human_review',sheets=proposal.sheets,confirmed_at=proposal.confirmed_at,
                confirmed_by=proposal.confirmed_by,
                categories={kind:sorted(fields | OPTIONAL.get(kind,set())) for kind,fields in REQUIRED.items()})


def public_state(db,principal,conversation):
    state=copy.deepcopy(conversation.workflow_state or {'stage':'FILES_RECEIVED','validation':None})
    if state.get('scope'):
        # Recheck access to every stored source even if the original selector changed.
        scope=state['scope']
        resolve_documents(db,principal,conversation.id,scope['project_id'],scope['source_ids'])
    proposal=db.get(MappingProposal,state.get('mapping_id')) if state.get('mapping_id') else None
    state['mapping']=proposal_view(proposal) if proposal else None
    if state.get('scope'):
        try:
            require_scope(db,principal,conversation,state)
            state['scope_fresh']=True
        except HTTPException as error:
            if error.status_code not in (409,422): raise
            state['scope_fresh']=False
            state['blockers']=['SOURCE_SCOPE_CHANGED: request Process for a fresh proposal']
            if state['mapping']: state['mapping']['effective_status']='stale'
    review_id = (state.get("validation") or {}).get("review_id")
    if review_id and state.get("scope_fresh"):
        validation = db.get(StructuralValidation, review_id)
        if validation and validation.project_id == state["scope"]["project_id"]:
            latest = {}
            for review in db.scalars(select(EvidenceReview).where(
                    EvidenceReview.validation_id == review_id).order_by(EvidenceReview.id.desc())):
                latest.setdefault((review.project_code, review.activity_code, review.kind), review.decision)
            for kind, blocker in (("planning", "PLANNING_APPROVAL_EVIDENCE_REQUIRED"),
                                  ("staff", "STAFF_VERIFICATION_REQUIRED")):
                if all(latest.get((row["project_code"], row["activity_code"], kind)) == "confirmed"
                       for row in validation.snapshot["activities"]):
                    state["blockers"] = [code for code in state["blockers"] if code != blocker]
    return state


def status_text(state):
    if not state.get('scope'):
        return 'No processing run has been recorded for this conversation. Analyze or Process the selected files first.'
    lines=[f"Workflow stage: {state['stage']}.",
           f"Scope: project {state['scope']['project_id']}, {len(state['scope']['source_ids'])} files, {state['scope']['source_rows']} source rows."]
    if state.get('intake_run_id'):
        lines.append(f"Intake run #{state['intake_run_id']} verified stored evidence; intake is not activity validation.")
    validation=state.get('validation')
    if validation:
        lines.append(f"Structural validation: {validation['status']}; run #{validation.get('run_id','unavailable')}.")
        if validation.get("review_id"):
            lines.append(f"Review planning and staff evidence in [Timesheet Imports](#imports/validation/{validation['review_id']}) under saved validation #{validation['review_id']}.")
        for key in ('started_at','completed_at','error_code'):
            if validation.get(key): lines.append(f'{key}: {validation[key]}.')
        if validation.get('status')=='failed':lines.append('Processing failed; it is not running in a background queue.')
    else:
        lines.append('No processing run is running. Structural validation has not started.')
    if state.get('stage')=='MAPPING_UNDER_REVIEW':
        lines.append('Confirm the exact mapping proposal, or specify the unresolved source columns. No background queue exists for this synchronous operation.')
    if state.get('blockers'):
        lines.append('Blockers: '+', '.join(state['blockers'])+'.')
    if state.get('registered_activities'):
        identities=sorted({f"{item['activity_code']} (activity #{item['activity_id']})" for item in state['registered_activities']})
        lines.append('Planning activities: '+', '.join(identities)+'.')
    if state.get('result'):
        if (state.get('validation') or {}).get('review_id'):
            lines.append('### Structural check at time of run')
        lines.append(state['result'])
    return '\n'.join(lines)


def proposal_text(proposal, scope):
    lines=[f'Mapping proposal {proposal.id}, version {proposal.version}: MAPPING_UNDER_REVIEW.',
           f"Scope: {len(scope['source_ids'])} files, {scope['source_rows']} source rows. This is column interpretation, not identity/report/payment approval."]
    for sheet in proposal.sheets:
        fields=', '.join(f'{field} ← column {index+1} ({escape(sheet["headers"][index])})' for field,index in sorted(sheet['columns'].items())) or 'no supported fields'
        lines.append(f"- {escape(sheet['filename'])} / sheet {sheet['sheet_index']+1}: {sheet['kind']}; {fields}.")
    errors=mapping_errors(proposal.sheets)
    if errors:
        lines.append('Cannot confirm yet:\n'+'\n'.join(escape(error) for error in errors))
    else:
        lines.append('Reply Confirmed to accept this exact proposal and run structural session checks. Required authority checks will remain blocked until independently verified.')
    return '\n'.join(lines)


def prepare_scope(db,principal,config,conversation,project_id,document_ids):
    old=conversation.workflow_state or {}
    selector=old.get('scope',{})
    if not document_ids and selector and project_id in (None,selector.get('project_id')):
        project_id=selector.get('selector_project_id',selector.get('project_id'))
        document_ids=selector.get('document_ids',[])
    selector_project_id=project_id
    documents=fresh_documents(db,principal,conversation,project_id,document_ids)
    check_integrity(config,documents)
    projects={file.project_id for file,_ in documents}
    if project_id is None:
        project_id=next(iter(projects)) if len(projects)==1 else None
    if project_id is None or not documents:
        raise HTTPException(422,'Select one project and its files in Context; no accessible intake evidence was found in a single project.')
    principal.require('projects:manage')
    principal.require('timesheets.view',project_id)
    return documents,dict(project_id=project_id,selector_project_id=selector_project_id,document_ids=sorted(str(v) for v in document_ids),
                          source_ids=sorted(file.id for file,_ in documents),source_rows=sum(r.row_count for _,r in documents),
                          fingerprint=fingerprint(documents))


def start_mapping(db,principal,config,conversation,project_id,document_ids,force_new=False):
    documents,scope=prepare_scope(db,principal,config,conversation,project_id,document_ids)
    state=copy.deepcopy(conversation.workflow_state or {})
    prior=None
    if state.get('scope',{}).get('fingerprint')==scope['fingerprint'] and state.get('mapping_id'):
        proposal=db.get(MappingProposal,state['mapping_id'])
        prior=proposal
        if not force_new:
            if proposal.status=='confirmed':
                return complete_validation(db,principal,config,conversation,proposal,documents,state)
            return proposal_text(proposal,scope)
    # Reuse verified interpretation only for exactly the same actor/file scope.
    # A deliberate correction creates a new review version, never overwrites it.
    sheets=copy.deepcopy(prior.sheets) if prior else [propose_sheet(file,sheet,index)
        for file,record in documents for index,sheet in enumerate(record.sheets)]
    version=(db.scalar(select(func.max(MappingProposal.version)).where(MappingProposal.conversation_id==conversation.id)) or 0)+1
    proposal=MappingProposal(conversation_id=conversation.id,actor_id=principal.user.id,project_id=scope['project_id'],
                             fingerprint=scope['fingerprint'],version=version,sheets=sheets,created_at=int(time()),status='proposed')
    # Approved column formats are reusable for this actor/project. Row values,
    # identity verification and planning/report approval are never inherited.
    reuse=reuse_approved_formats(db,principal.user.id,scope['project_id'],sheets) if not force_new else []
    db.add(proposal);db.flush()
    state=dict(scope=scope,stage='MAPPING_UNDER_REVIEW',mapping_id=proposal.id,pending='confirm_mapping',
               intake_run_id=state.get('intake_run_id') if state.get('scope',{}).get('fingerprint')==scope['fingerprint'] else None,
               validation=None,blockers=mapping_errors(sheets),milestones=['FILES_RECEIVED','FILES_IMPORTED','MAPPING_REQUIRED','MAPPING_UNDER_REVIEW'])
    save_state(conversation,state)
    if len(reuse)==len(sheets) and reuse and not mapping_errors(reuse):
        proposal.sheets=reuse;proposal.status='confirmed';proposal.confirmed_at=int(time());proposal.confirmed_by=principal.user.id
        db.flush()
        audit(db,'column_mapping_reused',principal.user.id,resource_type='mapping_proposal',resource_id=proposal.id,
              outcome='verified_format_reuse')
        return complete_validation(db,principal,config,conversation,proposal,documents,state)
    audit(db,'mapping_proposed',principal.user.id,resource_type='mapping_proposal',resource_id=proposal.id,outcome='human_review_required')
    return proposal_text(proposal,scope)


def complete_validation(db,principal,config,conversation,proposal,documents,state):
    from .planning_activities import register_planning
    try:
        with db.begin_nested():
            prepared,registered=register_planning(db,principal,mapped_documents(documents,proposal.sheets),proposal.sheets,proposal.id)
        state['registered_activities']=registered
    except HTTPException as error:
        state.update(stage='HUMAN_REVIEW_REQUIRED',pending=None,validation=None,blockers=[str(error.detail)])
        state['result']='Planning activity registration is blocked. Correct the source evidence; no financial eligibility was created.'
        save_state(conversation,state)
        return status_text(state)
    cutoffs=project_report_cutoffs(db,proposal.project_id)
    evidence_fingerprint=sha256(json.dumps(["review-handoff-v1",proposal.fingerprint,proposal.sheets,
        [[list(k),v] for k,v in sorted(cutoffs.items())]],sort_keys=True).encode()).hexdigest()
    if (state.get('validation') and state['validation']['status']=='completed'
            and state['validation'].get('evidence_fingerprint')==evidence_fingerprint):
        return status_text(state)
    if not any(sheet['kind']=='claims' for sheet in proposal.sheets):
        state.update(stage='HUMAN_REVIEW_REQUIRED',pending=None,blockers=['TIMESHEET_CLAIMS_REQUIRED'])
        save_state(conversation,state)
        return status_text(state)
    state['stage']='VALIDATION_RUNNING'
    state['validation']={'status':'running','started_at':utc_stamp(),'evidence_fingerprint':evidence_fingerprint}
    save_state(conversation,state);db.flush()
    try:
        # Keep a failure from rolling back the separately verified mapping decision.
        with db.begin_nested():
            snapshot = {"claims": [], "activities": []}
            run=run_workflow(db,principal,config,workflow_id='process_activity',project_id=proposal.project_id,
                             request_key=f'mapping:{proposal.id}:{evidence_fingerprint}',conversation_id=conversation.id,
                             document_ids=state['scope']['source_ids'],
                             prepared_documents=prepared, mapping_ref=proposal.id,
                             structural_snapshot=snapshot)
            if snapshot["activities"]:
                review = StructuralValidation(project_id=proposal.project_id, actor_id=principal.user.id,
                                              fingerprint=run.fingerprint, created_at=int(time()), snapshot=snapshot)
                db.add(review)
                db.flush()
                state["validation"]["review_id"] = review.id
            state['validation'].update(status='completed',run_id=run.id,completed_at=utc_stamp())
            state['result']=render_run(run)
            state['stage']='HUMAN_REVIEW_REQUIRED'
            state['blockers']=['STAFF_VERIFICATION_REQUIRED','PLANNING_APPROVAL_EVIDENCE_REQUIRED']
            if any('REPORT_VALIDATION_EVIDENCE_REQUIRED' in step['issue_codes'] for step in run.snapshot['steps']):
                state['blockers'].append('REPORT_VALIDATION_EVIDENCE_REQUIRED')
    except Exception:
        # Never serialize exception text: parsed rows, destinations and credentials may occur there.
        state['validation'].update(status='failed',completed_at=utc_stamp(),error_code='STRUCTURAL_VALIDATION_FAILED')
        state['stage']='VALIDATION_FAILED';state['blockers']=['STRUCTURAL_VALIDATION_FAILED']
        state.pop('result',None)
    state['pending']=None
    state.setdefault('milestones',[]).extend(['MAPPING_CONFIRMED','IDENTITY_VERIFICATION_REQUIRED',
        'VALIDATION_READY','VALIDATION_RUNNING',
        'VALIDATION_COMPLETED' if state['validation']['status']=='completed' else 'VALIDATION_FAILED',state['stage']])
    save_state(conversation,state)
    audit(db,'conversation_validation_finished',principal.user.id,resource_type='mapping_proposal',resource_id=proposal.id,
          outcome=state['validation']['status'])
    return status_text(state)


def confirm_mapping(db,principal,config,conversation,proposal_id,version,fingerprint_value,selections=None):
    state=copy.deepcopy(conversation.workflow_state or {})
    principal.require('projects:manage')
    proposal=db.get(MappingProposal,proposal_id)
    if (not proposal or proposal.conversation_id!=conversation.id or proposal.actor_id!=principal.user.id
            or state.get('mapping_id')!=proposal.id):
        raise HTTPException(404,'No active mapping proposal is available in this conversation')
    principal.require('timesheets.view',proposal.project_id)
    if proposal.version!=version or proposal.fingerprint!=fingerprint_value:
        raise HTTPException(409,'Mapping proposal version is stale; retrieve the active proposal before confirming')
    documents=require_scope(db,principal,conversation,state)
    check_integrity(config,documents)
    candidate=copy.deepcopy(proposal.sheets)
    if selections is not None:
        selected={(str(s.file_id),s.sheet_index):s for s in selections}
        expected={(s['file_id'],s['sheet_index']) for s in candidate}
        if set(selected)!=expected or len(selections)!=len(expected):
            raise HTTPException(422,'Supply one mapping for every file/sheet in this proposal; no omissions or duplicates')
        for sheet in candidate:
            selection=selected[sheet['file_id'],sheet['sheet_index']]
            sheet.update(kind=selection.kind,columns=selection.columns,conflicts=[])
    errors=mapping_errors(candidate)
    if errors:
        raise HTTPException(422,'Mapping not confirmed: '+' '.join(errors))
    if proposal.status=='confirmed' and candidate!=proposal.sheets:
        raise HTTPException(409,'Confirmed mapping is immutable; request a new version for a correction')
    if proposal.status!='confirmed':
        proposal.sheets=candidate;proposal.status='confirmed';proposal.confirmed_at=int(time());proposal.confirmed_by=principal.user.id
        db.flush()
        audit(db,'column_mapping_confirmed',principal.user.id,resource_type='mapping_proposal',resource_id=proposal.id,
              outcome='confirmed',trigger='human_confirmation')
    state['stage']='MAPPING_CONFIRMED';save_state(conversation,state)
    return complete_validation(db,principal,config,conversation,proposal,documents,state)


def handle_message(db,principal,config,conversation,message,project_id,document_ids,request_id):
    """Return None only for non-workflow conversation. No model status/confirmation."""
    state=copy.deepcopy(conversation.workflow_state or {})
    if not state:
        # Published conversations may predate the pending-action column. Recover
        # only from a real, completed intake receipt, never from model prose.
        previous=db.scalar(select(WorkflowRun).where(
            WorkflowRun.actor_id==principal.user.id,
            WorkflowRun.request_key.like(f'chat:{conversation.id}:%')
        ).order_by(WorkflowRun.id.desc()).limit(1))
        if previous and previous.workflow_id=='analyze_intake' and previous.status=='completed':
            ids=previous.snapshot.get('source_ids',[])
            if ids:
                documents=fresh_documents(db,principal,conversation,previous.project_id,ids)
                check_integrity(config,documents)
                scope=dict(project_id=previous.project_id,selector_project_id=previous.project_id,
                           document_ids=ids,source_ids=ids,source_rows=sum(r.row_count for _,r in documents),
                           fingerprint=fingerprint(documents))
                state=dict(scope=scope,stage='INTAKE_VERIFIED',intake_run_id=previous.id,mapping_id=None,
                           pending='process',validation=None,milestones=['INTAKE_VERIFIED'])
                save_state(conversation,state)
    if STATUS.search(message):
        if not state and previous:
            # A legacy run is historical evidence, not proof of a live queue.
            resolve_documents(db,principal,conversation.id,previous.project_id,previous.snapshot.get('source_ids',[]))
            return render_run(previous)+'\nThis is a recorded synchronous result; no background queue is running.'
        return status_text(public_state(db,principal,conversation))
    if re.fullmatch(r'(revise|correct|change) (?:column )?mappings?[.!\s]*',message.strip(),re.I):
        return start_mapping(db,principal,config,conversation,project_id,document_ids,force_new=True)
    confirmation=bool(CONFIRM.fullmatch(message.strip()) or MAPPING_CONFIRM.fullmatch(message.strip()))
    if confirmation:
        if not state.get('pending') and not state.get('mapping_id'):
            return 'No pending processing or mapping decision exists. Ask Analyze or Process for the selected files.'
        if state.get('scope'):
            # An explicit new scope must never approve the old pending proposal.
            if project_id is not None and project_id!=state['scope']['project_id']:
                return 'Mapping proposal is stale for this project selection. Request Process to review its files.'
            if document_ids and sorted(str(i) for i in document_ids)!=state['scope'].get('document_ids',[]):
                return 'Mapping proposal is stale for this file selection. Request Process to review its files.'
        try:
            if state.get('pending')=='process':
                require_scope(db,principal,conversation,state)
                return start_mapping(db,principal,config,conversation,None,[])
            proposal=db.get(MappingProposal,state.get('mapping_id'))
            if proposal:
                return confirm_mapping(db,principal,config,conversation,proposal.id,proposal.version,proposal.fingerprint)
        except HTTPException as error:
            if error.status_code in (409,422):return str(error.detail)
            raise
        return status_text(state)
    selected=choose_workflow(message)
    if selected not in {'analyze_intake','process_activity'}:
        return None
    try:
        if selected=='process_activity':
            return start_mapping(db,principal,config,conversation,project_id,document_ids)
        documents,scope=prepare_scope(db,principal,config,conversation,project_id,document_ids)
        run=run_workflow(db,principal,config,workflow_id='analyze_intake',project_id=scope['project_id'],
                         conversation_id=conversation.id,document_ids=scope['source_ids'],request_key=f'chat:{conversation.id}:{request_id}')
        if state.get('scope',{}).get('fingerprint')!=scope['fingerprint'] or not state.get('scope'):
            state=dict(scope=scope,stage='INTAKE_VERIFIED',intake_run_id=run.id,mapping_id=None,pending='process',validation=None,
                       milestones=['FILES_RECEIVED','FILES_IMPORTED','INTAKE_VERIFIED'])
        save_state(conversation,state)
        return render_run(run)+('\n'+status_text(state) if state.get('mapping_id') else '')
    except HTTPException as error:
        if error.status_code in (409,422):return str(error.detail)
        raise
