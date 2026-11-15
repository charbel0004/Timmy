"""One coordinator-global conversation, separately auditable per-project workflow receipts.

Confirmed source mappings connect planning registration, declared Excel report
evidence, human planning/staff reviews and deterministic payment preparation.
A mixed workbook remains one immutable original; project attribution comes
from source rows and verified reference codes, not the file's storage scope.
Financial approval and file export remain explicit authorized human actions.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from time import time

from fastapi import HTTPException
from sqlalchemy import select

from .audit import audit
from .models import WorkflowRun, WorkflowStepReceipt, projects
from .project_discovery import discover_projects, render_project_discovery
from .global_source_views import preview_documents_for_project
from .session_preview import preview
from .planning_activities import registry
from .documents import project_report_cutoffs
from .workflow_graph import execute_graph
from .workflows import knowledge, step_result


def run_global_workflow(db, principal, config, conversation, documents, *, workflow_id, request_id,
                        on_step=None):
    """Execute bounded, truthful LangGraph receipts per authorized project.

    The original workbook's bytes and owner are verified on each request.
    Each dependent step stops on missing evidence or authorization. Reconfirming
    evidence resumes the original goal without fabricating downstream progress.
    """
    definitions = {item.id: item for item in knowledge().workflows}
    if workflow_id not in definitions:
        raise HTTPException(422, "Unknown stored workflow")
    principal.require("projects:read")
    if workflow_id not in {"analyze_intake", "show_issues"}:
        principal.require("projects:manage")

    from .conversation_workflow import check_integrity  # Avoid import cycle.
    check_integrity(config, documents)
    overview = discover_projects(db, principal, documents)
    project_ids = [p["project_id"] for p in overview["projects"] if p["matched_rows"]]
    if not project_ids:
        return render_project_discovery(overview, processing_requested=True) + (
            "\nPROJECT_ROUTING_REVIEW_REQUIRED: No unambiguously matched project rows."
        )

    from .global_mappings import proposals
    mapping_by_project={p.project_id:p for p in proposals(db,principal,conversation,documents,project_ids,
        create=workflow_id in {'process_activity','weekly_cycle','prepare_payment'})}
    note = render_project_discovery(overview, workflow_receipts=True)
    report = [note, "\n### Actual project-specific workflow receipts"]
    for project_id in sorted(project_ids):
        principal.require("timesheets.view", project_id)
        if db.scalar(select(projects.c.status).where(projects.c.id == project_id)) != "active":
            raise HTTPException(409, "Project became inactive; request a new scope")
        project = next(p for p in overview["projects"] if p["project_id"] == project_id)
        proposal=mapping_by_project.get(project_id)
        confirmed=proposal is not None and proposal.status=='confirmed'
        prepared=documents
        if confirmed:
            from .column_mappings import mapped_documents
            prepared=mapped_documents(documents,proposal.sheets)
        scoped_views=preview_documents_for_project(prepared,project_id,project['project_code'])
        registration_issue=None
        if confirmed and workflow_id in {'process_activity','weekly_cycle','prepare_payment'}:
            from .planning_activities import register_planning
            try:
                with db.begin_nested():
                    register_planning(db,principal,scoped_views,proposal.sheets,proposal.id)
            except HTTPException as error:
                registration_issue=str(error.detail)
            from .reporting_register import synchronize_confirmed
            synchronize_confirmed(db,principal,config,documents)
        structural={'activities':[],'claims':[],'sheets':[
            {'file_id':f.id,'sheet':sheet['name']} for f,r in scoped_views for sheet in r.sheets]}
        activity_registry=registry(db,[project_id])
        cutoffs=project_report_cutoffs(db,project_id)
        provisional=None
        if project['policy_family']=='session' and scoped_views:
            provisional=preview(scoped_views,snapshot=structural,activity_registry=activity_registry,
                                report_cutoffs=cutoffs,project_codes={project_id:project['project_code']})
        elif project['policy_family']=='hours':
            from .hourly_preview import preview_hours
            provisional=preview_hours(prepared,project['project_code'],snapshot=structural)
            for key,activity in activity_registry.items():
                structural['activities'].append(dict(project_code=key[1],activity_code=key[2],activity_id=activity['id'],
                    structure='FLAGGED' if structural.get('hourly_parse_issues') or any(c['blockers'] for c in structural.get('hourly_candidates',[])) else 'PASSED',
                    session_pairs=0,role_slots=0,issues={},planning='PENDING',staff='PENDING',report='PENDING',
                    eligibility='BLOCKED',approval='PENDING',settlement='EXTERNAL',policy_family='hours',review_tasks=['PLANNING_APPROVAL_EVIDENCE_REQUIRED','STAFF_VERIFICATION_REQUIRED','REPORT_VALIDATION_EVIDENCE_REQUIRED']))
        from .column_mappings import propose_sheet
        structural['policy_issues']=[]
        expected_kind='claims' if project['policy_family']=='session' else 'hours'
        for file,record in scoped_views:
            for index,sheet in enumerate(record.sheets):
                kind=propose_sheet(file,sheet,index)['kind']
                if kind in {'claims','hours'} and kind!=expected_kind:
                    structural['policy_issues'].append('PROJECT_POLICY_SOURCE_TYPE_MISMATCH')
        if project['policy_family']=='hours':
            directory={}
            for _,record in scoped_views:
                for sheet in record.sheets:
                    if not sheet.get('rows'):continue
                    headers=sheet['rows'][0]['values']
                    if {'staff_id','status'}<=set(headers):
                        for row in sheet['rows'][1:]:
                            entry=dict(zip(headers,row['values']))
                            directory.setdefault(str(entry.get('staff_id') or ''),set()).add(str(entry.get('status') or '').casefold())
                    if {'activity_code','approval_status'}<=set(headers):
                        for row in sheet['rows'][1:]:
                            entry=dict(zip(headers,row['values']))
                            if str(entry.get('approval_status') or '').upper()!='APPROVED':
                                structural['policy_issues'].append('PLANNING_STATUS_NOT_APPROVED')
            from .source_dates import source_date
            for shift in structural.get('hourly_shifts',[]):
                if shift['project_code']!=project['project_code']:continue
                if directory.get(shift['staff_id'])!={'active'}:
                    structural['policy_issues'].append('STAFF_NOT_MATCHED_TO_ACTIVE_DIRECTORY')
                key=(project_id,shift['project_code'],shift['activity_code'])
                plan=activity_registry.get(key)
                day=source_date(shift['start'][:10])
                end_day=source_date(shift['end'][:10])
                if not plan or not (plan['planned_start']<=str(day)<=plan['planned_end'] and plan['planned_start']<=str(end_day)<=plan['planned_end']):
                    structural['policy_issues'].append('SHIFT_OUTSIDE_APPROVED_PLANNING')
                report_evidence=cutoffs.get(key)
                if report_evidence and (str(day)>report_evidence['cutoff'] or str(end_day)>report_evidence['cutoff']):
                    structural['policy_issues'].append('AFTER_VALIDATED_REPORT_CUTOFF')
        recommendations={
            'STAFF_NOT_MATCHED_TO_ACTIVE_DIRECTORY':'Check the exact staff ID against the independently verified directory; resolve inactive or ambiguous identities before approval.',
            'MISSING_SESSION_DATE':'Review the original date cell and confirmed mapping; obtain a corrected authoritative date rather than inventing one.',
            'MISSING_OR_INVALID_SUBMISSION_DATE':'Correct or map the original submission date; preserve the original cell and evidence reference.',
            'DUPLICATE_CLAIM':'Retain both originals, verify whether they represent the same occurrence, and obtain an authorized exclusion/correction before recalculating.',
            'PLANNING_STATUS_NOT_APPROVED':'Obtain current approved planning evidence; an uploaded retired/pending/rejected row cannot release payment.',
            'PROJECT_POLICY_SOURCE_TYPE_MISMATCH':'Correct the project attribution or source category against approved planning; do not calculate an hourly row under a session policy.',
            'AFTER_VALIDATED_REPORT_CUTOFF':'Keep the frozen cutoff; seek reporting-team correction/review rather than extending it from a later resubmission.',
            'SHIFT_OUTSIDE_APPROVED_PLANNING':'Review the original shift and approved planning window; obtain a documented correction or keep the claim blocked.',
        }
        finding_codes={code for a in structural['activities'] for code in a.get('issues',{})}|set(structural['policy_issues'])
        structural['resolution_recommendations']={code:recommendations.get(code,'Review the exact original rows and applicable deterministic rule; obtain an authorized evidence correction or decision before recalculating.') for code in sorted(finding_codes)}
        validation=None
        if confirmed and structural['activities']:
            from .models import StructuralValidation
            validation_key=sha256(json.dumps(['global-structural-v2',proposal.id,sorted((str(k),v) for k,v in cutoffs.items()),
                                           sorted(str(k) for k in activity_registry)],sort_keys=True).encode()).hexdigest()
            validation=db.scalar(select(StructuralValidation).where(StructuralValidation.project_id==project_id,
                                                                    StructuralValidation.fingerprint==validation_key))
            if validation is None and workflow_id!='show_issues':
                validation=StructuralValidation(project_id=project_id,actor_id=principal.user.id,
                    fingerprint=validation_key,created_at=int(time()),snapshot=structural)
                db.add(validation);db.flush()
        def reviewed(kind):
            if validation is None:return False
            from .models import EvidenceReview
            for activity in structural['activities']:
                decision=db.scalar(select(EvidenceReview.decision).where(EvidenceReview.validation_id==validation.id,
                    EvidenceReview.kind==kind,EvidenceReview.project_code==activity['project_code'],
                    EvidenceReview.activity_code==activity['activity_code']).order_by(EvidenceReview.id.desc()).limit(1))
                if decision!='confirmed':return False
            return bool(structural['activities'])
        original = sorted((f.id, f.sha256, r.row_count) for f, r in documents)
        fingerprint = sha256(json.dumps({
            "workflow_id": workflow_id, "knowledge": knowledge().version,
            "conversation_id": conversation.id, "actor_id": principal.user.id,
            "project_id": project_id, "sources": original,
            "row_discovery": overview,
        }, sort_keys=True).encode()).hexdigest()
        key = f"global:{conversation.id}:{request_id}:{project_id}"
        existing = db.scalar(select(WorkflowRun).where(
            WorkflowRun.actor_id == principal.user.id,
            WorkflowRun.request_key == key,
        ))
        if existing:
            if existing.fingerprint != fingerprint:
                raise HTTPException(409, "Workflow request identifier was reused with changed evidence")
            report.append(f"- Project {project_id}: existing run #{existing.id}, {existing.status}; "
                          "no steps replayed.")
            continue

        # Only a verified source checksum may complete intake. The row routing
        # is a *proposal*; it is not a confirmed planning or staff authority.
        payment_draft=None
        def evaluate(step):
            nonlocal payment_draft
            if step == "verify_intake":
                return step_result(step, "completed", files=len(documents),
                    project_rows=next(p["matched_rows"] for p in overview["projects"]
                                      if p["project_id"] == project_id),
                    provenance="original_file_sha256_verified",
                    project_mapping="provisional")
            if step == "show_discrepancies":
                return step_result(step, "completed",
                    issue_codes=list(overview["issue_counts"].keys()),
                    evidence_kind="provisional_project_routing")
            if overview['issue_counts']:
                return step_result(step,'blocked',['PROJECT_ROUTING_REVIEW_REQUIRED'],routing_issues=overview['issue_counts'])
            if not confirmed:
                return step_result(step,'needs_review',['PROJECT_SOURCE_MAPPING_CONFIRMATION_REQUIRED'])
            if step=='check_planning':
                if registration_issue:
                    return step_result(step,'blocked',['PLANNING_REGISTRATION_REVIEW_REQUIRED'],recommendation=registration_issue)
                return step_result(step,'completed' if reviewed('planning') else 'needs_review',
                    [] if reviewed('planning') else ['PLANNING_APPROVAL_EVIDENCE_REQUIRED'],
                    validation_id=validation.id if validation else None)
            if step=='check_reports':
                missing=[a['activity_code'] for a in structural['activities']
                         if (project_id,project['project_code'],a['activity_code']) not in cutoffs]
                return step_result(step,'blocked' if missing or not structural['activities'] else 'completed',
                    ['REPORT_VALIDATION_EVIDENCE_REQUIRED'] if missing or not structural['activities'] else [],missing_activities=missing)
            if step=='select_timesheets':
                return step_result(step,'completed' if reviewed('staff') else 'needs_review',
                    [] if reviewed('staff') else ['STAFF_VERIFICATION_REQUIRED'])
            if step=='validate_activity':
                issues=sorted({code for a in structural['activities'] for code in a.get('issues',{})})
                issues+=list(structural.get('hourly_parse_issues',[]))
                issues+=structural.get('policy_issues',[])
                issues+=sorted({code for c in structural.get('hourly_candidates',[]) for code in c['blockers']})
                return step_result(step,'needs_review' if issues else 'completed',issues,
                    validation_id=validation.id if validation else None)
            if step=='resolve_discrepancies':
                # This goal can be invoked alone, so graph ordering is not proof
                # that validation or its human prerequisites already passed.
                findings=sorted(finding_codes | set(structural.get('hourly_parse_issues',[])) |
                    {code for c in structural.get('hourly_candidates',[]) for code in c['blockers']})
                missing_reports=any((project_id,project['project_code'],a['activity_code']) not in cutoffs
                                    for a in structural['activities'])
                if findings:
                    return step_result(step,'needs_review',findings,
                        recommendation='Resolve the original source/evidence findings under approved policy and reprocess; no correction has been invented.')
                if registration_issue or not structural['activities'] or missing_reports or not reviewed('planning') or not reviewed('staff'):
                    return step_result(step,'needs_review',['VERIFIED_ACTIVITY_EVIDENCE_REQUIRED'],
                        recommendation='Complete planning, staff and report evidence reviews before recording resolution.')
                return step_result(step,'completed',[],recommendation='No unresolved structural findings remain; financial authority is still separate.')
            if step=='prepare_payment_request':
                from .workflow_payments import make_draft
                try:
                    payment_draft=make_draft(db,principal,conversation,documents,project,proposal,validation,structural)
                except HTTPException as error:
                    return step_result(step,'blocked',['PAYMENT_DRAFT_REVIEW_REQUIRED'],recommendation=str(error.detail))
                return step_result(step,'completed',[],draft_id=payment_draft.id,digest=payment_draft.digest)
            if step=='export_payment_request':
                from .models import WorkflowPaymentApproval, WorkflowPaymentExport
                if payment_draft is None:return step_result(step,'blocked',['PAYMENT_DRAFT_REQUIRED'])
                approved=db.scalar(select(WorkflowPaymentApproval.id).where(WorkflowPaymentApproval.draft_id==payment_draft.id))
                exported=db.scalar(select(WorkflowPaymentExport.id).where(WorkflowPaymentExport.draft_id==payment_draft.id))
                return step_result(step,'completed' if exported else 'needs_review',
                    [] if exported else ['EXACT_BATCH_APPROVAL_REQUIRED'] if not approved else ['APPROVED_FILE_READY_FOR_MANUAL_DOWNLOAD'],
                    draft_id=payment_draft.id,export_id=exported)
            return step_result(step,'blocked',['UNREGISTERED_WORKFLOW_STEP'])

        results = execute_graph(
            definitions[workflow_id].steps, evaluate,
            on_result=(lambda receipt: on_step(
                f"Project {project_id}: {receipt['step']} — {receipt['status']}" +
                (' (not executed; dependency hold)' if receipt.get('attempted') is False else ''))
                       if on_step else None),
        )
        status = ("blocked" if any(x["status"] == "blocked" for x in results)
                  else "needs_review" if any(x["status"] == "needs_review" for x in results)
                  else "completed")
        from .models import WorkflowPaymentApproval
        payment_authority=('exact_snapshot_human_approved' if payment_draft and db.scalar(select(WorkflowPaymentApproval.id).where(WorkflowPaymentApproval.draft_id==payment_draft.id))
                           else 'draft_not_approved' if payment_draft else 'none')
        run = WorkflowRun(
            actor_id=principal.user.id, project_id=project_id,
            request_key=key, fingerprint=fingerprint, workflow_id=workflow_id,
            knowledge_version=knowledge().version, created_at=int(time()),
            status=status, snapshot={
                "steps": results, "source_ids": [f.id for f, _ in documents],
                "source_sha256": {f.id:f.sha256 for f,_ in documents},
                "source_row_matches": next(p["matched_rows"] for p in overview["projects"]
                                           if p["project_id"] == project_id),
                "project_routing_issues": overview["issue_counts"],
                "project_routing_refs": overview["issue_references"],
                "resolution_recommendations":structural['resolution_recommendations'],
                "mapping_authority": "confirmed" if confirmed else "unconfirmed",
                "mapping_id":proposal.id if proposal else None,
                "structural_validation_id":validation.id if validation else None,
                "payment_authority": payment_authority,
                "provisional_structural_preview": provisional,
                "execution": {"mode": "synchronous",
                              "completed_at": datetime.now(timezone.utc).isoformat()},
            })
        db.add(run)
        db.flush()
        for index, result in enumerate(results):
            db.add(WorkflowStepReceipt(
                run_id=run.id, step_index=index, step_id=result["step"],
                status=result["status"], attempted=bool(result.get("attempted", True)),
                executed=bool(result.get("executed", False)),
                blocked_by=result.get("blocked_by"),
                issue_codes=result["issue_codes"], recorded_at=int(time()),
            ))
        db.flush()
        audit(db, "workflow_run_recorded", principal.user.id,
              resource_type="workflow_run", resource_id=str(run.id),
              outcome=status, trigger=workflow_id)
        report.append(f"- Project {project_id}: {workflow_id} run #{run.id} — {status}.")
        if structural['resolution_recommendations']:
            report.append('  Resolution recommendations (no unauthorized correction applied):')
            for code,recommendation in structural['resolution_recommendations'].items():
                report.append(f'  - {code}: {recommendation}')
        if provisional:
            report.append("  Provisional source-based policy checks (NOT authoritative validation):")
            report.append(provisional)
        from .workflow_contracts import CONTRACTS
        first_hold = next((r for r in results if r['status'] != 'completed'), None)
        if validation:
            report.append(f'  Evidence review: [Review planning and staff evidence](#imports/validation/{validation.id}).')
        if registration_issue:
            report.append('  Planning registration requires review: '+registration_issue)
        if first_hold:
            report.append('  Required next action: ' + CONTRACTS[first_hold['step']][2] + '.')
        for result in results:
            report.append(f"  - {result['step']}: {result['status']}"
                          + (f" ({', '.join(result['issue_codes'])})"
                             if result["issue_codes"] else ""))
            if result.get('recommendation'):
                report.append('    Next: '+result['recommendation'])
    if not any(p.status=='confirmed' for p in mapping_by_project.values()):
        report.append("No cross-project source registration, identity confirmation, report validation, payment eligibility, export or settlement was performed.")
    else:
        report.append("Original sources and evidence decisions are preserved. Only completed receipts above establish progress; actual payment transfers and settlement remain external.")
    return "\n".join(report)


def global_workflow_status(db, principal, conversation, documents):
    """Read the last committed workflow receipts; never claim a queued job."""
    principal.require("projects:read")
    runs = db.scalars(select(WorkflowRun).where(
        WorkflowRun.actor_id == principal.user.id,
        WorkflowRun.request_key.like(f"global:{conversation.id}:%"),
    ).order_by(WorkflowRun.id.desc()).limit(100)).all()
    if not runs:
        return "No recorded global workflow execution exists for this conversation."
    # Document authorization and actual bytes are rechecked by the request
    # handler. Never display a run for a project whose access was revoked.
    available = {f.id for f, _ in documents}
    by_project = {}
    for run in runs:
        if "timesheets.view" not in principal.project_permissions.get(run.project_id, ()):
            continue
        if not set(run.snapshot.get("source_ids", [])) <= available:
            continue
        by_project.setdefault(run.project_id, run)
    if not by_project:
        return "No global workflow records are available under current document permissions."
    lines = ["Recorded global workflow status (synchronous; no background queue):"]
    for pid, run in sorted(by_project.items()):
        lines.append(f"- Project {pid}: {run.workflow_id}, run #{run.id}, {run.status}.")
        for step in run.snapshot["steps"]:
            lines.append(f"  - {step['step']}: {step['status']}"
                         + (f" ({', '.join(step['issue_codes'])})"
                            if step["issue_codes"] else ""))
    lines.append("Planning/report/staff approval and financial actions remain independently gated.")
    return "\n".join(lines)


def global_conversation_state(db, principal, conversation):
    """Project-global UI state derived solely from committed, scoped receipts."""
    from .documents import resolve_documents
    principal.require("projects:read")
    docs = resolve_documents(db, principal, conversation.id, None, [])
    visible = {f.id for f, _ in docs}
    runs = db.scalars(select(WorkflowRun).where(
        WorkflowRun.actor_id == principal.user.id,
        WorkflowRun.request_key.like(f"global:{conversation.id}:%"),
    ).order_by(WorkflowRun.id.desc()).limit(100)).all()
    by_project = {}
    for run in runs:
        if "timesheets.view" not in principal.project_permissions.get(run.project_id, ()):
            continue
        if not set(run.snapshot.get("source_ids", [])) <= visible:
            continue
        by_project.setdefault(run.project_id, run)
    if not by_project:
        return None
    items = [
        {"project_id": pid, "workflow_id": run.workflow_id, "run_id": run.id,
         "status": run.status, "validation_id":run.snapshot.get("structural_validation_id"),
         "steps": [{"step": step["step"], "status": step["status"],
                    "issue_codes": step["issue_codes"]}
                   for step in run.snapshot["steps"]]}
        for pid, run in sorted(by_project.items())
    ]
    selected_ids = sorted({fid for run in by_project.values()
                           for fid in run.snapshot.get("source_ids", [])})
    return {
        "stage": "GLOBAL_WORKFLOW_RECORDED",
        "scope": {
            "project_ids": sorted(by_project),
            "source_ids": selected_ids,
            "source_rows": sum(max(0, len(sheet["rows"])-1) for file, record in docs if file.id in selected_ids for sheet in record.sheets),
        },
        "scope_fresh": True,
        "mapping": None,
        "validation": {"status": "blocked" if any(run.status == "blocked"
                                                for run in by_project.values())
                       else "needs_review" if any(run.status=="needs_review" for run in by_project.values()) else "completed"},
        "blockers": sorted({code for run in by_project.values() for step in run.snapshot['steps']
                            if step.get('attempted') for code in step['issue_codes']}),
        "project_runs": items,
    }
