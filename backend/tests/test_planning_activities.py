"""Planning-source identities, source-issued code authority and automatic routine progression."""
from uuid import uuid4

from sqlalchemy import select, func, insert
from sqlalchemy.orm import Session
from planning_fixtures import conversation
from test_foundation import client
from timmy.models import activities, activity_planning_sources, ExternalReportVersion


def planning_case(conversation, rows, *, headers='project_code,activity_code,activity_name,approved_start_date,approved_end_date'):
    c,h,_,_,_,upload,_,_=conversation
    conv=c.post('/api/chat/conversations',headers=h).json()['id']
    ids=upload({'planning.csv':headers+'\n'+rows},conv)
    def send(message):
        r=c.post(f'/api/chat/conversations/{conv}/messages',headers=h,json={
            'message':message,'request_id':str(uuid4()),'project_id':1,'document_ids':ids})
        assert r.status_code==200,r.text
        return r.json()['message']['text']
    def state():return c.get(f'/api/chat/conversations/{conv}/workflow').json()
    return c,h,conv,send,state


def test_planning_preserves_source_codes_and_reimports_once(conversation):
    rows='P,P-A-0042,Existing event,2026-07-01,2026-07-03\nP,P-A-0043,New event,2026-07-04,2026-07-06\n'
    c,h,conv,send,state=planning_case(conversation,rows)
    assert 'Mapping proposal' in send('Process')
    send('Confirmed')
    records=c.get('/api/workspace/activities').json()
    assert {r['activity_code'] for r in records}=={'P-A-0042','P-A-0043'}
    assert {r['name'] for r in records}=={'Existing event','New event'}
    assert 'TIMESHEET_CLAIMS_REQUIRED' in state()['blockers']
    original_ids={r['activity_code']:r['id'] for r in records}
    # Same source bytes, new upload IDs: approved format reused, activity IDs retained.
    c,h,other,send_again,new_state=planning_case(conversation,rows)
    answer=send_again('Process')
    assert 'Mapping proposal' not in answer
    assert new_state()['mapping']['confirmation_method']=='verified_format_reuse'
    assert {r['activity_code']:r['id'] for r in c.get('/api/workspace/activities').json()}==original_ids
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(activity_planning_sources))==2


def test_AC_01_missing_code_column_cannot_generate(conversation):
    c,h,conv,send,state=planning_case(conversation,'P,Workshop,2026-07-01,2026-07-03\n',
        headers='project_code,activity_name,approved_start_date,approved_end_date')
    send('Process');answer=send('Confirmed')
    assert 'activity_code' in answer
    assert c.get('/api/workspace/activities').json()==[]


def test_claims_and_reports_link_the_sidebar_activity_id(conversation):
    c,h,conv,send,state,*_=conversation
    send('Process');send('Confirmed')
    sidebar={r['activity_code']:r['id'] for r in c.get('/api/workspace/activities').json()}
    assert len(sidebar)==3
    from timmy.models import WorkflowRun
    with Session(c.app.state.engine) as db:
        run=db.get(WorkflowRun,state()['validation']['run_id'])
        rows=next(step['activities'] for step in run.snapshot['steps'] if step['step']=='validate_activity')
        assert all(row['activity_id']==sidebar[row['activity_code']] for row in rows)
    from timmy.report_reconciliation import ReportEvent,synchronize
    class Provider:
        source='synthetic-only'
        def health(self):return 'ready'
        def events(self,*args):return [ReportEvent(report_id='R',version='1',submitted_at='2026-07-01T00:00:00Z',
            validated_at='2026-07-02T00:00:00Z',evidence_ref='test-only')]
    synchronize(c.app.state.engine,Provider(),project_id=1,activity_code='P-A-0001',timezone='UTC')
    with Session(c.app.state.engine) as db:
        event=db.scalar(select(ExternalReportVersion))
        assert event.activity_id==sidebar['P-A-0001']
    result=send('Process') # No repeated confirmation for the exact reviewed mapping.
    assert 'AFTER_VALIDATED_REPORT_CUTOFF' in result
    assert 'Mapping proposal' not in result


def test_new_known_format_continues_without_proceed_and_keeps_authority_gates(conversation):
    c,h,conv,send,state,upload,files,_=conversation
    send('Process');send('Confirmed')
    c,h,new,process,new_state=planning_case(conversation,'P,P-A-0004,Next event,2026-07-02,2026-07-05\n')
    process('Process');process('Confirmed') # Approve the optional-name format once.
    c,h,newer,process_again,reused=planning_case(conversation,'P,P-A-0005,Another event,2026-07-07,2026-07-09\n')
    answer=process_again('Process')
    assert reused()['mapping']['confirmation_method']=='verified_format_reuse'
    assert 'P-A-0005' in answer and 'Mapping proposal' not in answer
    assert 'TIMESHEET_CLAIMS_REQUIRED' in reused()['blockers']


def test_weekly_registers_new_planning_from_known_formats_without_chat_confirmation(conversation):
    c,h,conv,send,state,upload,files,_=conversation
    send('Process');send('Confirmed')
    _,_,_,process,_=planning_case(conversation,'P,P-A-0004,Fourth event,2026-07-02,2026-07-05\n')
    process('Process');process('Confirmed')
    target=c.post('/api/chat/conversations',headers=h).json()['id']
    upload({'planning.csv':'project_code,activity_code,activity_name,approved_start_date,approved_end_date\nP,P-A-0005,Weekly new event,2026-07-07,2026-07-09\n'},target)
    r=c.post('/api/workflows/runs',headers=h,json={'request_id':str(uuid4()),'workflow_id':'weekly_cycle','project_id':1})
    assert r.status_code==201,r.text
    records=c.get('/api/workspace/activities').json()
    assert any(row['activity_code']=='P-A-0005' and row['name']=='Weekly new event' for row in records)
    assert r.json()['status']=='blocked' # Missing report/finance authority, not a fake payment success.
    assert 'EXACT_BATCH_APPROVAL_REQUIRED' in r.json()['steps'][-1]['issue_codes']


def test_wrong_project_and_code_prefix_do_not_create_activities(conversation):
    c,h,_,process,state=planning_case(conversation,'Q,P-A-0001,Wrong project,2026-07-01,2026-07-02\n')
    process('Process');answer=process('Confirmed')
    assert 'PROJECT_CODE_MISMATCH' in answer
    assert c.get('/api/workspace/activities').json()==[]
    _,_,_,process,state=planning_case(conversation,'P,Q-A-0001,Wrong prefix,2026-07-01,2026-07-02\n')
    answer=process('Process') # Already reviewed layout is reusable, but bad values are rejected.
    assert 'ACTIVITY_CODE_FORMAT' in answer
    assert c.get('/api/workspace/activities').json()==[]


def test_conflicting_planning_is_atomic_and_does_not_rewrite_event(conversation):
    c,h,_,process,_=planning_case(conversation,'P,P-A-0001,Workshop,2026-07-01,2026-07-03\n')
    process('Process');process('Confirmed')
    original=c.get('/api/workspace/activities').json()
    _,_,_,conflict,state=planning_case(conversation,'P,P-A-0002,Must roll back,2026-07-05,2026-07-07\nP,P-A-0001,Workshop,2026-07-01,2026-07-04\n')
    assert 'PLANNING_ACTIVITY_CONFLICT' in conflict('Process')
    assert c.get('/api/workspace/activities').json()==original


def test_codeless_reexport_reuses_unique_exact_event_identity(conversation):
    c,h,_,process,_=planning_case(conversation,'P,,Same event,2026-07-01,2026-07-03\n')
    process('Process');process('Confirmed')
    # Formatting changes to the same exact event do not create another identity.
    _,_,_,again,_=planning_case(conversation,'P,,Same event,2026-07-01,2026-07-03\n\n')
    assert 'MISSING_ACTIVITY_CODE' in again('Process')
    assert c.get('/api/workspace/activities').json()==[]


def test_manual_activity_creation_and_prefix_rewrite_are_blocked(conversation):
    c,h,conv,send,state,*_=conversation
    assert c.post('/api/workspace/projects/1/activities',headers=h,json={'name':'Unlinked'}).status_code==409
    send('Process');send('Confirmed')
    r=c.patch('/api/workspace/projects/1',headers=h,json={'name':'Renamed','code':'OTHER'})
    assert r.status_code==409 and 'permanent' in r.json()['detail']
    assert c.patch('/api/workspace/projects/1',headers=h,json={'name':'Renamed','code':'P'}).status_code==204


def test_timesheet_cannot_create_activity(conversation):
    c,h,conv,send,state,upload,files,_=conversation
    new=c.post('/api/chat/conversations',headers=h).json()['id']
    ids=upload({'claims.csv':files['timesheets_valid.csv']},new)
    def chat(message):return c.post(f'/api/chat/conversations/{new}/messages',headers=h,json={'message':message,'request_id':str(uuid4()),'document_ids':ids,'project_id':1})
    chat('Process');result=chat('Confirmed')
    assert 'ACTIVITY_NOT_IN_PLANNING' in result.json()['message']['text']
    assert c.get('/api/workspace/activities').json()==[]


def test_unknown_report_activity_is_not_registered_by_report_adapter(conversation):
    import pytest
    from timmy.report_reconciliation import ReportEvent,synchronize
    c,*_=conversation
    class Provider:
        source='synthetic-only'
        def health(self):return 'ready'
        def events(self,*args):return [ReportEvent(report_id='R',version='1',submitted_at='2026-07-01T00:00:00Z',
            validated_at='2026-07-02T00:00:00Z',evidence_ref='test-only')]
    with pytest.raises(ValueError,match='not registered'):
        synchronize(c.app.state.engine,Provider(),project_id=1,activity_code='P-A-0099',timezone='UTC')
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(activities))==0
        assert db.scalar(select(func.count()).select_from(ExternalReportVersion))==0


def test_migration_preserves_legacy_activity_and_unlinked_report(tmp_path,monkeypatch):
    from alembic import command
    from alembic.config import Config
    from timmy.config import settings
    from timmy.database import make_engine
    from sqlalchemy import text
    url=f'sqlite:///{tmp_path / "legacy.db"}'
    monkeypatch.setenv('TIMMY_DATABASE_URL',url);settings.cache_clear()
    config=Config('backend/alembic.ini')
    try:
        command.upgrade(config,'0013')
        engine=make_engine(url)
        with engine.begin() as db:
            db.execute(text("INSERT INTO projects(id,name,project_code,status) VALUES(1,'Legacy project','P','active')"))
            db.execute(text("INSERT INTO activities(id,project_id,name) VALUES(7,1,'Legacy manual event')"))
            db.execute(text("""INSERT INTO external_report_versions(id,project_id,activity_code,source,report_id,version,
                submitted_at,local_date,validated_at,evidence_ref,cutoff)
                VALUES(9,1,'TRN-01','synthetic','R','1','2026-07-01T00:00:00Z','2026-07-01','2026-07-02T00:00:00Z','test-only','2026-07-01')"""))
        command.upgrade(config,'head');command.check(config)
        with engine.connect() as db:
            row=db.execute(text('SELECT id,name,activity_code FROM activities')).one()
            assert tuple(row)==(7,'Legacy manual event',None)
            report=db.execute(text('SELECT activity_id,cutoff FROM external_report_versions')).one()
            assert tuple(report)==(None,'2026-07-01')
        engine.dispose()
    finally:settings.cache_clear()


def test_ambiguous_or_duplicate_planning_events_need_explicit_codes(conversation):
    c,h,_,process,_=planning_case(conversation,'P,P-A-0001,Same event,2026-07-01,2026-07-03\nP,P-A-0002,Same event,2026-07-01,2026-07-03\n')
    process('Process');process('Confirmed')
    _,_,_,ambiguous,_=planning_case(conversation,'P,,Same event,2026-07-01,2026-07-03\n')
    assert 'MISSING_ACTIVITY_CODE' in ambiguous('Process')
    _,_,_,duplicate,_=planning_case(conversation,'P,,New event,2026-07-04,2026-07-06\nP,,New event,2026-07-04,2026-07-06\n')
    assert 'MISSING_ACTIVITY_CODE' in duplicate('Process')
    assert len(c.get('/api/workspace/activities').json())==2


def test_AC_02_source_format_is_not_hardcoded_to_project_prefix(conversation):
    from timmy.models import PlanningCodeContract
    c,*_=conversation
    with Session(c.app.state.engine) as db,db.begin():
        db.get(PlanningCodeContract,1).code_pattern='TRN-[0-9]{2}'
    c,h,_,process,_=planning_case(conversation,'P,TRN-01,Source event,2026-07-01,2026-07-03\n')
    process('Process');process('Confirmed')
    assert c.get('/api/workspace/activities').json()[0]['activity_code']=='TRN-01'


def test_AC_03_source_code_cannot_be_reassigned_across_projects(conversation):
    from timmy.models import PlanningCodeContract,projects
    c,*_=conversation
    with Session(c.app.state.engine) as db,db.begin():
        db.get(PlanningCodeContract,1).code_pattern='TRN-[0-9]{2}'
        db.execute(insert(activities).values(project_id=2,name='Other project',activity_code='TRN-01',code_authority='source_supplied'))
    c,h,_,process,_=planning_case(conversation,'P,TRN-01,Conflicting event,2026-07-01,2026-07-03\n')
    process('Process');answer=process('Confirmed')
    assert 'ACTIVITY_CODE_PROJECT_CONFLICT' in answer
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(activities.c.project_id).where(activities.c.activity_code=='TRN-01'))==2


def test_legacy_generated_code_is_held_without_reinterpretation(conversation):
    c,*_=conversation
    with Session(c.app.state.engine) as db,db.begin():
        db.execute(insert(activities).values(project_id=1,name='Historic generated event',activity_code='P-A-0001'))
    c,h,_,process,_=planning_case(conversation,'P,P-A-0001,Historic generated event,2026-07-01,2026-07-03\n')
    process('Process');assert 'LEGACY_ACTIVITY_CODE_REVIEW_REQUIRED' in process('Confirmed')
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(activities.c.code_authority))=='legacy_review_required'


def test_missing_source_format_contract_blocks_instead_of_guessing(conversation):
    from timmy.models import PlanningCodeContract
    c,*_=conversation
    with Session(c.app.state.engine) as db,db.begin():db.delete(db.get(PlanningCodeContract,1))
    _,_,_,process,_=planning_case(conversation,'P,P-A-0001,Source event,2026-07-01,2026-07-03\n')
    process('Process');assert 'PLANNING_CODE_CONTRACT_REQUIRED' in process('Confirmed')


def test_migration_holds_historical_generated_code_without_rewriting(tmp_path,monkeypatch):
    from alembic import command
    from alembic.config import Config
    from timmy.config import settings
    from timmy.database import make_engine
    from sqlalchemy import text
    url=f'sqlite:///{tmp_path / "authority.db"}'
    monkeypatch.setenv('TIMMY_DATABASE_URL',url);settings.cache_clear()
    config=Config('backend/alembic.ini')
    try:
        command.upgrade(config,'0015');engine=make_engine(url)
        with engine.begin() as db:
            db.execute(text("INSERT INTO projects(id,name,project_code,status) VALUES(1,'Legacy','P','active')"))
            db.execute(text("INSERT INTO activities(id,project_id,name,activity_code) VALUES(8,1,'Generated previously','P-A-0001')"))
        command.upgrade(config,'head');command.check(config)
        with engine.connect() as db:
            assert tuple(db.execute(text('SELECT id,activity_code,code_authority FROM activities')).one())==(8,'P-A-0001','legacy_review_required')
        engine.dispose()
    finally:settings.cache_clear()


def test_global_activity_code_unique_constraint(conversation):
    import pytest
    from sqlalchemy.exc import IntegrityError
    c,*_=conversation
    with pytest.raises(IntegrityError),Session(c.app.state.engine) as db,db.begin():
        db.execute(insert(activities).values(project_id=1,name='One',activity_code='SRC-001'))
        db.execute(insert(activities).values(project_id=2,name='Two',activity_code='SRC-001'))


def test_duplicate_source_codes_require_review_and_roll_back(conversation):
    row = 'P,P-A-0001,Repeated source identity,2026-07-01,2026-07-03\n'
    c,h,_,process,state = planning_case(conversation, row + row)
    process('Process')
    assert 'DUPLICATE_ACTIVITY_CODE' in process('Confirmed')
    assert state()['stage'] == 'HUMAN_REVIEW_REQUIRED'
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(activities)) == 0
        assert db.scalar(select(func.count()).select_from(activity_planning_sources)) == 0


def test_migration_collision_preflight_preserves_both_legacy_rows(tmp_path,monkeypatch):
    import pytest
    from alembic import command
    from alembic.config import Config
    from timmy.config import settings
    from timmy.database import make_engine
    from sqlalchemy import text
    url=f'sqlite:///{tmp_path / "collision.db"}'
    monkeypatch.setenv('TIMMY_DATABASE_URL',url);settings.cache_clear()
    cfg=Config('backend/alembic.ini')
    try:
        command.upgrade(cfg,'0015');engine=make_engine(url)
        with engine.begin() as db:
            db.execute(text("INSERT INTO projects(id,name,project_code,status) VALUES(1,'One','P','active'),(2,'Two','Q','active')"))
            db.execute(text("INSERT INTO activities(project_id,name,activity_code) VALUES(1,'One','SRC-01'),(2,'Two','SRC-01')"))
        with pytest.raises(RuntimeError,match='collisions'):command.upgrade(cfg,'head')
        with engine.connect() as db:
            assert db.execute(text('SELECT count(*) FROM activities')).scalar()==2
            assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='0015'
        engine.dispose()
    finally:settings.cache_clear()
