"""Actual chat-API regressions; no real staff, provider or payment records."""
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, func, update
from sqlalchemy.orm import Session

from test_foundation import client, ORIGIN, PASSWORD
from timmy.auth import password_hasher
from timmy.models import Role, User, WorkflowRun, project_memberships, projects


@pytest.fixture
def conversation(client, tmp_path, monkeypatch):
    from timmy.ai import OllamaAdapter
    async def no_model(*args, **kwargs):
        raise AssertionError('Workflow confirmations/status must not depend on model inference')
    monkeypatch.setattr(OllamaAdapter, 'structured', no_model)
    client.app.state.config.document_root = tmp_path / 'documents'
    with Session(client.app.state.engine) as db, db.begin():
        role = Role(name='admin'); db.add(role); db.flush()
        db.add(User(id=90, username='conversation-test', role_id=role.id, password_hash=password_hasher.hash(PASSWORD)))
        db.flush(); db.execute(insert(project_memberships).values(project_id=1, user_id=90))
        db.execute(update(projects).where(projects.c.id==1).values(project_code='P'))
    from timmy.models import PlanningCodeContract
    with Session(client.app.state.engine) as db,db.begin():
        db.add(PlanningCodeContract(project_id=1,version='synthetic-v1',code_pattern='P-A-[0-9]{4}',
            source_ref='SYNTHETIC_TEST_PLANNING',approved_by=90,approved_at=1))
    login = client.post('/api/auth/login', headers=ORIGIN, json={'username':'conversation-test','password':PASSWORD})
    headers = ORIGIN | {'X-CSRF-Token':login.json()['csrf_token']}
    identifier = client.post('/api/chat/conversations', headers=headers).json()['id']
    claims = 'project_code,activity_code,staff_id,role,session_number,work_date,timesheet_submitted_date\n'
    for activity in ['P-A-0001','P-A-0002','P-A-0003']:
        for session in range(1,7):
            for staff,role in [('TEST-T','TRAINER'),('TEST-L','LOGISTIC')]:
                claims += f'P,{activity},{staff},{role},S{session},2026-07-{1+(session-1)//3:02},2026-07-10\n'
    files = {
        'timesheets_valid.csv':claims,
        'planning_activities.csv':'project_code,activity_code,approved_start_date,approved_end_date\n'+''.join(f'P,{a},2026-07-01,2026-07-30\n' for a in ['P-A-0001','P-A-0002','P-A-0003']),
        'projects.csv':'project_code,project_name\nP,Synthetic P\nQ,Synthetic Q\nR,Synthetic R\n',
        'staff_directory.csv':'staff_id,status\nTEST-T,active\nTEST-L,active\n'+''.join(f'TEST-{n},active\n' for n in range(12)),
    }
    def upload(files=files, target=identifier):
        ids=[]
        for name,data in files.items():
            r=client.post('/api/documents',params={'filename':name,'project_id':1,'conversation_id':target},
                          content=data.encode(),headers=headers|{'Content-Type':'text/csv'})
            assert r.status_code==201,r.text
            ids.append(r.json()['id'])
        return ids
    ids=upload()
    # These fixtures exercise the explicit single-project protocol.
    # Unselected/global defaults are covered by test_global_chat_projects.py.
    def send(message, **context):
        r=client.post(f'/api/chat/conversations/{identifier}/messages',headers=headers,
                      json={'request_id':str(uuid4()),'message':message,'project_id':1,**context})
        assert r.status_code==200,r.text
        return r.json()['message']['text']
    def state():
        r=client.get(f'/api/chat/conversations/{identifier}/workflow'); assert r.status_code==200,r.text
        return r.json()
    return client,headers,identifier,send,state,upload,files,ids
