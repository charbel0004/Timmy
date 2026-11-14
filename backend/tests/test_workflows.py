from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from test_foundation import client, ORIGIN, PASSWORD
from timmy.auth import password_hasher
from timmy.models import Role, User, WorkflowRun, StoredFile, projects, project_memberships, PlanningCodeContract, activities
from timmy.workflows import choose_workflow, knowledge
from timmy.workflow_scheduler import run_due


@pytest.fixture
def workspace(client, tmp_path):
    client.app.state.config.document_root = tmp_path / 'private'
    with Session(client.app.state.engine) as db, db.begin():
        role = Role(name='admin')
        db.add(role)
        db.flush()
        db.add(User(id=99, username='workflow-main', role_id=role.id, password_hash=password_hasher.hash(PASSWORD)))
        db.flush()
        db.execute(insert(project_memberships).values(project_id=1, user_id=99))
        db.execute(update(projects).where(projects.c.id == 1).values(project_code='P'))
        db.add(PlanningCodeContract(project_id=1,version='synthetic-only',code_pattern='A',source_ref='SYNTHETIC_TEST_ONLY',approved_by=99,approved_at=1))
    result = client.post('/api/auth/login', headers=ORIGIN, json={'username':'workflow-main','password':PASSWORD})
    headers = ORIGIN | {'X-CSRF-Token':result.json()['csrf_token']}
    conversation = client.post('/api/chat/conversations', headers=headers).json()['id']
    rows = 'project_code,activity_code,staff_id,role,session_number,work_date,timesheet_submitted_date\n'
    for n in range(1, 7):
        for staff, role in [('T','TRAINER'),('L','LOGISTIC')]:
            rows += f'P,A,{staff},{role},S{n},2026-07-{1+(n-1)//3:02},2026-07-10\n'
    for filename, body in [('claims.csv', rows), ('plans.csv','project_code,activity_code,approved_start_date,approved_end_date\nP,A,2026-07-01,2026-07-30\n'), ('staff.csv','staff_id,status\nT,active\nL,active\n')]:
        response = client.post('/api/documents', params={'filename':filename,'project_id':1,'conversation_id':conversation},
                               headers=headers | {'Content-Type':'text/csv'}, content=body.encode())
        assert response.status_code == 201, response.text
    return client, headers, conversation


def send(workspace, message, **changes):
    c, headers, conversation = workspace
    payload = {'message':message,'request_id':str(uuid4()),'project_id':1} | changes
    return payload, c.post(f'/api/chat/conversations/{conversation}/messages', headers=headers, json=payload)


@pytest.mark.parametrize(('text','expected'), [
    ('Analyze', 'analyze_intake'), ('Process', 'process_activity'),
    ('Run weekly', 'weekly_cycle'), ('Reconcile the payment report', 'payment_return'),
    ('Prepare a payment request', 'prepare_payment'), ('Show flags', 'show_issues'),
    ('Resolve discrepancies', 'resolve_issues'), ('Process payments', 'clarify'),
    ('Analyze then process', 'clarify'), ('عالج السجلات', 'process_activity'),
])
def test_brief_requests_select_stored_workflow(text, expected):
    assert choose_workflow(text) == expected


def test_intake_offers_processing_and_persists_replay(workspace):
    c, h, conv = workspace
    payload, response = send(workspace, 'Analyze')
    assert response.status_code == 200, response.text
    answer = response.json()['message']['text']
    assert '3 files' in answer and 'Process these' in answer
    assert c.get(f'/api/chat/conversations/{conv}').json()['messages'][-1]['text'] == answer
    assert c.post(f'/api/chat/conversations/{conv}/messages',headers=h,json=payload).json() == response.json()
    with Session(c.app.state.engine) as db:
        runs = list(db.scalars(select(WorkflowRun)))
        assert len(runs) == 1
        assert [s['step'] for s in runs[0].snapshot['steps']] == ['verify_intake']
    changed = c.post(f'/api/chat/conversations/{conv}/messages',headers=h,json=payload | {'project_id':2})
    assert changed.status_code in (403,409)


def test_weekly_steps_block_finance_and_use_same_api_runner(workspace):
    c,h,conv = workspace
    send(workspace,'Process'); send(workspace,'Confirmed')
    key = str(uuid4())
    response = c.post('/api/workflows/runs',headers=h,json={'request_id':key,'project_id':1,'workflow_id':'weekly_cycle'})
    assert response.status_code == 201, response.text
    body = response.json()
    expected = next(w.steps for w in knowledge().workflows if w.id == 'weekly_cycle')
    assert [s['step'] for s in body['steps']] == expected
    assert body['status'] == 'blocked'
    assert body['steps'][-1]['step'] == 'export_payment_request'
    assert 'DEPENDENCY_NOT_SATISFIED' in body['steps'][-1]['issue_codes']
    assert 'EXACT_BATCH_APPROVAL_REQUIRED' in body['steps'][-1]['unverified_requirements']
    assert body['steps'][-1]['blocked_by'] == 'check_planning'
    assert body['steps'][-1]['executed'] is False
    replay = c.post('/api/workflows/runs',headers=h,json={'request_id':key,'project_id':1,'workflow_id':'weekly_cycle'})
    assert replay.json() == body
    last = c.get('/api/workflows/last-run/1').json()
    assert last['id'] == body['id'] and last['recorded_at'].endswith('+00:00')


def test_return_workflow_does_not_claim_reconciliation_or_archive(workspace):
    _,response = send(workspace,'Reconcile the payment report')
    assert response.status_code == 200
    answer = response.json()['message']['text']
    assert 'reconcile payments: blocked' in answer and 'archive payment evidence: blocked' in answer


def test_processing_uses_frozen_report_cutoff(workspace):
    from timmy.report_reconciliation import ReportEvent, synchronize
    c,_,_ = workspace
    class Provider:
        source='synthetic-only'
        def health(self): return 'ready'
        def events(self,*args):
            return [ReportEvent(report_id='R',version='1',submitted_at='2026-07-01T00:00:00Z',validated_at='2026-07-02T00:00:00Z',evidence_ref='test-only')]
    send(workspace,'Process');send(workspace,'Confirmed')
    synchronize(c.app.state.engine,Provider(),project_id=1,activity_code='A',timezone='UTC')
    _,response = send(workspace,'Process')
    assert 'Mapping proposal' not in response.json()['message']['text']
    assert 'AFTER_VALIDATED_REPORT_CUTOFF' in response.json()['message']['text']
    assert '6/12 role slots' in response.json()['message']['text']


def test_source_corruption_blocks_processing(workspace):
    c,_,_ = workspace
    with Session(c.app.state.engine) as db:
        file = db.scalar(select(StoredFile))
        (c.app.state.config.document_root / file.id).write_bytes(b'corrupt synthetic file')
    _,response = send(workspace,'Process')
    assert response.status_code == 200
    assert 'SOURCE_INTEGRITY_FAILED' in response.json()['message']['text']
    assert 'Structure passes' not in response.json()['message']['text']


def test_history_rechecks_access(workspace):
    c,h,conv = workspace
    send(workspace,'Analyze')
    from timmy.models import project_permission_overrides
    with Session(c.app.state.engine) as db,db.begin():
        db.execute(insert(project_permission_overrides).values(user_id=99,project_id=1,permissions=['projects:read']))
    reply = c.get(f'/api/chat/conversations/{conv}').json()['messages'][-1]['text']
    assert 'unavailable under your current' in reply


def test_monday_schedule_uses_beirut_time_and_deduplicates(workspace):
    c,_,_ = workspace
    config = c.app.state.config
    config.weekly_enabled = True
    config.weekly_actor_id = None
    config.weekly_project_ids = []
    # Missing identity or project scope must fail closed.
    due = datetime(2026,11,16,2,0,tzinfo=timezone.utc) # 04:00 Beirut
    assert run_due(c.app.state.engine,config,due) == []
    config.weekly_actor_id = 99
    assert run_due(c.app.state.engine, config, due) == []
    config.weekly_project_ids = [1]
    assert run_due(c.app.state.engine,config,datetime(2026,11,16,1,59,tzinfo=timezone.utc)) == []
    ids = run_due(c.app.state.engine,config,due)
    assert len(ids) == 1
    assert run_due(c.app.state.engine,config,due) == []
    # New week uses a fresh key. DST is resolved via Asia/Beirut rather than UTC hours.
    assert len(run_due(c.app.state.engine,config,datetime(2026,11,23,2,0,tzinfo=timezone.utc))) == 1


def test_model_selects_workflow_id_and_receives_stored_instructions():
    import asyncio
    from timmy.chat import respond
    seen = []
    class Adapter:
        async def structured(self, messages, schema):
            assert 'Monday at 04:00' in messages[0]['content']
            assert 'payment_return' in messages[0]['content']
            return schema(answer='Proposed',tool='run_workflow',workflow_id='weekly_cycle')
    reply,_ = asyncio.run(respond(Adapter(),[{'role':'user','content':'Please handle our regular operations'}],
                                  lambda:[],lambda:None,workflow=lambda identifier:seen.append(identifier) or 'Run recorded'))
    assert seen == ['weekly_cycle'] and reply == 'Run recorded'


def test_ambiguous_and_negated_requests_do_not_call_workflow():
    import asyncio
    from timmy.chat import respond
    class NoInference:
        async def structured(self,*args): raise AssertionError('Clarification must not require inference')
    for message in ['Process payments', 'Do not process', 'Analyze then process']:
        reply,_ = asyncio.run(respond(NoInference(),[{'role':'user','content':message}],lambda:[],lambda:None,
                                      workflow=lambda identifier:pytest.fail('Ambiguous request executed')))
        assert 'What would you like' in reply
    assert choose_workflow("Show flags; don't resolve anything") == 'show_issues'


def test_scheduler_disabled_and_summer_local_time(workspace):
    c,_,_ = workspace
    config=c.app.state.config
    config.weekly_actor_id=99
    config.weekly_project_ids=[1]
    config.weekly_enabled=False
    summer_due=datetime(2026,7,6,1,0,tzinfo=timezone.utc) # 04:00 in DST
    assert run_due(c.app.state.engine,config,summer_due)==[]
    config.weekly_enabled=True
    assert run_due(c.app.state.engine,config,datetime(2026,7,6,0,59,tzinfo=timezone.utc))==[]
    assert len(run_due(c.app.state.engine,config,summer_due))==1
    assert run_due(c.app.state.engine,config,datetime(2026,7,7,1,0,tzinfo=timezone.utc))==[]


def test_weekly_replay_with_changed_evidence_conflicts(workspace):
    c,h,_=workspace
    send(workspace,'Process');send(workspace,'Confirmed')
    payload={'request_id':str(uuid4()),'project_id':1,'workflow_id':'weekly_cycle'}
    first=c.post('/api/workflows/runs',headers=h,json=payload)
    assert first.status_code==201
    with Session(c.app.state.engine) as db,db.begin():
        from timmy.models import ExternalReportVersion
        db.add(ExternalReportVersion(project_id=1,activity_id=db.scalar(select(activities.c.id).where(activities.c.activity_code=='A')),activity_code='A',source='synthetic',report_id='R',version='1',
                                    submitted_at='2026-07-01T00:00:00Z',local_date='2026-07-01',cutoff='2026-07-01',
                                    validated_at='2026-07-02T00:00:00Z',evidence_ref='test-only'))
    assert c.post('/api/workflows/runs',headers=h,json=payload).status_code==409


def test_workflow_endpoints_require_scope_and_csrf(workspace):
    c,h,_=workspace
    payload={'request_id':str(uuid4()),'project_id':1,'workflow_id':'weekly_cycle'}
    assert c.post('/api/workflows/runs',headers=ORIGIN,json=payload).status_code==403
    assert c.post('/api/workflows/runs',headers=h,json=payload|{'project_id':2}).status_code==403
    assert c.post('/api/workflows/runs',headers=h,json=payload|{'workflow_id':'approve_payment'}).status_code==422
    c.post('/api/auth/login',headers=ORIGIN,json={'username':'unknown','password':PASSWORD})
    assert c.get('/api/workflows/last-run/1').status_code==403

def test_failed_weekly_handler_is_recorded_and_not_retried(workspace, monkeypatch):
    from timmy import workflow_scheduler
    c, _, _ = workspace
    config = c.app.state.config
    config.weekly_enabled = True
    config.weekly_actor_id = 99
    config.weekly_project_ids = [1]
    attempts = []

    def fails_once(*args, **kwargs):
        attempts.append(kwargs['request_key'])
        raise ValueError('sensitive input must not be logged or persisted')

    monkeypatch.setattr(workflow_scheduler, 'run_workflow', fails_once)
    due = datetime(2026, 11, 16, 2, 0, tzinfo=timezone.utc)
    assert workflow_scheduler.run_due(c.app.state.engine, config, due) == []
    assert workflow_scheduler.run_due(c.app.state.engine, config, due) == []
    assert len(attempts) == 1
    with Session(c.app.state.engine) as db:
        marker = db.scalar(select(WorkflowRun).where(WorkflowRun.request_key == attempts[0]))
        assert marker.status == 'failed'
        assert marker.snapshot['steps'][0]['issue_codes'] == ['SCHEDULED_EXECUTION_FAILED']
        assert 'sensitive input' not in str(marker.snapshot)


def test_weekly_http_failure_is_held_without_retry(workspace, monkeypatch):
    from fastapi import HTTPException
    from timmy import workflow_scheduler
    c, _, _ = workspace
    config = c.app.state.config
    config.weekly_enabled = True
    config.weekly_actor_id = 99
    config.weekly_project_ids = [1]
    attempts = []
    def rejects(*args, **kwargs):
        attempts.append(1)
        raise HTTPException(409, 'untrusted details')
    monkeypatch.setattr(workflow_scheduler, 'run_workflow', rejects)
    due = datetime(2026, 11, 16, 2, 0, tzinfo=timezone.utc)
    workflow_scheduler.run_due(c.app.state.engine, config, due)
    workflow_scheduler.run_due(c.app.state.engine, config, due)
    assert attempts == [1]
    with Session(c.app.state.engine) as db:
        marker = db.scalar(select(WorkflowRun).where(
            WorkflowRun.request_key == 'weekly:2026-W47:1'))
        assert marker.status == 'blocked'
        assert marker.snapshot['steps'][0]['issue_codes'] == ['SCHEDULED_HTTP_409']

def test_unexecuted_validation_exposes_only_provisional_evidence(workspace):
    c, h, _ = workspace
    response = c.post('/api/workflows/runs', headers=h,
                      json={'request_id': str(uuid4()), 'project_id': 1,
                            'workflow_id': 'process_activity'})
    assert response.status_code == 201
    steps = response.json()['steps']
    hold = next(row for row in steps if row['step'] == 'validate_activity')
    assert hold['executed'] is False
    assert hold['attempted'] is False
    assert hold['structural_preview_only'] is True
    assert hold['evidence_kind'] == 'provisional_structural_preview'

def test_workflow_step_receipts_are_committed_and_scoped(workspace):
    from timmy.models import WorkflowStepReceipt
    c,h,_ = workspace
    response=c.post('/api/workflows/runs',headers=h,json={
        'request_id':str(uuid4()),'project_id':1,'workflow_id':'weekly_cycle'})
    assert response.status_code==201,response.text
    run_id=response.json()['id']
    with Session(c.app.state.engine) as db:
        rows=list(db.scalars(select(WorkflowStepReceipt).where(
            WorkflowStepReceipt.run_id==run_id).order_by(WorkflowStepReceipt.step_index)))
        assert len(rows)==len(response.json()['steps'])
        assert [row.step_id for row in rows]==[row['step'] for row in response.json()['steps']]
        assert all(not row.executed for row in rows[1:])
        assert rows[1].blocked_by=='check_planning'


def test_manual_continuation_is_new_immutable_run_and_no_finance(workspace):
    c,h,_=workspace
    response=c.post('/api/workflows/runs',headers=h,json={
        'request_id':str(uuid4()),'project_id':1,'workflow_id':'weekly_cycle'})
    original=response.json()['id']
    key=str(uuid4())
    route=f'/api/workflows/runs/{original}/resume'
    resumed=c.post(route,headers=h,json={'request_id':key})
    assert resumed.status_code==201,resumed.text
    body=resumed.json()
    assert body['id'] != original
    assert body['resumed_from_run_id']==original
    assert body['steps'][-1]['executed'] is False
    assert c.post(route,headers=h,json={'request_id':key}).json() == body
    with Session(c.app.state.engine) as db:
        previous=db.get(WorkflowRun,original)
        assert previous.snapshot.get('resumed_from_run_id') is None
        current=db.get(WorkflowRun,body['id'])
        assert current.snapshot['resumed_from_run_id']==original
        assert current.snapshot['resume_mode']=='fresh_evidence_revalidation'
    assert c.post(route,headers=ORIGIN,json={'request_id':str(uuid4())}).status_code==403


def test_cannot_resume_completed_intake_or_cross_parent(workspace):
    c,h,_=workspace
    first=c.post('/api/workflows/runs',headers=h,json={
        'request_id':str(uuid4()),'project_id':1,'workflow_id':'analyze_intake'})
    assert first.json()['status']=='completed'
    denied=c.post(f"/api/workflows/runs/{first.json()['id']}/resume",
                  headers=h,json={'request_id':str(uuid4())})
    assert denied.status_code==409

def test_typed_payment_return_upload_triggers_unverified_reconciliation_hold(workspace):
    c,h,conv=workspace
    data=b'batch,reference,result\nSYNTHETIC,EXAMPLE,pending\n'
    uploaded=c.post('/api/documents',
        params={'filename':'synthetic-return.csv','project_id':1,
                'purpose':'payment_return','conversation_id':conv},
        content=data,headers=h|{'Content-Type':'text/csv'})
    assert uploaded.status_code==201,uploaded.text
    body=uploaded.json()
    assert body['status']=='PAYMENT_RETURN_RECEIVED_UNVERIFIED'
    assert isinstance(body['workflow_run_id'],int)
    with Session(c.app.state.engine) as db:
        run=db.get(WorkflowRun,body['workflow_run_id'])
        assert run.workflow_id=='payment_return'
        assert run.status=='blocked'
        assert run.request_key=='payment_return:upload:'+body['id']
        assert run.snapshot['payment_return_file_id']==body['id']
        first,second=run.snapshot['steps'][:2]
        assert first['step']=='receive_payment_report'
        assert first['status']=='completed'
        assert first['authority']=='UNVERIFIED_UPLOAD_ONLY'
        assert 'TRUSTED_PAYMENT_REPORT_ADAPTER_REQUIRED' in second['issue_codes']
        assert not any(s.get('status')=='completed' for s in run.snapshot['steps'][1:])
    visible=c.get('/api/documents',params={'conversation_id':conv})
    assert visible.status_code==200
    assert body['id'] not in [row['id'] for row in visible.json()]
    from timmy.models import payment_batches
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(payment_batches.c.id).limit(1)) is None


def test_generic_timesheet_upload_never_triggers_payment_return(workspace):
    c,h,conv=workspace
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(WorkflowRun).where(
            WorkflowRun.workflow_id=='payment_return')) is None
    result=c.post('/api/documents',
        params={'filename':'generic.csv','project_id':1,'conversation_id':conv},
        content=b'a,b\n1,2\n',headers=h|{'Content-Type':'text/csv'})
    assert result.status_code==201,result.text
    assert result.json()['workflow_run_id'] is None
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(WorkflowRun).where(
            WorkflowRun.workflow_id=='payment_return')) is None
