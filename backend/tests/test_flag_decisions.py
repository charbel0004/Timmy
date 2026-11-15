"""One end-of-run decision pass: persisted flags, exclusion-only dispositions, gates intact."""
from decimal import Decimal
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_foundation import client  # noqa: F401
from test_excel_register_acceptance import coordinator, load, declare, review  # noqa: F401
from timmy.models import WorkflowFinding, WorkflowPaymentApproval


def decision_round(c, conv):
    response = c.get(f'/api/workflow-findings/conversations/{conv}')
    assert response.status_code == 200, response.text
    return response.json()


def decide(c, h, finding, decision='invalidate', evidence='INDEPENDENT_FLAG_DECISION_EVIDENCE'):
    return c.post(f'/api/workflow-findings/{finding["id"]}/decide', headers=h,
                  json={'decision': decision, 'evidence_ref': evidence})


def drafts(c, conv):
    return c.get(f'/api/workflow-payments/conversations/{conv}').json()


def test_open_flags_block_payment_and_project_wide_findings_cannot_be_excluded(coordinator):
    c, h, conv = coordinator
    load(coordinator, '02_Mixed_Data_And_Discrepancies')
    declare(coordinator)
    review(coordinator)
    round = decision_round(c, conv)
    assert round['open_total'] > 0 and round['ready_for_payment'] is False
    assert drafts(c, conv) == []
    scopes = {finding['scope'] for project in round['projects'] for finding in project['findings']}
    assert {'activity', 'project'} <= scopes
    project_finding = next(finding for project in round['projects']
                           for finding in project['findings'] if finding['scope'] == 'project')
    refused = decide(c, h, project_finding)
    assert refused.status_code == 409 and 'PROJECT_SCOPE_FINDING_REQUIRES_EVIDENCE' in refused.text
    escalated = decide(c, h, project_finding, decision='escalate')
    assert escalated.status_code == 200, escalated.text
    assert escalated.json()['state'] == 'escalated'
    replay = decide(c, h, project_finding, decision='escalate')
    assert replay.status_code == 200 and replay.json()['decided'] == 1
    changed = decide(c, h, project_finding, decision='correct_source')
    assert changed.status_code == 409 and 'FLAG_ALREADY_DECIDED' in changed.text
    with Session(c.app.state.engine) as db:
        assert not list(db.scalars(select(WorkflowPaymentApproval)))


def test_invalidation_excludes_affected_records_and_reaches_one_payment_request(coordinator):
    c, h, conv = coordinator
    load(coordinator, '03_Boundaries_And_Financial_Controls')
    declare(coordinator)
    review(coordinator)
    round = decision_round(c, conv)
    by_project = {project['project_code']: project for project in round['projects']}
    assert set(by_project) == {'TCD', 'FOS'}
    assert drafts(c, conv) == []

    for code in ('FOS', 'TCD'):
        for finding in by_project[code]['findings']:
            response = decide(c, h, finding)
            assert response.status_code == 200, (code, finding['code'], response.text)
    settled = decision_round(c, conv)
    assert settled['open_total'] == 0 and settled['ready_for_payment'] is True
    assert all(finding['state'] == 'invalidated'
               for project in settled['projects'] for finding in project['findings'])

    created = {draft['snapshot']['project_code']: draft for draft in drafts(c, conv)}
    assert set(created) == {'TCD', 'FOS'}
    tcd = {line['staff_id']: line['amount'] for line in created['TCD']['snapshot']['lines']}
    assert tcd == {'SYN-102': '50.00', 'SYN-104': '25.00'}
    assert sum(Decimal(value) for value in tcd.values()) == Decimal('75.00')
    fos = {(line['staff_id'], line['year'], line['month']): line['amount']
           for line in created['FOS']['snapshot']['lines']}
    assert fos == {('SYN-101', 2026, 9): '600.00', ('SYN-104', 2026, 9): '40.00',
                   ('SYN-104', 2026, 10): '20.00', ('SYN-106', 2026, 9): '40.00'}
    assert sum(Decimal(value) for value in fos.values()) == Decimal('700.00')
    excluded = created['FOS']['snapshot']['exclusions']['hours_months']
    assert excluded == ['SYN-105|2026-09', 'SYN-107|2026-09', 'SYN-108|2026-09']
    assert {'SYN-105', 'SYN-107', 'SYN-108'}.isdisjoint(
        line['staff_id'] for line in created['FOS']['snapshot']['lines'])
    assert created['TCD']['snapshot']['exclusions']['activities'] == ['26-TCD-002', '26-TCD-003', '26-TCD-004']
    assert set(created['FOS']['snapshot']['decisions'][0]) >= {'id', 'code', 'subject', 'state', 'evidence_ref'}
    with Session(c.app.state.engine) as db:
        current = {draft['snapshot']['validation_id'] for draft in created.values()}
        stored = list(db.scalars(select(WorkflowFinding).where(
            WorkflowFinding.validation_id.in_(current))))
        assert stored and all(row.decided_by == 120 and row.decided_at and row.evidence_ref
                              for row in stored)
        assert not list(db.scalars(select(WorkflowPaymentApproval)))


def test_flag_decision_requires_the_financial_exclusion_grant(coordinator):
    from sqlalchemy import update
    from timmy.models import project_permission_overrides
    c, h, conv = coordinator
    load(coordinator, '03_Boundaries_And_Financial_Controls')
    declare(coordinator)
    review(coordinator)
    round = decision_round(c, conv)
    finding = next(finding for project in round['projects'] for finding in project['findings']
                   if finding['scope'] == 'activity')
    with Session(c.app.state.engine) as db, db.begin():
        target = db.execute(select(project_permission_overrides).where(
            project_permission_overrides.c.user_id == 120)).mappings().all()
        for item in target:
            db.execute(update(project_permission_overrides).where(
                project_permission_overrides.c.user_id == 120,
                project_permission_overrides.c.project_id == item['project_id']).values(
                permissions=[key for key in item['permissions'] if key != 'payments.allocate']))
    denied = decide(c, h, finding)
    assert denied.status_code == 403
    allowed = decide(c, h, finding, decision='escalate')
    assert allowed.status_code == 200
