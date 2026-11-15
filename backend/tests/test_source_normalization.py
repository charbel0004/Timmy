from datetime import date
from types import SimpleNamespace
from timmy.source_dates import source_date
from timmy.global_source_views import preview_documents_for_project
from timmy.column_mappings import propose_sheet
from timmy.workflows import choose_workflow


def test_excel_dates_are_candidates_without_accepting_ambiguous_times():
    assert source_date('2026-09-04 00:00:00') == date(2026,9,4)
    assert source_date('2026-09-04') == date(2026,9,4)
    assert source_date('09/04/2026') is None
    assert source_date('2026-09-04 13:15:00') is None


def test_shared_directory_retained_only_alongside_matching_project_evidence():
    file = SimpleNamespace(id='source', sha256='a'*64, original_filename='source.xlsx')
    record = SimpleNamespace(sheets=[
        {'name':'Planning','rows':[{'row':1,'values':['project_code','activity_code']},{'row':2,'values':['TCD','26-TCD-001']}]},
        {'name':'Staff','rows':[{'row':1,'values':['staff_id','status']},{'row':2,'values':['S1','active']}]},
    ])
    views = preview_documents_for_project([(file,record)], 1, 'TCD')
    assert [s['name'] for s in views[0][1].sheets] == ['Planning','Staff']
    assert preview_documents_for_project([(file,record)],2,'UNKNOWN') == []
    assert record.sheets[1]['rows'][1]['values'] == ['S1','active']


def test_hourly_and_report_mapping_have_distinct_categories():
    file=SimpleNamespace(id='source',original_filename='source.xlsx')
    for headers,kind in [(['project_code','staff_id','role','work_date','Clock in','Clock out'],'hours'),
                         (['project_code','activity_code','External report reference','Validated at','Validation status'],'reports')]:
        mapping=propose_sheet(file,{'name':'Sheet','rows':[{'row':1,'values':headers}]},0)
        assert mapping['kind']==kind


def test_combined_processing_and_payment_intent_preserves_financial_goal_and_negation():
    assert choose_workflow('Process the documents and give me a final payment request.') == 'weekly_cycle'
    assert choose_workflow('Process documents but do not prepare a payment request.') != 'weekly_cycle'


def test_every_workflow_step_has_a_prerequisite_outcome_and_action():
    from timmy.workflow_contracts import catalog
    for workflow in catalog():
        assert workflow['trigger_pattern'] and workflow['trigger'] and workflow['execution_path'] and workflow['steps']
        for step in workflow['steps']:
            assert all(step[key] for key in ('prerequisites','expected_outcome','next_action','availability'))


def test_hourly_diagnostics_use_deterministic_rules_but_never_confer_authority():
    from timmy.hourly_preview import preview_hours
    headers=['project_code','activity_code','staff_id','role','work_date','Clock in','Clock out','timesheet_submitted_date']
    record=SimpleNamespace(sheets=[{'name':'Shift claims','rows':[
        {'row':1,'values':headers},
        {'row':2,'values':['FOS','26-FOS-001','SYN-1','DRIVER','2026-09-08 00:00:00','08:00:00','16:30:00','2026-09-09 00:00:00']},
    ]}])
    file=SimpleNamespace(id='original',original_filename='hours.xlsx')
    result=preview_hours([(file,record)],'FOS')
    assert '510 unique minutes' in result and '40.00' in result
    assert 'not payment entitlements' in result


def test_standalone_shared_directory_is_preserved_for_an_existing_project_view():
    f=SimpleNamespace(id='planning',sha256='a'*64,original_filename='planning.xlsx')
    d=SimpleNamespace(id='directory',sha256='b'*64,original_filename='staff.xlsx')
    plan=SimpleNamespace(sheets=[{'name':'Plan','rows':[{'row':1,'values':['project_code']},{'row':2,'values':['TCD']}]}])
    staff=SimpleNamespace(sheets=[{'name':'Staff','rows':[{'row':1,'values':['staff_id','status']},{'row':2,'values':['S1','active']}]}])
    assert len(preview_documents_for_project([(f,plan),(d,staff)],1,'TCD')) == 2


def test_known_planning_approval_status_cannot_be_dropped_from_review():
    from timmy.column_mappings import mapping_errors
    file=SimpleNamespace(id='source',original_filename='planning.xlsx')
    mapping=propose_sheet(file,{'name':'Planning','rows':[{'row':1,'values':[
        'Project code','Activity code','Approved start date','Approved end date','Approval status']} ]},0)
    assert mapping_errors([mapping])==[]
    mapping['columns'].pop('approval_status')
    assert any('approval-status' in error for error in mapping_errors([mapping]))
