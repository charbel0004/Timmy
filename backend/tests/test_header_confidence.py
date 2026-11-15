"""Independent document-type detection and automatic high-confidence mapping."""
from uuid import uuid4
import pytest
from test_foundation import client  # noqa: F401
from test_excel_register_acceptance import coordinator, load  # noqa: F401
from timmy.column_mappings import propose_sheet
from timmy.documents import parse


class File:
    def __init__(self, name='upload.csv'):
        self.id = 'file-1'
        self.original_filename = name


def sheet_of(header, *rows):
    lines = [header, *rows]
    sheets, _ = parse(('\n'.join(lines) + '\n').encode(), '.csv')
    return sheets[0]


def classify(header):
    return propose_sheet(File(), sheet_of(header), 0)


@pytest.mark.parametrize('header,kind', [
    ('project_code,activity_code,staff_id,role,session_number,work_date,timesheet_submitted_date', 'claims'),
    ('project_code,activity_code,staff_id,role,clock_in,clock_out,work_date,timesheet_submitted_date', 'hours'),
    ('project_code,activity_code,report_id,report_version,submitted_at,validation_status,validated_at,evidence_ref', 'reports'),
    ('project_code,activity_code,activity_name,approved_start_date,approved_end_date,approval_status', 'planning'),
    ('staff_id,status', 'directory'),
    ('project_code,project_name', 'projects'),
])
def test_document_type_is_identified_independently_from_its_own_headers(header, kind):
    proposal = classify(header)
    assert proposal['kind'] == kind
    assert proposal['confidence'] == 'high'
    assert proposal['confidence_basis'] in {'distinctive_headers', 'complete_exact_headers'}


def test_missing_required_column_requires_a_human_mapping():
    proposal = classify('project_code,activity_code,staff_id,work_date,timesheet_submitted_date')
    assert proposal['kind'] == 'claims'
    assert proposal['confidence'] == 'review_required'


def test_duplicate_field_columns_require_a_human_mapping():
    proposal = classify('project_code,activity_code,staff_id,role,session_number,date,work_date,'
                        'timesheet_submitted_date')
    assert proposal['conflicts'] == ['work_date']
    assert proposal['confidence'] == 'review_required'


def test_unrecognized_headers_are_never_applied_automatically():
    proposal = classify('alpha,beta,gamma')
    assert proposal['kind'] == 'unsupported'
    assert proposal['confidence'] == 'review_required'


def upload_suite(c, h, conv, suite):
    from pathlib import Path
    fixtures = Path(__file__).parent / 'fixtures/excel_acceptance'
    for path in sorted((fixtures / suite).glob('*.xlsx')):
        response = c.post('/api/documents', params={'filename': path.name, 'conversation_id': conv},
                          content=path.read_bytes(), headers=h | {
                              'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
        assert response.status_code == 201, response.text
    replied = c.post(f'/api/chat/conversations/{conv}/messages', headers=h,
                     json={'message': 'Process the documents and give me a final payment request.',
                           'request_id': str(uuid4())})
    assert replied.status_code == 200, replied.text
    return replied.json()['message']['text']


def test_matching_workbook_continues_without_a_mapping_confirmation(coordinator):
    c, h, conv = coordinator
    reply = upload_suite(c, h, conv, '01_Happy_Path')
    assert 'no mapping review was required' in reply
    review = c.get(f'/api/global-mappings/{conv}').json()
    assert review['confirmed'] is True and review['automatic'] is True
    assert review['errors'] == []
    assert {sheet['kind'] for sheet in review['sheets']} == {
        'planning', 'directory', 'reports', 'hours', 'claims'}
    assert all(sheet['confidence'] == 'high' for sheet in review['sheets'])
    assert review['errors'] == []


def test_ambiguous_workbook_still_requests_a_human_mapping(coordinator):
    c, h, conv = coordinator
    header = 'project_code,activity_code,staff_id,role,date,timesheet_submitted_date'
    body = '\n'.join([header, 'TCD,26-TCD-001,T1,TRAINER,2026-09-01,2026-09-05']) + '\n'
    uploaded = c.post('/api/documents', params={'filename': 'claims.csv', 'conversation_id': conv},
                      content=body.encode(), headers=h | {'Content-Type': 'text/csv'})
    assert uploaded.status_code == 201, uploaded.text
    c.post(f'/api/chat/conversations/{conv}/messages', headers=h,
           json={'message': 'Process', 'request_id': str(uuid4())})
    review = c.get(f'/api/global-mappings/{conv}').json()
    assert review['confirmed'] is False and review['automatic'] is False
    assert any('missing required field' in error for error in review['errors'])


def test_automatic_mapping_stays_correctable_by_an_authorized_human(coordinator):
    c, h, conv = coordinator
    upload_suite(c, h, conv, '01_Happy_Path')
    review = c.get(f'/api/global-mappings/{conv}').json()
    assert review['automatic'] is True
    corrected = [dict(sheet) for sheet in review['sheets']]
    directory = next(sheet for sheet in corrected if sheet['kind'] == 'directory')
    directory['columns'] = {'staff_id': 1, 'status': 0}
    response = c.post(f'/api/global-mappings/{conv}/confirm', headers=h,
                      json={'fingerprint': review['fingerprint'],
                            'sheets': [{k: sheet[k] for k in ('file_id', 'sheet_index', 'kind', 'columns')}
                                       for sheet in corrected]})
    assert response.status_code == 200, response.text
    current = c.get(f'/api/global-mappings/{conv}').json()
    assert current['automatic'] is False
    assert next(sheet for sheet in current['sheets']
                if sheet['kind'] == 'directory')['columns'] == {'staff_id': 1, 'status': 0}
