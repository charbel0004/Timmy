"""Actual delivered synthetic Excel suites; no live provider, real payment or AI authority."""
from pathlib import Path
from uuid import uuid4
from decimal import Decimal
import pytest
from sqlalchemy import insert, update, select
from sqlalchemy.orm import Session
from test_foundation import client, ORIGIN, PASSWORD
from timmy.auth import password_hasher
from timmy.models import (Role, User, project_memberships,project_permission_overrides,projects,PlanningCodeContract,
                          WorkflowRun,WorkflowPaymentDraft,WorkflowPaymentApproval,WorkflowPaymentExport,ExternalReportVersion)
FIXTURES=Path(__file__).parent/'fixtures/excel_acceptance'


@pytest.fixture
def coordinator(client,tmp_path,monkeypatch):
    from timmy.ai import OllamaAdapter
    async def no_model(*args,**kwargs):raise AssertionError('Authority and financial workflows must be deterministic')
    monkeypatch.setattr(OllamaAdapter,'structured',no_model)
    client.app.state.config.document_root=tmp_path/'originals'
    with Session(client.app.state.engine) as db,db.begin():
        role=Role(name='admin');db.add(role);db.flush()
        db.add(User(id=120,username='acceptance-coordinator',password_hash=password_hasher.hash(PASSWORD),role_id=role.id));db.flush()
        for pid,code,family in [(1,'TCD','session'),(2,'FOS','hours')]:
            db.execute(update(projects).where(projects.c.id==pid).values(project_code=code,name=code,policy_family=family))
            db.execute(insert(project_memberships).values(user_id=120,project_id=pid))
            # Explicit harness authorization, independently seeded. Never derived from uploaded workbooks.
            db.execute(insert(project_permission_overrides).values(user_id=120,project_id=pid,permissions=[
                'projects:read','timesheets.view','activities.view','payments.view','discrepancies.view',
                'planning.verify','staff.verify','payments.allocate','payments.approve']))
            db.add(PlanningCodeContract(project_id=pid,version='independently-approved-fixture-v1',code_pattern=f'26-{code}-[0-9]{{3}}',
                source_ref='SYNTHETIC ACCEPTANCE HARNESS APPROVAL',approved_by=120,approved_at=1))
    login=client.post('/api/auth/login',headers=ORIGIN,json={'username':'acceptance-coordinator','password':PASSWORD})
    headers=ORIGIN|{'X-CSRF-Token':login.json()['csrf_token']}
    conversation=client.post('/api/chat/conversations',headers=headers).json()['id']
    return client,headers,conversation


def load(coordinator,suite):
    c,h,conv=coordinator
    files={}
    for path in sorted((FIXTURES/suite).glob('*.xlsx')):
        response=c.post('/api/documents',params={'filename':path.name,'conversation_id':conv},content=path.read_bytes(),
            headers=h|{'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
        assert response.status_code==201,response.text
        files[path.name]=response.json()
    reply=c.post(f'/api/chat/conversations/{conv}/messages',headers=h,json={'message':'Process the documents and give me a final payment request.','request_id':str(uuid4())})
    assert reply.status_code==200,reply.text
    mapping=c.get(f'/api/global-mappings/{conv}').json()
    confirmed=c.post(f'/api/global-mappings/{conv}/confirm',headers=h,json={'fingerprint':mapping['fingerprint'],
        'sheets':[{k:s[k] for k in ('file_id','sheet_index','kind','columns')} for s in mapping['sheets']]})
    assert confirmed.status_code==200,confirmed.text
    return files


def declare(coordinator):
    c,h,conv=coordinator
    source=c.post('/api/reporting-register/sources',headers=h,json={'name':'Designated acceptance Excel reporting register','project_ids':[1,2],'approved_source':True})
    assert source.status_code==201,source.text
    candidates=c.get(f'/api/reporting-register/conversations/{conv}').json()
    assert len(candidates)==1
    candidate=candidates[0]
    response=c.post(f'/api/reporting-register/conversations/{conv}/confirm',headers=h,json={'source_id':source.json()['id'],
        'file_id':candidate['file_id'],'sha256':candidate['sha256'],'official_export_declared':True,
        'sheets':[{'sheet_index':s['sheet_index'],'columns':s['columns']} for s in candidate['sheets']]})
    assert response.status_code==200,response.text
    return response.json()


def review(coordinator):
    c,h,conv=coordinator
    state=c.get(f'/api/chat/conversations/{conv}/workflow').json()
    with Session(c.app.state.engine) as db:
        runs=list(db.scalars(select(WorkflowRun).where(WorkflowRun.actor_id==120).order_by(WorkflowRun.id.desc())))
        latest={}
        for run in runs:latest.setdefault(run.project_id,run)
        validations=[r.snapshot.get('structural_validation_id') for r in latest.values()]
    for identifier in validations:
        assert identifier is not None
        data=c.get(f'/api/documents/validation/{identifier}').json()
        for activity in data['activities']:
            for kind in ('planning','staff'):
                response=c.post(f'/api/documents/reviews/{identifier}',headers=h,json={'project_code':activity['project_code'],
                    'activity_code':activity['activity_code'],'kind':kind,'decision':'confirmed',
                    'evidence_ref':'INDEPENDENT_SYNTHETIC_HARNESS_VERIFICATION'})
                assert response.status_code==200,response.text


def test_happy_path_reaches_exact_human_payment_approval_without_intermediate_process_commands(coordinator):
    c,h,conv=coordinator
    load(coordinator,'01_Happy_Path')
    declaration=declare(coordinator)
    assert declaration['assurance']=='coordinator_declared_not_independently_authenticated'
    assert all(r['accepted'] for r in declaration['evaluation']['rows'])
    review(coordinator)
    response=c.get(f'/api/workflow-payments/conversations/{conv}')
    assert response.status_code==200,response.text
    drafts=response.json();assert len(drafts)==2,drafts
    assert {d['snapshot']['project_code']:sum(Decimal(line['amount']) for line in d['snapshot']['lines']) for d in drafts}=={'TCD':Decimal('100.00'),'FOS':Decimal('160.00')}
    for draft in drafts:
        assert not draft['approved']
        denied=c.post(f'/api/workflow-payments/{draft["id"]}/export',headers=h,json={'digest':draft['digest'],'approve_exact_snapshot':True})
        assert denied.status_code==409
        allocation=c.post(f'/api/workflow-payments/{draft["id"]}/allocations',headers=h,json={'digest':draft['digest'],'verified_by_human':True,
            'allocations':{line['staff_id']:{'payee_reference':'INERT_TEST_PAYEE_'+line['staff_id'],'allocation_reference':'SYNTHETIC_BUDGET_ONLY','evidence_ref':'INDEPENDENT_TEST_ALLOCATION'} for line in draft['snapshot']['lines']}})
        assert allocation.status_code==200,allocation.text
        configured=allocation.json()
        approved=c.post(f'/api/workflow-payments/{configured["id"]}/approve',headers=h,json={'digest':configured['digest'],'approve_exact_snapshot':True})
        assert approved.status_code==200,approved.text
        exported=c.post(f'/api/workflow-payments/{configured["id"]}/export',headers=h,json={'digest':configured['digest'],'approve_exact_snapshot':True})
        assert exported.status_code==200,exported.text
        assert 'text/csv' in exported.headers['content-type'] and 'INERT_TEST_PAYEE_' in exported.text
    with Session(c.app.state.engine) as db:
        assert len(list(db.scalars(select(WorkflowPaymentApproval))))==2
        assert len(list(db.scalars(select(WorkflowPaymentExport))))==2


@pytest.mark.parametrize('suite',['02_Mixed_Data_And_Discrepancies','03_Boundaries_And_Financial_Controls'])
def test_discrepancy_and_boundary_exports_are_preserved_without_automatic_financial_approval(coordinator,suite):
    c,h,conv=coordinator
    load(coordinator,suite)
    result=declare(coordinator)
    assert result['evaluation']['rows']
    resolved=c.post(f'/api/chat/conversations/{conv}/messages',headers=h,
        json={'message':'Resolve discrepancies','request_id':str(uuid4())})
    assert resolved.status_code==200,resolved.text
    with Session(c.app.state.engine) as db:
        runs=list(db.scalars(select(WorkflowRun).where(WorkflowRun.actor_id==120,
            WorkflowRun.workflow_id=='resolve_issues')))
        assert len(runs)==2
        assert all(run.status in {'needs_review','blocked'} for run in runs)
        assert all(run.status!='completed' for run in runs)
        assert all(run.snapshot['steps'][0]['issue_codes'] for run in runs)
        assert not list(db.scalars(select(WorkflowPaymentApproval)))
        assert not list(db.scalars(select(WorkflowPaymentExport)))


def ready_draft(coordinator):
    c,h,conv=coordinator
    load(coordinator,'01_Happy_Path');declare(coordinator);review(coordinator)
    draft=c.get(f'/api/workflow-payments/conversations/{conv}').json()[0]
    configured=c.post(f'/api/workflow-payments/{draft["id"]}/allocations',headers=h,json={'digest':draft['digest'],'verified_by_human':True,
        'allocations':{line['staff_id']:{'payee_reference':'INERT_ONLY','allocation_reference':'TEST_BUDGET','evidence_ref':'TEST_HUMAN_VERIFIED'} for line in draft['snapshot']['lines']}})
    assert configured.status_code==200,configured.text
    return configured.json()


def test_financial_grants_are_required_even_for_existing_admin_and_approval_is_exact(coordinator):
    c,h,conv=coordinator;draft=ready_draft(coordinator)
    wrong=c.post(f'/api/workflow-payments/{draft["id"]}/approve',headers=h,json={'digest':'0'*64,'approve_exact_snapshot':True})
    assert wrong.status_code==409
    with Session(c.app.state.engine) as db,db.begin():
        item=db.get(WorkflowPaymentDraft,draft['id'])
        row=db.execute(select(project_permission_overrides).where(project_permission_overrides.c.user_id==120,
            project_permission_overrides.c.project_id==item.project_id)).mappings().one()
        db.execute(update(project_permission_overrides).where(project_permission_overrides.c.user_id==120,
            project_permission_overrides.c.project_id==item.project_id).values(permissions=[p for p in row['permissions'] if p!='payments.approve']))
    denied=c.post(f'/api/workflow-payments/{draft["id"]}/approve',headers=h,json={'digest':draft['digest'],'approve_exact_snapshot':True})
    assert denied.status_code==403


def test_new_sources_invalidate_prepared_payment_snapshot(coordinator):
    c,h,conv=coordinator;draft=ready_draft(coordinator)
    uploaded=c.post('/api/documents',params={'filename':'changed-source.csv','conversation_id':conv},
        content=b'project_code,project_name\nTCD,Changed source context\n',headers=h|{'Content-Type':'text/csv'})
    assert uploaded.status_code==201
    refused=c.post(f'/api/workflow-payments/{draft["id"]}/approve',headers=h,json={'digest':draft['digest'],'approve_exact_snapshot':True})
    assert refused.status_code==409 and 'STALE_FINANCIAL_SNAPSHOT' in refused.text
    with Session(c.app.state.engine) as db:assert not list(db.scalars(select(WorkflowPaymentApproval)))


def test_admin_source_format_confirmation_resumes_declared_register_without_new_process_command(coordinator):
    from sqlalchemy import delete
    c,h,conv=coordinator
    with Session(c.app.state.engine) as db,db.begin():db.execute(delete(PlanningCodeContract))
    load(coordinator,'01_Happy_Path')
    declared=declare(coordinator)
    assert all(not row['accepted'] for row in declared['evaluation']['rows'])
    for pid,code in [(1,'TCD'),(2,'FOS')]:
        result=c.post(f'/api/global-mappings/contracts/{pid}',headers=h,json={'version':'approved-fixture-v2',
            'code_pattern':f'26-{code}-[0-9]{{3}}','sample_code':f'26-{code}-001',
            'source_ref':'INDEPENDENT_TEST_SOURCE_FORMAT_APPROVAL','approved_source_format':True,'conversation_id':conv})
        assert result.status_code==200,result.text
    with Session(c.app.state.engine) as db:
        reports=list(db.scalars(select(ExternalReportVersion)))
        assert len(reports)==2 and all(report.cutoff for report in reports)
    review(coordinator)
    assert len(c.get(f'/api/workflow-payments/conversations/{conv}').json())==2


def test_direct_payment_preparation_cannot_bypass_official_report_declaration(coordinator):
    c,h,conv=coordinator
    load(coordinator,'01_Happy_Path');review(coordinator)
    result=c.post(f'/api/chat/conversations/{conv}/messages',headers=h,json={
        'message':'Prepare September payment requests for both projects.','request_id':str(uuid4())})
    assert result.status_code==200,result.text
    assert 'REPORT_VALIDATION_EVIDENCE_REQUIRED' in result.json()['message']['text']
    assert c.get(f'/api/workflow-payments/conversations/{conv}').json()==[]


def test_rule_version_change_invalidates_payment_approval(coordinator,monkeypatch):
    c,h,conv=coordinator;draft=ready_draft(coordinator)
    monkeypatch.setattr('timmy.workflow_payments.rules_digest',lambda family:'changed-rule-version')
    refused=c.post(f'/api/workflow-payments/{draft["id"]}/approve',headers=h,
        json={'digest':draft['digest'],'approve_exact_snapshot':True})
    assert refused.status_code==409 and 'rule version changed' in refused.text
    with Session(c.app.state.engine) as db:assert not list(db.scalars(select(WorkflowPaymentApproval)))


def test_planning_format_proposals_use_original_project_rows_and_require_human_confirmation(coordinator):
    from sqlalchemy import delete
    c,h,conv=coordinator
    with Session(c.app.state.engine) as db,db.begin():db.execute(delete(PlanningCodeContract))
    load(coordinator,'01_Happy_Path')
    state=c.get(f'/api/global-mappings/{conv}').json()
    proposals=state['contract_candidates']
    assert {p['project_code']:p['code_pattern'] for p in proposals}=={'TCD':'26-TCD-[0-9]{3}','FOS':'26-FOS-[0-9]{3}'}
    for p in proposals:
        assert p['evidence'] and all(e['filename']=='planning.xlsx' and e['sheet']=='Activities' and e['row']>=2 for e in p['evidence'])
        assert p['sample_code'].startswith('26-'+p['project_code']+'-')
    p=proposals[0]
    body={k:p[k] for k in ('version','code_pattern','sample_code','source_ref')}
    body.update(conversation_id=conv,source_fingerprint=state['fingerprint'],approved_source_format=False)
    assert c.post(f'/api/global-mappings/contracts/{p["project_id"]}',headers=h,json=body).status_code==422
    body.update(approved_source_format=True,sample_code=p['project_code'])
    assert c.post(f'/api/global-mappings/contracts/{p["project_id"]}',headers=h,json=body).status_code==422
    body.update(sample_code=p['sample_code'],source_fingerprint='0'*64)
    assert c.post(f'/api/global-mappings/contracts/{p["project_id"]}',headers=h,json=body).status_code==409
    with Session(c.app.state.engine) as db:assert not list(db.scalars(select(PlanningCodeContract)))
