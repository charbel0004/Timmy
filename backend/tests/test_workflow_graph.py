"""Synthetic-only control-flow regression tests. No financial handler is run."""
import pytest

from timmy.workflow_graph import execute_graph


def result(step, status):
    return {'step':step,'status':status,'issue_codes':[]}


@pytest.mark.parametrize('hold', ['needs_review', 'blocked', 'failed'])
def test_depends_stop_after_first_hold(hold):
    visited=[]
    output=execute_graph(['one','two','three'],lambda step: visited.append(step) or result(step,hold))
    assert visited == ['one']
    assert output[1]['blocked_by'] == 'one'
    assert output[2]['issue_codes'] == ['DEPENDENCY_NOT_SATISFIED']
    assert not any(item['executed'] for item in output[1:])


def test_all_success_invokes_in_order_once():
    visited=[]
    output=execute_graph(['one','two'],lambda step: visited.append(step) or result(step,'completed'))
    assert visited == ['one','two']
    assert all(item['status']=='completed' for item in output)


def test_bad_result_fails_closed_and_stops():
    visited=[]
    def evaluator(step):
        visited.append(step)
        return {'step':step,'status':'unrecognized'}
    output=execute_graph(['one','two'],evaluator)
    assert visited==['one']
    assert output[0]['issue_codes']==['INVALID_STEP_RESULT']
    assert output[1]['attempted'] is False


def test_exception_is_safe_and_not_retried():
    attempts=[]
    def evaluator(step):
        attempts.append(step)
        raise ValueError('secret row that must not appear in outcome')
    output=execute_graph(['one','two'],evaluator)
    assert attempts==['one']
    assert output[0]['issue_codes']==['WORKFLOW_STEP_UNEXPECTED_ERROR']
    assert 'secret' not in str(output)


def test_invalid_steps_rejected():
    with pytest.raises(ValueError):
        execute_graph(['same','same'],lambda step:result(step,'completed'))
