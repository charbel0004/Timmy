"""Bounded, fail-open operational telemetry. Never capture prompts or row data."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
from functools import wraps
import inspect
import json
import logging
from time import monotonic
from urllib.parse import urlsplit
from uuid import uuid4
from threading import RLock, Lock
import math

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from .database import make_engine
from .auth import Authenticated, Database, current_principal
from .models import ExecutionRun, ExecutionEvent

log = logging.getLogger(__name__)
current = ContextVar('execution', default=None)
parent = ContextVar('execution_parent', default=None)
router = APIRouter(prefix='/api/executions')


def stamp():
    return datetime.now(timezone.utc).isoformat()


# Allowlisting is intentional: arbitrary values, exceptions, prompts and arguments
# never become telemetry. IDs, counters and trusted server operation names only.
FIELDS = {'category', 'operation', 'duration_ms', 'code', 'http_status', 'model',
          'prompt_eval_count', 'eval_count', 'prompt_eval_duration', 'eval_duration',
          'total_duration', 'load_duration', 'tokens_per_second', 'total_tokens',
          'instruction_set', 'version', 'stage', 'reference_id', 'schema', 'source',
          'backend_cpu_percent', 'backend_rss_bytes', 'host_cpu_percent',
          'host_used_bytes', 'host_total_bytes', 'host_memory_percent',
          'ollama_cpu_percent', 'ollama_rss_bytes', 'interval_seconds', 'gpu',
          'model_process_source', 'attribution', 'truncated', 'backend_pid', 'ollama_process_count'}


def safe(data):
    return {key: value[:240] if isinstance(value, str) else value
            for key, value in data.items() if key in FIELDS
            and (value is None or isinstance(value, (str, int, float, bool)))
            and (not isinstance(value, float) or math.isfinite(value))}


class Trace:
    def __init__(self, manager, actor_id, operation, project_ids=(), conversation_id=None, identifier=None):
        self.manager = manager
        self.info = dict(id=identifier or str(uuid4()), trace_id=uuid4().hex,
                         actor_id=actor_id, operation=operation, project_ids=list(project_ids),
                         conversation_id=conversation_id, status='running', started_at=stamp(), ended_at=None,
                         heartbeat_at=stamp(), access_grants={})
        self.lock = RLock()
        self.events = []
        self.root = uuid4().hex[:16]
        self.emit('span.started', self.root, None, 'running', category='request', operation=operation)

    def emit(self, *args, **kwargs):
        try:
            with self.lock:
                self._emit(*args, **kwargs)
        except Exception:
            log.debug('Telemetry event dropped', exc_info=False)

    def _emit(self, kind, span_id=None, parent_id=None, status='completed', **payload):
        # Reserve one terminal event even when the trace limit is reached.
        if len(self.events) >= self.manager.config.telemetry_max_events - 1 and kind != 'run.finished':
            return
        self.events.append(dict(schema_version=1, event_id=str(uuid4()), run_id=self.info['id'],
            trace_id=self.info['trace_id'], span_id=span_id or uuid4().hex[:16],
            parent_span_id=parent_id, event_type=kind, sequence_number=len(self.events)+1,
            timestamp=stamp(), status=status, safe_payload=safe(payload)))

    def snapshot(self):
        with self.lock:
            return self.info.copy(), list(self.events)

    def finish(self, status):
        with self.lock:
            self._finish(status)

    def _finish(self, status):
        if self.info["ended_at"] is not None:
            return
        self.info.update(status=status, ended_at=stamp())
        self.emit('run.finished', self.root, status=status,
                  truncated=len(self.events) >= self.manager.config.telemetry_max_events - 1)


@contextmanager
def span(operation, category='internal_tool', **metadata):
    trace = current.get()
    if trace is None:
        yield {}
        return
    identifier = uuid4().hex[:16]
    parent_id = parent.get() or trace.root
    trace.emit('span.started', identifier, parent_id, 'running', operation=operation, category=category, **metadata)
    token = parent.set(identifier)
    started = monotonic()
    result = {}
    try:
        yield result
    except BaseException as error:
        result['status'] = 'failed'
        result['code'] = getattr(error, 'code', 'OPERATION_FAILED')
        raise
    finally:
        parent.reset(token)
        status = result.pop('status', 'completed')
        trace.emit('span.ended', identifier, parent_id, status,
                   operation=operation, category=category,
                   duration_ms=round((monotonic()-started)*1000, 3), **metadata, **result)


def instrument(operation, category='internal_tool'):
    def decorate(function):
        if inspect.iscoroutinefunction(function):
            @wraps(function)
            async def async_call(*args, **kwargs):
                with span(operation, category):
                    return await function(*args, **kwargs)
            return async_call
        @wraps(function)
        def call(*args, **kwargs):
            with span(operation, category):
                return function(*args, **kwargs)
        return call
    return decorate


def reference(reference_id, stage, version=None, category="policy", status="completed"):
    trace = current.get()
    if trace:
        trace.emit('policy.reference', parent_id=parent.get() or trace.root, status=status,
                   category=category, operation='Instruction / policy reference',
                   reference_id=reference_id, stage=stage, version=version)


def model_usage(body, model):
    trace = current.get()
    if not trace:
        return
    values = {key: value if type(value := body.get(key)) is int and 0 <= value <= 2**63-1 else None
              for key in ('prompt_eval_count', 'eval_count', 'prompt_eval_duration',
                          'eval_duration', 'total_duration', 'load_duration')}
    prompt, output, duration = (values[k] for k in ('prompt_eval_count', 'eval_count', 'eval_duration'))
    values['total_tokens'] = prompt + output if prompt is not None and output is not None else None
    values['tokens_per_second'] = output / (duration / 1e9) if output is not None and duration else None
    trace.emit('model.usage', parent.get(), category='model', operation='Ollama usage', model=model, **values)


def aggregate(events):
    calls = [e['safe_payload'] for e in events if e['event_type'] == 'model.usage']
    invocations = max(len(calls), sum(e['event_type'] == 'span.started' and e['safe_payload'].get('category') == 'model' for e in events))
    truncated = any(e['event_type'] == 'run.finished' and e['safe_payload'].get('truncated') for e in events)
    def total(key):
        return sum(c[key] for c in calls) if not truncated and calls and len(calls) == invocations and all(c.get(key) is not None for c in calls) else None
    output, duration = total('eval_count'), total('eval_duration')
    return dict(invocation_count=invocations, reported_invocation_count=len(calls), input_tokens=total('prompt_eval_count'),
                output_tokens=output, total_tokens=total('total_tokens'),
                tokens_per_second=output/(duration/1e9) if output is not None and duration else None,
                model_duration_ns=total('total_duration'), load_duration_ns=total('load_duration'))


class Collector:
    def __init__(self, config):
        self.config = config
        self.api = None
        self.models = {}
        try:
            import psutil
            self.psutil = psutil
            self.api = psutil.Process()
            self.api.cpu_percent()
            psutil.cpu_percent()
        except Exception:
            self.psutil = None

    def sample(self):
        if self.psutil is None:
            return dict(source='unavailable', gpu='Unavailable')
        p = self.psutil
        result = dict(source='FastAPI host', interval_seconds=self.config.telemetry_sample_seconds,
                      gpu='Unavailable', model_process_source=self.config.telemetry_model_process_source,
                      ollama_cpu_percent=None, ollama_rss_bytes=None, attribution='Observed process/host usage; not exclusive to this request')
        try:
            memory = p.virtual_memory()
            result.update(backend_pid=self.api.pid, backend_cpu_percent=self.api.cpu_percent(),
                backend_rss_bytes=self.api.memory_info().rss, host_cpu_percent=p.cpu_percent(),
                host_used_bytes=memory.total-memory.available, host_total_bytes=memory.total,
                host_memory_percent=memory.percent)
            # Loopback origin is enforced by Settings. Names only; never inspect
            # process arguments, which can contain secrets.
            local = urlsplit(self.config.ollama_url).hostname in {'localhost', '127.0.0.1', '::1'}
            found = {}
            if local and self.config.telemetry_model_process_source == 'local':
                for proc in p.process_iter(['pid', 'name']):
                    if 'ollama' in (proc.info['name'] or '').lower():
                        found[proc.pid] = self.models.get(proc.pid, proc)
                rss, cpu = 0, 0.0
                for proc in found.values():
                    rss += proc.memory_info().rss
                    measured = proc.cpu_percent()
                    if proc.pid in self.models:
                        cpu += measured
                result.update(ollama_rss_bytes=rss if found else None,
                    ollama_cpu_percent=cpu if found and all(pid in self.models for pid in found) else None,
                    ollama_process_count=len(found))
            self.models = found
        except (p.Error, OSError):
            result.update(ollama_rss_bytes=None, ollama_cpu_percent=None)
        return result


class Telemetry:
    def __init__(self, engine, config):
        # Dedicated pool for telemetry: its short SQLite lock timeout must never
        # leak onto a pooled connection used by business transactions.
        self.engine = make_engine(engine.url) if engine is not None else None
        self.config = config
        self.active = {}
        self.lock = RLock()
        self.flush_lock = Lock()
        self.collector = Collector(config)
        self.task = None

    def items(self):
        with self.lock:
            return list(self.active.items())

    def start(self, *args, **kwargs):
        with self.lock:
            if not self.config.telemetry_enabled or len(self.active) >= 64:
                return None
            trace = Trace(self, *args, **kwargs)
            self.active[trace.info['id']] = trace
            return trace

    @contextmanager
    def execution(self, actor_id, operation, project_ids, access_grants):
        trace = self.start(actor_id, operation, project_ids)
        if trace:
            trace.info['access_grants'] = access_grants
        token = current.set(trace)
        parent_token = parent.set(trace.root if trace else None)
        try:
            yield trace
        except BaseException:
            if trace:
                trace.finish('failed')
            raise
        else:
            if trace:
                trace.finish('completed')
        finally:
            parent.reset(parent_token)
            current.reset(token)

    def recover_stale(self, db):
        cutoff = (datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
        rows = db.scalars(select(ExecutionRun).where(ExecutionRun.status == 'running', ExecutionRun.heartbeat_at < cutoff))
        for row in rows:
            if row.id in self.active:
                continue
            row.status, row.ended_at = 'interrupted', stamp()
            entries = list(db.scalars(select(ExecutionEvent.payload).where(ExecutionEvent.run_id == row.id).order_by(ExecutionEvent.sequence_number)))
            root = entries[0]['span_id'] if entries else uuid4().hex[:16]
            event = dict(schema_version=1, event_id=str(uuid4()), run_id=row.id, trace_id=row.trace_id,
                span_id=root, parent_span_id=None, event_type='run.finished', sequence_number=len(entries)+1,
                timestamp=row.ended_at, status='interrupted', safe_payload={'code': 'COLLECTOR_LEASE_EXPIRED'})
            db.add(ExecutionEvent(event_id=event['event_id'], run_id=row.id, sequence_number=event['sequence_number'], payload=event))

    def flush(self):
        if not self.flush_lock.acquire(blocking=False):
            return
        try:
            self._flush()
        finally:
            self.flush_lock.release()

    def _flush(self):
        # This connection never shares the business session. A locked database
        # defers telemetry instead of waiting on, or changing, a financial write.
        try:
            with self.engine.connect() as connection:
                connection.exec_driver_sql('PRAGMA busy_timeout=20')
                connection.commit()
                with Session(bind=connection) as db:
                    persisted = []
                    for identifier, trace in self.items():
                        info, events = trace.snapshot()
                        stored = db.get(ExecutionRun, identifier)
                        if stored is None:
                            stored = ExecutionRun(**info)
                            db.add(stored)
                            db.flush()
                        stored.heartbeat_at = stamp()
                        stored.access_grants = info['access_grants']
                        stored.status = info['status']
                        stored.ended_at = info['ended_at']
                        last = db.scalar(select(ExecutionEvent.sequence_number).where(
                            ExecutionEvent.run_id == identifier).order_by(ExecutionEvent.sequence_number.desc()).limit(1)) or 0
                        for event in events[last:]:
                            db.add(ExecutionEvent(event_id=event['event_id'], run_id=identifier,
                                sequence_number=event['sequence_number'], payload=event))
                        persisted.append((identifier, len(events), info['status']))
                    self.recover_stale(db)
                    db.commit()
            for identifier, count, status in persisted:
                with self.lock:
                    trace = self.active.get(identifier)
                    if trace:
                        with trace.lock:
                            if status != 'running' and len(trace.events) == count and trace.info['status'] == status:
                                self.active.pop(identifier, None)
        except Exception:
            log.debug('Telemetry persistence deferred', exc_info=False)

    async def loop(self):
        last_retention = 0
        while True:
            try:
                if any(t.info['status'] == 'running' for _, t in self.items()):
                    sample = self.collector.sample()
                    for _, trace in self.items():
                        if trace.info['status'] == 'running':
                            trace.emit('resource.sample', parent_id=trace.root, category='resource', **sample)
                self.flush()
                if monotonic() - last_retention > 3600:
                    cutoff = (datetime.now(timezone.utc)-timedelta(days=self.config.telemetry_retention_days)).isoformat()
                    with self.engine.connect() as connection:
                        connection.exec_driver_sql('PRAGMA busy_timeout=20')
                        connection.commit()
                        with Session(bind=connection) as db, db.begin():
                            db.execute(delete(ExecutionRun).where(ExecutionRun.started_at < cutoff, ExecutionRun.status != 'running'))
                    last_retention = monotonic()
            except Exception:
                log.debug('Telemetry collection unavailable', exc_info=False)
            await asyncio.sleep(self.config.telemetry_sample_seconds)


def permitted(info, principal):
    principal.require('projects:read')
    if info['actor_id'] != principal.user.id:
        return False
    for project in info['project_ids']:
        if 'projects:read' not in principal.project_permissions.get(project, []):
            return False
    for project, grants in info.get('access_grants', {}).items():
        if not set(grants).issubset(principal.project_permissions.get(int(project), [])):
            return False
    return True


def run_info(row):
    return {key: getattr(row, key) for key in ('id', 'trace_id', 'actor_id', 'conversation_id',
            'project_ids', 'operation', 'status', 'started_at', 'ended_at', 'heartbeat_at', 'access_grants')}


def get_run(request, db, principal, identifier):
    trace = request.app.state.telemetry.active.get(identifier)
    row = db.get(ExecutionRun, identifier) if not trace else None
    info, live_events = trace.snapshot() if trace else (run_info(row), None) if row else (None, None)
    if info is None or not permitted(info, principal):
        raise HTTPException(404, 'Execution unavailable')
    events = live_events if trace else list(db.scalars(select(ExecutionEvent.payload).where(
        ExecutionEvent.run_id == identifier).order_by(ExecutionEvent.sequence_number)))
    return dict(run=info, events=events, usage=aggregate(events))


@router.get('')
def runs(request: Request, principal: Authenticated, db: Database, conversation_id: str | None = None):
    principal.require('projects:read')
    rows = db.scalars(select(ExecutionRun).where(ExecutionRun.actor_id == principal.user.id)
                      .order_by(ExecutionRun.started_at.desc()).limit(100))
    values = {row.id: run_info(row) for row in rows}
    values.update({key: t.info.copy() for key, t in request.app.state.telemetry.items()})
    return sorted([v for v in values.values() if permitted(v, principal)
                   and (conversation_id is None or v['conversation_id'] == conversation_id)],
                  key=lambda v: v['started_at'], reverse=True)[:100]


@router.get('/instructions')
def instructions(principal: Authenticated):
    principal.require('settings:read')
    from .instruction_pack import DIGEST
    return {'instruction_set': 'approved-action-pack', 'version': DIGEST,
            'configuration_version': 'execution-schema-1', 'prompt_text': 'Not exposed'}


@router.get('/{identifier}')
def detail(identifier: str, request: Request, principal: Authenticated, db: Database):
    return get_run(request, db, principal, identifier)


@router.get('/{identifier}/events')
def events(identifier: str, request: Request, principal: Authenticated, db: Database, after: int = 0):
    get_run(request, db, principal, identifier)
    try:
        cursor = max(0, after, int(request.headers.get('last-event-id', '0')))
    except ValueError:
        raise HTTPException(422, 'Invalid event cursor') from None
    async def stream():
        nonlocal cursor
        # One bounded batch per second; persistently replayable, no subscriber queue.
        # Reauthenticate every batch in a fresh session, including revoked grants.
        while not await request.is_disconnected():
            with Session(request.app.state.engine) as session:
                try:
                    actor = current_principal(request, session)
                    result = get_run(request, session, actor, identifier)
                except HTTPException:
                    yield 'event: access-ended\ndata: {}\n\n'
                    return
            batch = [e for e in result['events'] if e['sequence_number'] > cursor][:100]
            for event in batch:
                cursor = event['sequence_number']
                yield f'id: {cursor}\nevent: execution\ndata: {json.dumps(event)}\n\n'
            if result['run']['status'] != 'running' and (not batch or cursor >= result['events'][-1]['sequence_number']):
                yield 'event: complete\ndata: {}\n\n'
                return
            yield ': heartbeat\n\n'
            await asyncio.sleep(1)
    db.rollback()  # Do not retain a read transaction for the stream lifetime.
    return StreamingResponse(stream(), media_type='text/event-stream',
                             headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-store'})


# Registered before dynamic /{identifier} by main's separate /api/overview route.
def overview_data(principal, db):
    from sqlalchemy import func
    from .models import projects, activities, MappingProposal, StructuralValidation, WorkflowRun, Conversation
    from .documents import scoped_documents
    principal.require('projects:read')
    scopes = [pid for pid, grants in principal.project_permissions.items() if 'projects:read' in grants]
    timesheet_scopes = [pid for pid, grants in principal.project_permissions.items() if 'timesheets.view' in grants]
    activity_scopes = [pid for pid, grants in principal.project_permissions.items() if 'activities.view' in grants]
    today = datetime.now(timezone.utc).date().isoformat()
    active = db.scalar(select(func.count()).select_from(projects).where(projects.c.id.in_(scopes), projects.c.status == 'active'))
    current_activities = db.scalar(select(func.count()).select_from(activities).where(activities.c.project_id.in_(activity_scopes),
        activities.c.planned_start <= today, activities.c.planned_end >= today))
    review = db.scalar(select(func.count()).select_from(MappingProposal).where(MappingProposal.actor_id == principal.user.id,
        MappingProposal.project_id.in_(timesheet_scopes), MappingProposal.status == 'proposed'))
    stored = db.scalar(select(func.count()).select_from(scoped_documents(db, principal).subquery()))
    validated = db.scalar(select(func.count()).select_from(StructuralValidation).where(StructuralValidation.project_id.in_(timesheet_scopes), StructuralValidation.actor_id == principal.user.id))
    days = [(datetime.now(timezone.utc)-timedelta(days=offset)).date().isoformat() for offset in range(6, -1, -1)]
    grouped_day = func.date(WorkflowRun.created_at, 'unixepoch')
    outcomes = db.execute(select(grouped_day, WorkflowRun.status, func.count()).where(
        WorkflowRun.actor_id == principal.user.id, WorkflowRun.project_id.in_(timesheet_scopes),
        grouped_day >= days[0]).group_by(grouped_day, WorkflowRun.status)).all()
    trend = {day: {'day': day, 'completed': 0, 'needs_review': 0, 'blocked': 0, 'failed': 0} for day in days}
    for day, status, count in outcomes:
        if day in trend and status in {'completed', 'needs_review', 'blocked', 'failed'}:
            trend[day][status] = count
    pending = db.execute(select(MappingProposal.conversation_id, MappingProposal.created_at, Conversation.title).join(
        Conversation, Conversation.id == MappingProposal.conversation_id).where(
            MappingProposal.actor_id == principal.user.id, Conversation.owner_id == principal.user.id,
            MappingProposal.project_id.in_(timesheet_scopes), MappingProposal.status == 'proposed'
        ).order_by(MappingProposal.created_at.desc()).limit(20)).all()
    return dict(workflow_trend=list(trend.values()), pending_reviews=[{'conversation_id': row.conversation_id,
                'created_at': row.created_at, 'title': row.title} for row in pending], active_projects=active, current_activities=current_activities, mapping_reviews=review,
                documents=stored, structural_validations=validated,
                payment_ready=None, outstanding_obligations=None,
                limitations='Payment entitlement and settlement summary adapters are unavailable. Current activities require both planned dates.')
