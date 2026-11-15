"""Observable contracts, isolation, usage math and actual guarded workflows."""
import asyncio
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from test_foundation import client, ORIGIN, PASSWORD
from test_conversation_workflow import conversation
from timmy.ai import OllamaAdapter, OllamaExtractionError
from timmy.chat import Proposal
from timmy.config import Settings
from timmy.models import ExecutionRun, ExecutionEvent, project_memberships, project_permission_overrides
from timmy.observability import Telemetry, aggregate, current, instrument, parent, reference, safe
from timmy.workflow_graph import execute_graph


@pytest.fixture
def trace():
    manager = Telemetry(None, Settings())
    item = manager.start(1, 'test', [1])
    token = current.set(item)
    parent_token = parent.set(item.root)
    try:
        yield item
    finally:
        parent.reset(parent_token)
        current.reset(token)


def ollama(body, status=200):
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(status, json=body))) as transport:
            return await OllamaAdapter(Settings(), transport).structured([
                {'role': 'system', 'content': 'PRIVATE_INSTRUCTIONS'},
                {'role': 'user', 'content': 'PRIVATE_USER_DATA'}], Proposal)
    return asyncio.run(call())


def response(**usage):
    return dict(message={'content': '{"answer":"Hello","tool":null}'}, done=True, **usage)


def test_actual_ollama_contract_and_nanosecond_throughput(trace):
    assert ollama(response(prompt_eval_count=20, eval_count=10, eval_duration=2_000_000_000,
                           total_duration=3_000_000_000, load_duration=100)).answer == 'Hello'
    values = aggregate(trace.events)
    assert values['input_tokens'] == 20 and values['total_tokens'] == 30
    assert values['tokens_per_second'] == 5
    assert values['load_duration_ns'] == 100
    assert len([e for e in trace.events if e['event_type'] == 'span.started' and e['safe_payload'].get('category') == 'model']) == 1
    assert 'PRIVATE_' not in str(trace.events)


def test_multiple_calls_aggregate_without_duplicate_span_usage(trace):
    for _ in range(2):
        ollama(response(prompt_eval_count=12, eval_count=8, eval_duration=1_000_000_000))
    assert aggregate(trace.events)['total_tokens'] == 40
    assert aggregate(trace.events)['invocation_count'] == 2
    assert aggregate(trace.events)['tokens_per_second'] == 8


@pytest.mark.parametrize('usage', [{}, {'eval_count': -1}, {'prompt_eval_count': True}, {'eval_count': '5'}])
def test_missing_or_invalid_metadata_is_unavailable(trace, usage):
    ollama(response(**usage))
    assert aggregate(trace.events)['total_tokens'] is None
    assert aggregate(trace.events)['tokens_per_second'] is None


def test_partial_usage_does_not_become_complete_total(trace):
    ollama(response(prompt_eval_count=1, eval_count=2))
    ollama(response(eval_count=3))
    assert aggregate(trace.events)['input_tokens'] is None
    assert aggregate(trace.events)['output_tokens'] == 5
    assert aggregate(trace.events)['total_tokens'] is None


def test_tools_are_linked_and_failure_is_safe(trace):
    @instrument('outer')
    def outer():
        return inner(secret='RAW_PASSWORD')
    @instrument('inner')
    def inner(secret):
        raise RuntimeError('PRIVATE_DOCUMENT_DATA ' + secret)
    with pytest.raises(RuntimeError):
        outer()
    starts = [e for e in trace.events if e['event_type'] == 'span.started']
    assert starts[-1]['parent_span_id'] == starts[-2]['span_id']
    ends = [e for e in trace.events if e['event_type'] == 'span.ended']
    assert all(e['status'] == 'failed' for e in ends)
    assert 'RAW_PASSWORD' not in str(trace.events) and 'PRIVATE_DOCUMENT_DATA' not in str(trace.events)
    assert safe({'password': 'secret', 'reasoning': 'secret', 'arguments': {'token': 'secret'}}) == {}


def test_policy_stages_are_preserved_without_invented_citations(trace):
    for stage in ('available', 'retrieved', 'supplied', 'cited', 'executed'):
        reference('explicit-test-reference', stage, 'v1')
    assert [e['safe_payload']['stage'] for e in trace.events if e['event_type'] == 'policy.reference'] == [
        'available', 'retrieved', 'supplied', 'cited', 'executed']


def test_workflow_only_traces_invoked_steps(trace):
    results = execute_graph(['check', 'payment'], lambda step: {'step': step, 'status': 'needs_review'})
    assert results[1]['attempted'] is False
    operations = [e['safe_payload'].get('operation') for e in trace.events if e['event_type'] == 'span.started']
    assert 'check' in operations and 'payment' not in operations
    assert any(e['status'] == 'needs_review' for e in trace.events)


def test_bounded_history_reserves_terminal(trace):
    ollama(response(prompt_eval_count=1, eval_count=2))
    for _ in range(2500):
        trace.emit('resource.sample', source='test')
    trace.finish('completed')
    assert len(trace.events) == trace.manager.config.telemetry_max_events
    assert trace.events[-1]['event_type'] == 'run.finished'
    assert trace.events[-1]['safe_payload']['truncated'] is True
    assert aggregate(trace.events)['total_tokens'] is None
    assert [e['sequence_number'] for e in trace.events] == list(range(1, len(trace.events)+1))


def login(client, user='reviewer'):
    reply = client.post('/api/auth/login', headers=ORIGIN, json={'username': user, 'password': PASSWORD})
    return ORIGIN | {'X-CSRF-Token': reply.json()['csrf_token']}


def test_authenticated_replay_history_and_revocation(client, monkeypatch):
    async def reply(*args, **kwargs):
        return Proposal(answer='Hello', tool=None)
    monkeypatch.setattr(OllamaAdapter, 'structured', reply)
    headers = login(client)
    conversation = client.post('/api/chat/conversations', headers=headers).json()['id']
    result = client.post(f'/api/chat/conversations/{conversation}/messages', headers=headers,
        json={'request_id': str(uuid4()), 'message': 'Hello'})
    assert result.status_code == 200
    identifier = result.headers['X-Execution-ID']
    detail = client.get('/api/executions/' + identifier).json()
    assert detail['run']['status'] == 'completed'
    assert detail['usage']['input_tokens'] is None
    client.app.state.telemetry.flush()
    assert identifier not in client.app.state.telemetry.active
    saved = client.get('/api/executions/' + identifier).json()
    assert 'events' in saved, saved
    assert saved['events'] == detail['events']
    stream = client.get(f'/api/executions/{identifier}/events?after=2')
    assert 'event: complete' in stream.text
    assert 'id: 1\n' not in stream.text and 'id: 2\n' not in stream.text
    assert 'X-Accel-Buffering' in stream.headers
    login(client, 'unknown')
    assert client.get('/api/executions/' + identifier).status_code in (403, 404)
    login(client)
    with Session(client.app.state.engine) as db, db.begin():
        db.execute(delete(project_memberships).where(project_memberships.c.user_id == 1))
    assert client.get('/api/executions/' + identifier).status_code == 404
    assert client.get('/api/executions').json() == []


def test_instruction_metadata_requires_admin(client):
    login(client)
    assert client.get('/api/executions/instructions').status_code == 403


def test_stale_run_gets_terminal_interruption(client):
    login(client)
    manager = client.app.state.telemetry
    item = manager.start(1, 'test', [1]); manager.flush()
    identifier = item.info['id']
    manager.active.pop(identifier)
    with Session(client.app.state.engine) as db, db.begin():
        db.execute(update(ExecutionRun).where(ExecutionRun.id == identifier).values(
            heartbeat_at=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()))
    manager.flush()
    saved = client.get('/api/executions/' + identifier).json()
    assert saved['run']['status'] == 'interrupted'
    assert saved['events'][-1]['event_type'] == 'run.finished'


def test_collector_real_sources_and_unavailable_model(client):
    collector = client.app.state.telemetry.collector
    sample = collector.sample()
    assert sample['source'] == 'FastAPI host'
    assert sample['backend_pid'] > 0 and sample['backend_rss_bytes'] > 0
    assert sample['host_total_bytes'] >= sample['host_used_bytes']
    assert sample['gpu'] == 'Unavailable'
    assert 'not exclusive' in sample['attribution']


def test_telemetry_storage_failure_does_not_change_financial_results(trace, monkeypatch):
    from timmy.session_compensation import session_compensation
    baseline = session_compensation(8)
    monkeypatch.setattr(trace, '_emit', lambda *a, **kw: (_ for _ in ()).throw(OSError('collector unavailable')))
    @instrument('deterministic.calculation', 'rule')
    def calculate():
        return session_compensation(8)
    assert calculate() == baseline
    trace.manager.flush()  # Missing engine must fail open.


def test_representative_upload_review_validation_and_persisted_graph(conversation):
    c, headers, identifier, send, state, *_ = conversation
    send('Analyze these files.')
    send('Yes')
    send('Confirmed')
    assert state()['stage'] == 'HUMAN_REVIEW_REQUIRED'
    runs = c.get('/api/executions', params={'conversation_id': identifier}).json()
    details = [c.get('/api/executions/' + run['id']).json() for run in runs]
    events = [e for detail in details for e in detail['events']]
    assert any(e['safe_payload'].get('category') == 'approval' for e in events)
    assert any(e['safe_payload'].get('category') == 'validation' for e in events)
    assert any(e['safe_payload'].get('stage') == 'executed' for e in events)
    assert any(e['safe_payload'].get('stage') == 'retrieved' for e in events)
    for detail in details:
        starts = {e['span_id'] for e in detail['events'] if e['event_type'] == 'span.started'}
        assert all(e['parent_span_id'] in starts for e in detail['events'] if e['parent_span_id'])
    c.app.state.telemetry.flush()
    for detail in details:
        assert c.get('/api/executions/' + detail['run']['id']).json()['events'] == detail['events']
    # Business fixture separately verifies no payment rows; telemetry adds none.


def test_model_failure_counts_invocation_without_fabricating_usage(trace):
    with pytest.raises(OllamaExtractionError):
        ollama({'error': 'PRIVATE_PROVIDER_ERROR'}, status=503)
    assert aggregate(trace.events)['invocation_count'] == 1
    assert aggregate(trace.events)['input_tokens'] is None
    assert aggregate(trace.events)['reported_invocation_count'] == 0
    assert 'PRIVATE_PROVIDER_ERROR' not in str(trace.events)


def test_collector_distinguishes_api_host_and_absent_ollama(client, monkeypatch):
    collector = client.app.state.telemetry.collector
    monkeypatch.setattr(collector.psutil, 'process_iter', lambda *args: [])
    sample = collector.sample()
    assert sample['backend_rss_bytes'] > 0
    assert sample['ollama_rss_bytes'] is None and sample['ollama_cpu_percent'] is None
    assert sample['ollama_process_count'] == 0


def test_business_write_lock_defers_telemetry_without_changing_timeout(client):
    from time import monotonic
    manager = client.app.state.telemetry
    item = manager.start(1, 'test', [1])
    with client.app.state.engine.connect() as connection:
        original = connection.exec_driver_sql('PRAGMA busy_timeout').scalar()
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        started = monotonic(); manager.flush()
        assert monotonic()-started < 0.5
        assert item.info['id'] in manager.active
        assert connection.exec_driver_sql('PRAGMA busy_timeout').scalar() == original
        connection.rollback()
    item.finish('completed'); manager.flush()
    assert item.info['id'] not in manager.active
    with Session(client.app.state.engine) as db:
        assert db.get(ExecutionRun, item.info['id']).status == 'completed'


def test_revoking_operational_grant_hides_stored_trace(client):
    headers = login(client)
    reply = client.post('/api/chat/conversations', headers=headers)
    identifier = reply.headers['X-Execution-ID']
    client.app.state.telemetry.flush()
    with Session(client.app.state.engine) as db, db.begin():
        db.execute(project_permission_overrides.insert().values(user_id=1, project_id=1, permissions=['projects:read']))
    assert client.get('/api/executions/' + identifier).status_code == 404


def test_restart_restores_persisted_execution(client):
    from timmy.main import create_app
    from fastapi.testclient import TestClient
    headers = login(client)
    reply = client.post('/api/chat/conversations', headers=headers)
    identifier = reply.headers['X-Execution-ID']
    client.app.state.telemetry.flush()
    expected = client.get('/api/executions/' + identifier).json()['events']
    with TestClient(create_app(client.app.state.config)) as restarted:
        login(restarted)
        assert restarted.get('/api/executions/' + identifier).json()['events'] == expected


def test_overview_includes_authorized_global_uploads_and_real_workflow_outcomes(conversation):
    c, headers, identifier, send, state, *_ = conversation
    before = c.get('/api/overview').json()
    assert before['documents'] == 4 and before['active_projects'] == 1
    assert before['payment_ready'] is None and before['outstanding_obligations'] is None
    send('Analyze these files.')
    send('Yes')
    after = c.get('/api/overview').json()
    assert after['mapping_reviews'] >= 1
    assert any(item['conversation_id'] == identifier for item in after['pending_reviews'])
    assert sum(day['completed'] for day in after['workflow_trend']) >= 1
    global_upload = c.post('/api/documents', params={'conversation_id': identifier, 'filename': 'global.csv'},
                          content=b'project_code,project_name\nP,Synthetic\n', headers=headers | {'Content-Type': 'text/csv'})
    assert global_upload.status_code == 201
    assert c.get('/api/overview').json()['documents'] == len(c.get('/api/documents').json()) == 5


@pytest.mark.parametrize('revoke', [False, True])
def test_live_sse_batches_recheck_access_and_close_on_terminal(client, revoke):
    from timmy.auth import current_principal
    from timmy.observability import events
    login(client)
    item = client.app.state.telemetry.start(1, 'live-test', [1])
    async def connected():
        return False
    request = SimpleNamespace(app=client.app, headers={}, cookies=dict(client.cookies), is_disconnected=connected)
    with Session(client.app.state.engine) as db:
        actor = current_principal(request, db)
        stream = events(item.info['id'], request, actor, db)
    async def consume():
        body = stream.body_iterator
        first = await anext(body)
        assert 'id: 1\n' in first and '"status": "running"' in first
        if revoke:
            with Session(client.app.state.engine) as db, db.begin():
                db.execute(delete(project_memberships).where(project_memberships.c.user_id == 1))
        else:
            item.finish('completed')
        assert ': heartbeat' in await anext(body)
        following = await anext(body)
        if revoke:
            assert 'event: access-ended' in following
        else:
            assert 'id: 2\n' in following and 'run.finished' in following
            assert 'event: complete' in await anext(body)
        with pytest.raises(StopAsyncIteration):
            await anext(body)
    asyncio.run(consume())
