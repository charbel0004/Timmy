from dataclasses import replace
from datetime import date, timedelta

import pytest

from timmy.session_rules import Claim, coverage

START = date(2026, 7, 12)
END = START + timedelta(days=10)


def synthetic(days):
    return [
        Claim(index * 2 + offset, str(offset), role, index,
              START + timedelta(days=day), END)
        for index, day in enumerate(days, 1)
        for offset, role in enumerate(("TRAINER", "LOGISTIC"))
    ]


@pytest.mark.parametrize(("days", "complete"), [
    ([0, 0, 0, 1, 1, 1], True),
    ([0, 0, 1, 1, 2, 2], True),
    ([0, 1, 1, 2, 2, 2], False),
    ([0, 0, 0, 0, 1, 1], False),
    ([1, 0, 0, 1, 1, 1], False),
    ([0] * 6, False),
])
def test_activity_day_patterns(days, complete):
    assert coverage(synthetic(days), start=START, end=END).complete is complete


@pytest.mark.parametrize(("change", "code"), [
    ({"staff_id": None}, "MISSING_STAFF_ID"),
    ({"staff_id": "1"}, "SAME_STAFF_BOTH_ROLES"),
    ({"role": "UNKNOWN"}, "ROLE_UNKNOWN"),
    ({"session": None}, "MISSING_SESSION_NUMBER"),
    ({"work_date": None}, "MISSING_SESSION_DATE"),
    ({"submitted": START - timedelta(days=1)}, "SUBMISSION_PRECEDES_WORK"),
    ({"work_date": START - timedelta(days=1)}, "PLANNED_DATE_OUT_OF_RANGE"),
])
def test_invalid_claim_blocks_activity(change, code):
    rows = synthetic([0, 0, 0, 1, 1, 1])
    rows[0] = replace(rows[0], **change)
    result = coverage(rows, start=START, end=END)
    assert not result.complete
    assert code in {issue.code for issue in result.issues}


def test_conflicts_keep_both_source_references():
    rows = synthetic([0, 0, 0, 1, 1, 1])
    rows.append(replace(rows[0], source_row_id=99, staff_id="99"))
    result = coverage(rows, start=START, end=END)
    assert not result.complete
    issue = next(issue for issue in result.issues if issue.code == "ROLE_ASSIGNMENT_CONFLICT")
    assert {rows[0].source_row_id, 99} <= set(issue.source_rows)


def test_cutoff_rechecks_completeness():
    rows = synthetic([0, 0, 0, 1, 1, 1])
    assert coverage(rows, start=START, end=END).complete
    result = coverage(rows, start=START, end=END, cutoff=START)
    assert not result.complete
    assert len(result.accepted) == 6
    assert sum(issue.code == "AFTER_VALIDATED_REPORT_CUTOFF" for issue in result.issues) == 6
