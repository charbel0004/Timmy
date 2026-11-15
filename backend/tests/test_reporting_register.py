"""Deterministic fixture register uses the same XLSX upload/declaration path."""
from io import BytesIO
from uuid import uuid4
from openpyxl import Workbook
from sqlalchemy import insert, select, func
from sqlalchemy.orm import Session
from test_conversation_workflow import conversation
from test_foundation import client, ORIGIN, PASSWORD
from timmy.models import ExternalReportVersion, ReportingRegisterImport, ReportingRegisterDecision, activities

HEADERS=['project_code','activity_code','External report reference','Version','Submitted at','Validation status','Validated at','Source evidence']


def fixture_export(rows):
    book=Workbook(); sheet=book.active; sheet.title='Official report history'
    sheet.append(HEADERS)
    for row in rows: sheet.append(row)
    data=BytesIO(); book.save(data); book.close(); return data.getvalue()


def setup(conversation):
    c,h,conv,*_=conversation
    with Session(c.app.state.engine) as db, db.begin():
        db.execute(insert(activities).values(project_id=1,name='Synthetic activity',activity_code='TEST-A-001',
                   planned_start='2026-09-01',planned_end='2026-09-30',code_authority='source_supplied'))
    source=c.post('/api/reporting-register/sources',headers=h,json={'name':'Official fixture register','project_ids':[1],'approved_source':True})
    assert source.status_code==201,source.text
    def upload(rows):
        response=c.post('/api/documents',params={'filename':f'official-{uuid4()}.xlsx','conversation_id':conv},
                        content=fixture_export(rows),headers=h|{'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
        assert response.status_code==201,response.text
        file=response.json()
        pending=c.get(f'/api/reporting-register/conversations/{conv}').json()
        candidate=next(x for x in pending if x['file_id']==file['id'])
        return {'source_id':source.json()['id'],'file_id':file['id'],'sha256':file['sha256'],
                'official_export_declared':True,'sheets':[{'sheet_index':s['sheet_index'],'columns':s['columns']} for s in candidate['sheets']]}
    def confirm(body):
        return c.post(f'/api/reporting-register/conversations/{conv}/confirm',headers=h,json=body)
    return c,h,conv,upload,confirm


def row(version='1',status='VALIDATED',submitted='2026-09-06 10:00:00',validated='2026-09-07 12:00:00',evidence='TEAM-VALIDATION-1'):
    return ['P','TEST-A-001','REPORT-1',version,submitted,status,validated,evidence]


def test_upload_alone_cannot_establish_report_authority_and_confirmation_is_declared(conversation):
    c,h,conv,upload,confirm=setup(conversation)
    body=upload([row()])
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(ExternalReportVersion))==0
    refused=confirm({**body,'official_export_declared':False})
    assert refused.status_code==422
    response=confirm(body); assert response.status_code==200,response.text
    data=response.json()
    assert data['assurance']=='coordinator_declared_not_independently_authenticated'
    assert data['evaluation']['rows'][0]['accepted'] is True
    assert data['evaluation']['rows'][0]['cutoff']=='2026-09-06'
    repeat=confirm(body); assert repeat.status_code==200
    assert repeat.json()['idempotent'] is True
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(ReportingRegisterImport))==1
        assert db.scalar(select(func.count()).select_from(ExternalReportVersion))==1
        assert db.scalar(select(func.count()).select_from(ReportingRegisterDecision))==1


def test_new_versions_cannot_extend_frozen_cutoff_and_conflicts_are_retained(conversation):
    c,h,conv,upload,confirm=setup(conversation)
    assert confirm(upload([row()])).status_code==200
    newer=confirm(upload([row('2',submitted='2026-09-20 10:00:00',validated='2026-09-21 12:00:00')]))
    assert newer.status_code==200,newer.text
    assert newer.json()['evaluation']['rows'][0]['cutoff']=='2026-09-06'
    conflict=confirm(upload([row(submitted='2026-09-08 10:00:00')]))
    assert 'CONFLICTING_REPORT_HISTORY' in conflict.json()['evaluation']['rows'][0]['issue_codes']
    with Session(c.app.state.engine) as db:
        versions=list(db.scalars(select(ExternalReportVersion).order_by(ExternalReportVersion.id)))
        assert len(versions)==2 and versions[0].cutoff=='2026-09-06' and versions[1].cutoff is None
        assert versions[0].submitted_at.startswith('2026-09-06')
        from timmy.documents import project_report_cutoffs
        assert project_report_cutoffs(db,1)=={}


def test_statuses_are_preserved_and_insufficient_evidence_cannot_be_accepted(conversation):
    c,h,conv,upload,confirm=setup(conversation)
    variants=[row('1','NOT_SUBMITTED',None,None,None),row('2','SUBMITTED',validated=None),
              row('3','REJECTED',validated=None),row('4','REQUIRES_CORRECTION',validated=None),
              row('5',evidence=None),row('6',validated='2026-09-01 10:00:00')]
    response=confirm(upload(variants)); assert response.status_code==200,response.text
    result=response.json()['evaluation']['rows']
    assert {x['register_status'] for x in result}>={'NOT_SUBMITTED','AWAITING_VALIDATION','REJECTED','REQUIRES_CORRECTION','VALIDATED'}
    assert not any(x['accepted'] for x in result)
    with Session(c.app.state.engine) as db:
        assert not any(x.cutoff for x in db.scalars(select(ExternalReportVersion)))


def test_initial_export_freezes_earliest_validation_even_when_rows_are_reversed(conversation):
    c,h,conv,upload,confirm=setup(conversation)
    response=confirm(upload([row('2',submitted='2026-09-20 10:00:00',validated='2026-09-21 12:00:00'),row()]))
    assert response.status_code==200,response.text
    with Session(c.app.state.engine) as db:
        frozen=db.scalar(select(ExternalReportVersion).where(ExternalReportVersion.cutoff.is_not(None)))
        assert frozen.version=='1' and frozen.cutoff=='2026-09-06'


def test_designation_and_declaration_check_csrf_and_current_permissions(conversation):
    c,h,conv,upload,confirm=setup(conversation)
    body=upload([row()])
    assert c.post(f'/api/reporting-register/conversations/{conv}/confirm',headers=ORIGIN,json=body).status_code==403
    c.post('/api/auth/login',headers=ORIGIN,json={'username':'reviewer','password':PASSWORD})
    assert c.get(f'/api/reporting-register/conversations/{conv}').status_code==404


def test_submitted_then_validated_register_version_freezes_only_after_validation_evidence(conversation):
    c,h,conv,upload,confirm=setup(conversation)
    pending=confirm(upload([row(status='SUBMITTED',validated=None)]))
    assert pending.status_code==200 and not pending.json()['evaluation']['rows'][0]['accepted']
    with Session(c.app.state.engine) as db:
        assert db.scalar(select(ExternalReportVersion)).cutoff is None
    accepted=confirm(upload([row()]))
    assert accepted.status_code==200 and accepted.json()['evaluation']['rows'][0]['accepted']
    with Session(c.app.state.engine) as db:
        version=db.scalar(select(ExternalReportVersion))
        assert version.cutoff=='2026-09-06'
        assert version.evidence_ref.startswith(accepted.json()['import_id']+':')


def test_register_cutoff_accepts_boundary_work_day_but_not_later_claims(conversation):
    from timmy.session_rules import Claim,coverage
    from datetime import date
    c,h,conv,upload,confirm=setup(conversation)
    confirmed=confirm(upload([row()]))
    assert confirmed.status_code==200
    cutoff=date.fromisoformat(confirmed.json()['evaluation']['rows'][0]['cutoff'])
    claims=[Claim(i,'STAFF-A' if i%2 else 'STAFF-B','TRAINER' if i%2 else 'LOGISTIC',(i+1)//2,cutoff,date(2026,9,26)) for i in range(1,13)]
    result=coverage(claims,start=date(2026,9,1),end=date(2026,9,30),cutoff=cutoff)
    assert not any(i.code=='AFTER_VALIDATED_REPORT_CUTOFF' for i in result.issues)
    late=Claim(13,'STAFF-A','TRAINER',1,date(2026,9,7),date(2026,9,26))
    assert any(i.code=='AFTER_VALIDATED_REPORT_CUTOFF' for i in coverage([late],start=date(2026,9,1),end=date(2026,9,30),cutoff=cutoff).issues)


def test_conflicting_status_and_duplicate_versions_never_establish_cutoff(conversation):
    c,h,conv,upload,confirm=setup(conversation)
    response=confirm(upload([row(status='REJECTED'),row('2'),row('2')]))
    assert response.status_code==200,response.text
    rows=response.json()['evaluation']['rows']
    assert not any(r['accepted'] for r in rows)
    assert any('CONTRADICTORY_REPORT_STATUS' in r['issue_codes'] for r in rows)
    assert any('DUPLICATE_REPORT_VERSION_IN_EXPORT' in r['issue_codes'] for r in rows)
    with Session(c.app.state.engine) as db:
        assert not any(r.cutoff for r in db.scalars(select(ExternalReportVersion)))
