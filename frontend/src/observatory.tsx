import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ArrowUpRight, CheckCircle2, ChevronRight, Clock3, Cpu, GitBranch, Search, X } from 'lucide-react';
import { motion } from 'motion/react';
import { apiBase, errorMessage, request } from './api';
import { executionSpans, mergeEvents, usageFromEvents } from './execution-model';
import type { ExecutionDetail, ExecutionEvent, ExecutionRun, SpanView } from './execution-model';
const ExecutionGraph = lazy(() => import('./execution-graph'));

const numeric = (value: unknown, suffix = '') => typeof value === 'number' ? `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}` : 'Unavailable';
const bytes = (value: unknown) => typeof value === 'number' ? numeric(value / 1048576, ' MB') : 'Unavailable';
const date = (value: string) => new Date(value).toLocaleString();

export function useRuns(conversation?: string, refresh = false) {
  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const pending = useRef<AbortController | undefined>(undefined);
  const reload = useCallback(async () => {
    pending.current?.abort();
    const controller = new AbortController(); pending.current = controller;
    try {
      const items = await request<ExecutionRun[]>(`/executions${conversation ? `?conversation_id=${conversation}` : ''}`, { signal: controller.signal });
      if (!controller.signal.aborted) { setRuns(items); setError(''); }
    } catch (e) { if (!controller.signal.aborted) setError(errorMessage(e)); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }, [conversation]);
  useEffect(() => {
    setRuns([]); setLoading(true); void reload();
    const timer = refresh ? setInterval(reload, 4000) : undefined;
    return () => { clearInterval(timer); pending.current?.abort(); };
  }, [reload, refresh]);
  return { runs, error, loading, reload };
}

export function useExecution(id?: string) {
  const [detail, setDetail] = useState<ExecutionDetail>();
  const [error, setError] = useState('');
  const [connection, setConnection] = useState('Stored history');
  useEffect(() => {
    setDetail(undefined); setError('');
    if (!id) return;
    let active = true, source: EventSource | undefined;
    request<ExecutionDetail>(`/executions/${id}`).then((value) => {
      if (!active) return;
      setDetail(value);
      if (value.run.status !== 'running') { setConnection('Stored history'); return; }
      setConnection('Connecting');
      const last = value.events.at(-1)?.sequence_number ?? 0;
      source = new EventSource(`${apiBase}/executions/${id}/events?after=${last}`, { withCredentials: true });
      source.onopen = () => setConnection('Live events');
      source.onerror = () => setConnection('Reconnecting');
      source.addEventListener('execution', (message) => {
        const event = JSON.parse((message as MessageEvent).data) as ExecutionEvent;
        setDetail((previous) => {
          if (!previous) return previous;
          const events = mergeEvents(previous.events, [event]);
          return { ...previous, events, usage: usageFromEvents(events), run: event.event_type === 'run.finished'
            ? { ...previous.run, status: event.status, ended_at: event.timestamp } : previous.run };
        });
      });
      source.addEventListener('complete', () => { setConnection('Stored history'); source?.close(); });
      source.addEventListener('access-ended', () => { setDetail(undefined); setError('Execution access ended.'); source?.close(); });
    }).catch((e) => { if (active) setError(errorMessage(e)); });
    return () => { active = false; source?.close(); };
  }, [id]);
  return { detail, error, connection };
}

export function ExecutionTimeline({ conversation, busy }: { conversation?: string; busy: boolean }) {
  const { runs, error } = useRuns(conversation, busy);
  const { detail, connection } = useExecution(runs[0]?.id);
  const spans = useMemo(() => executionSpans(detail?.events ?? []), [detail?.events]);
  if (!conversation) return null;
  return <details className="execution-timeline" open={busy || undefined}>
    <summary><Activity size={15} /> Execution activity <span>{detail ? connection : 'No execution selected'}</span></summary>
    {error && <p role="alert">{error}</p>}
    {detail ? <><ol>{spans.slice(-18).map((item) => <motion.li key={item.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <span className={`state-mark state-${item.status}`} aria-hidden="true" />
      <div><strong>{item.operation}</strong><small>{item.category} · {item.status}{item.duration !== undefined && ` · ${numeric(item.duration, ' ms')}`}</small></div>
    </motion.li>)}</ol><a href={`#observatory/${detail.run.id}`}>Inspect full execution <ArrowUpRight size={14} /></a></>
      : <p className="empty-state">Execution events appear when a request reaches the API.</p>}
  </details>;
}

function Inspector({ selected, detail, onClose }: { selected: SpanView; detail: ExecutionDetail; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  const children = executionSpans(detail.events).filter((s) => s.parent === selected.id);
  return <dialog ref={dialog} className="execution-inspector" onClose={onClose} onClick={(e) => { if (e.target === e.currentTarget) dialog.current?.close(); }}>
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <header><span className="eyebrow">Operation inspector</span><button className="secondary" autoFocus aria-label="Close inspector" onClick={onClose}><X size={16} /></button></header>
      <h2>{selected.operation}</h2><p className={`execution-status state-${selected.status}`}>{selected.status}</p>
      <dl className="inspector-fields">
        <div><dt>Category</dt><dd>{selected.category}</dd></div>
        <div><dt>Started</dt><dd>{date(selected.started)}</dd></div>
        <div><dt>Ended</dt><dd>{selected.ended ? date(selected.ended) : selected.status === 'running' ? 'In progress' : 'End not observed'}</dd></div>
        <div><dt>Duration</dt><dd>{numeric(selected.duration, ' ms')}</dd></div>
        <div><dt>Trace ID</dt><dd>{detail.run.trace_id}</dd></div>
        <div><dt>Run ID</dt><dd>{detail.run.id}</dd></div>
        <div><dt>Span ID</dt><dd>{selected.id}</dd></div>
        <div><dt>Parent span</dt><dd>{selected.parent ?? 'Root request'}</dd></div>
        <div><dt>Conversation</dt><dd>{detail.run.conversation_id ?? 'Outside conversation'}</dd></div>
        <div><dt>Access scope</dt><dd>{detail.run.project_ids.join(', ') || 'No project context'}</dd></div>
        <div><dt>Dependencies</dt><dd>{selected.dependencies.join(", ") || "No explicit dependency links"}</dd></div>
        <div><dt>Child operations</dt><dd>{children.map((c) => c.operation).join(', ') || 'None'}</dd></div>
      </dl><h3>Safe operation metadata</h3>
      <dl className="inspector-fields">{Object.entries(selected.payload).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{value === null ? 'Unavailable' : String(value)}</dd></div>)}</dl>
      <p className="muted">Raw arguments, confidential prompts, document values and hidden model reasoning are excluded. Resource samples describe observed process usage.</p>
    </motion.div>
  </dialog>;
}

function Gauge({ label, value, note }: { label: string; value: unknown; note: string }) {
  return <article className="resource-gauge"><header><Cpu size={15} /><span>{label}</span></header>
    <strong>{numeric(value, '%')}</strong><meter min="0" max="100" value={typeof value === 'number' ? Math.min(value, 100) : 0} aria-label={label} />
    <small>{note}</small></article>;
}

function ResourceChart({ events }: { events: ExecutionEvent[] }) {
  const samples = events.filter((e) => e.event_type === 'resource.sample' && typeof e.safe_payload.host_cpu_percent === 'number');
  const lines = ['host_cpu_percent', 'host_memory_percent'];
  return <section className="resource-chart"><header><h3>Host utilization over time</h3><span>CPU / Memory · %</span></header>
    {samples.length > 1 ? <><svg viewBox="0 0 800 130" role="img" aria-label={`Actual host CPU and RAM history, ${samples.length} samples`} preserveAspectRatio="none">
      {[25, 50, 75, 100].map((v) => <line key={v} x1="0" x2="800" y1={130-v*1.2} y2={130-v*1.2} className="chart-grid" />)}
      {lines.map((key, index) => <polyline key={key} fill="none" stroke={index ? '#a78bfa' : '#38bdf8'} strokeWidth="2" points={samples.map((e, i) => `${i/(samples.length-1)*800},${130-Number(e.safe_payload[key])*1.2}`).join(' ')} />)}
    </svg><footer><time>{new Date(samples[0].timestamp).toLocaleTimeString()}</time><span>Blue CPU · Violet RAM</span><time>{new Date(samples.at(-1)!.timestamp).toLocaleTimeString()}</time></footer></>
      : <p className="empty-state">{samples.length ? 'One sample recorded. A trend requires at least two.' : 'No resource samples for this execution.'}</p>}
  </section>;
}

export function Observatory() {
  const { runs, error, loading, reload } = useRuns(undefined, true);
  const [hashPath, hashQuery] = window.location.hash.split('?');
  const target = hashPath.split('/')[1];
  const [runStatus, setRunStatus] = useState(new URLSearchParams(hashQuery || '').get('status') || 'all');
  const listedRuns = runs.filter(run => runStatus === 'all' || run.status === runStatus);
  const [id, setId] = useState<string | undefined>(target);
  const [filter, setFilter] = useState('');
  const [category, setCategory] = useState('all');
  const [status, setStatus] = useState('all');
  const [selectedId, setSelectedId] = useState<string>();
  const [cursor, setCursor] = useState<number | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  useEffect(() => { if (target) setId(target); }, [target]);
  const { detail, error: detailError, connection } = useExecution(id || listedRuns[0]?.id);
  useEffect(() => { setCursor(null); setCollapsed(new Set()); setSelectedId(undefined); }, [detail?.run.id]);
  const shownEvents = useMemo(() => cursor === null ? detail?.events ?? [] : detail?.events.slice(0, cursor) ?? [], [detail?.events, cursor]);
  const spans = useMemo(() => executionSpans(shownEvents), [shownEvents]);
  const usage = useMemo(() => usageFromEvents(shownEvents), [shownEvents]);
  const filtered = useMemo(() => {
    const lookup = new Map(spans.map((s) => [s.id, s]));
    return spans.filter((s) => {
      let ancestor = s.parent;
      while (ancestor) { if (collapsed.has(ancestor)) return false; ancestor = lookup.get(ancestor)?.parent ?? null; }
      return s.operation.toLowerCase().includes(filter.toLowerCase()) && (category === 'all' || s.category === category) && (status === 'all' || s.status === status);
    });
  }, [spans, collapsed, filter, category, status]);
  const sample = shownEvents.filter((e) => e.event_type === 'resource.sample').at(-1)?.safe_payload;
  const selected = spans.find((s) => s.id === selectedId);
  const tools = spans.filter((s) => s.category === 'internal_tool' || s.category === 'mcp');
  return <div className="observatory">
    <header className="command-heading"><div><span className="eyebrow">Intelligence / Observability</span><h1>Execution Observatory</h1><p>Every operation. Every gate. Observable evidence.</p></div>
      <button className="secondary" onClick={reload}><Activity size={15} /> Refresh history</button></header>
    {(error || detailError) && <p role="alert">{error || detailError}</p>}
    <section className="observatory-controls glass-panel"><label>Execution<select value={id || listedRuns[0]?.id || ''} onChange={(e) => { setId(e.target.value); window.history.replaceState(null, '', `#observatory/${e.target.value}`); }}>
      {!listedRuns.length && <option value="">{loading ? 'Loading executions…' : 'No recorded executions'}</option>}
      {listedRuns.map((r) => <option key={r.id} value={r.id}>{date(r.started_at)} · {r.operation} · {r.status}</option>)}</select></label>
      <select aria-label="Filter execution status" value={runStatus} onChange={(event) => { setRunStatus(event.target.value); setId(undefined); }}><option value="all">All executions</option>{['failed', 'running', 'completed', 'interrupted'].map(value => <option key={value}>{value}</option>)}</select>
      <span className={`connection-label ${detail?.run.status === 'running' ? 'is-live' : ''}`}><span className="status-dot" />{connection}</span>
      <span className="trace-id">{detail?.run.trace_id ?? 'No trace selected'}</span></section>
    {!detail ? <section className="glass-panel empty-observatory"><GitBranch size={35} /><h2>Your execution history starts here</h2><p>Send a message or process an upload. Real backend operations will appear here.</p><a className="hero-action" href="#assistant">Open AI Workspace <ChevronRight size={16} /></a></section> : <>
      {detail.events.some(e => e.event_type === "run.finished" && e.safe_payload.truncated) && <p role="status" className="trace-truncation">This trace reached its event limit. Later operations are missing and aggregate token usage is unavailable.</p>}
      <section className="execution-metrics" aria-label="Execution measurements">
        {[
          ['Input tokens', numeric(usage.input_tokens), 'Reported by Ollama'], ['Total tokens', numeric(usage.total_tokens), 'Input + output, when both reported'], ['Output tokens', numeric(usage.output_tokens), `${usage.invocation_count} observed invocations`],
          ['Tokens / second', numeric(usage.tokens_per_second), 'Output / generation time'],
          ['Execution duration', detail.run.ended_at ? numeric(Date.parse(detail.run.ended_at)-Date.parse(detail.run.started_at), ' ms') : 'In progress', detail.run.status],
          ['Active model', String([...shownEvents].reverse().find(e => e.safe_payload.model)?.safe_payload.model ?? 'Unavailable'), 'From the actual invocation'],
          ['Tool calls', String(tools.length), `${tools.filter((s) => s.status === 'failed').length} failed`],
        ].map(([label, value, note]) => <article className="glass-panel" key={label}><span>{label}</span><strong data-mono>{value}</strong><small>{note}</small></article>)}
      </section>
      <section className="execution-canvas glass-panel" aria-label="Execution dependency graph">
        <header className="graph-toolbar"><label className="graph-search"><Search size={15} /><input aria-label="Search operations" placeholder="Find an operation…" value={filter} onChange={(e) => setFilter(e.target.value)} /></label>
          <select aria-label="Filter category" value={category} onChange={(e) => setCategory(e.target.value)}><option value="all">All categories</option>{[...new Set(spans.map((s) => s.category))].map((v) => <option key={v}>{v}</option>)}</select>
          <select aria-label="Filter status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">All statuses</option>{['running', 'completed', 'failed', 'blocked', 'needs_review'].map((v) => <option key={v}>{v}</option>)}</select>
        </header>
        <Suspense fallback={<div className="flow-viewport skeleton" role="status">Loading execution graph…</div>}><ExecutionGraph runId={detail.run.id} spans={spans} filtered={filtered} onSelect={setSelectedId} onCollapse={(id) => setCollapsed((old) => { const next = new Set(old); next.has(id) ? next.delete(id) : next.add(id); return next; })} /></Suspense>
        <footer className="graph-caption"><span><GitBranch size={14} /> Dashed: parent · Solid: dependency · Blue: longest measured dependency path · Outline: longest operation</span><span>{filtered.length} operations</span></footer>
      </section>
      <div className="replay-bar glass-panel"><Clock3 size={17} /><label>Replay stored events<input type="range" min="1" max={Math.max(1, detail.events.length)} value={cursor ?? detail.events.length} onChange={(e) => setCursor(Number(e.target.value))} /></label><span>{cursor ?? detail.events.length} / {detail.events.length}</span><button className="secondary" onClick={() => setCursor(null)}>Latest</button></div>
      <section className="glass-panel provenance-panel"><h2>Instruction &amp; policy provenance</h2><p className="muted">Stages record application evidence. They do not establish what the model internally read or considered.</p><div className="provenance-stages">{['available', 'retrieved', 'supplied', 'cited', 'executed'].map((stage) => <div key={stage}><strong>{shownEvents.filter((e) => e.event_type === 'policy.reference' && e.safe_payload.stage === stage).length}</strong><span>{stage === 'cited' ? 'Explicit citations reported' : stage}</span></div>)}</div><p className="muted">The current structured response schema does not report document citations. Retrieved documents are not automatically supplied to the model. Select a policy or context node to inspect its identifier and version.</p></section>
      <div className="observatory-bottom"><section className="glass-panel resources"><header><h2>Resource telemetry</h2><span>Observed on FastAPI host</span></header>
        <div className="resource-grid"><Gauge label="Host CPU" value={sample?.host_cpu_percent} note={`Sample interval ${sample?.interval_seconds ?? 'unavailable'} s`} />
          <Gauge label="Host RAM" value={sample?.host_memory_percent} note={`${bytes(sample?.host_used_bytes)} / ${bytes(sample?.host_total_bytes)}`} />
          <article className="resource-gauge"><header>FastAPI process</header><strong>{numeric(sample?.backend_cpu_percent, '% CPU')}</strong><small>{bytes(sample?.backend_rss_bytes)} RSS · process CPU may exceed 100%</small></article>
          <article className="resource-gauge"><header>Ollama process telemetry</header><strong>{bytes(sample?.ollama_rss_bytes)}</strong><small>{numeric(sample?.ollama_cpu_percent, '% CPU')} · source: {sample?.model_process_source ?? 'unavailable'} · GPU unavailable</small></article></div>
        <ResourceChart events={shownEvents} /><p className="muted">Host and process measurements are shared utilization, not resources consumed solely by this request. Counts appear only when reported; no token estimates.</p></section>
        <section className="glass-panel trace-ledger"><h2>Operation ledger</h2><p className="muted">Select to inspect. Expand/collapse child operations here or double-click a graph node.</p>
          <ol>{filtered.map((s) => <li key={s.id}><button className="ledger-inspect" onClick={() => setSelectedId(s.id)}><span className={`state-mark state-${s.status}`} /><span>{s.operation}<small>{s.status} · {s.category}</small></span><ArrowUpRight size={14} /></button>
            {spans.some((child) => child.parent === s.id) && <button className="secondary" aria-expanded={!collapsed.has(s.id)} onClick={() => setCollapsed((old) => { const next = new Set(old); next.has(s.id) ? next.delete(s.id) : next.add(s.id); return next; })}>{collapsed.has(s.id) ? 'Expand' : 'Collapse'}</button>}</li>)}</ol>
        </section></div>
      {selected && <Inspector selected={selected} detail={detail} onClose={() => setSelectedId(undefined)} />}
    </>}
  </div>;
}

export function ExecutionSummary() {
  const { runs, error, loading } = useRuns();
  const days = Array.from({ length: 7 }, (_, i) => { const d = new Date(); d.setDate(d.getDate() - 6 + i); return d.toISOString().slice(0, 10); });
  return <section className="glass-panel execution-summary"><header><div><span className="eyebrow">Application activity</span><h2>Recent executions</h2></div><a href="#observatory">Open Observatory <ArrowUpRight size={14} /></a></header>
    {error && <p role="alert">{error}</p>}{loading ? <div className="skeleton" role="status">Loading execution history…</div> : <>
      <a className="failed-executions" href="#observatory?status=failed"><span className="state-mark state-failed" /> {runs.filter(run => run.status === 'failed').length} failed operations in recent history · Inspect →</a>
      <div className="execution-trend" aria-label="Completed executions in recent history by day">{days.map((day) => { const count = runs.filter((r) => r.started_at.startsWith(day) && r.status === 'completed').length; return <div key={day}><span>{count}</span><meter min="0" max={Math.max(1, runs.length)} value={count} aria-label={`${day}: ${count} completed`} /><small>{day.slice(5)}</small></div>; })}</div>
      <p className="muted">Completion trend within your latest 100 recorded API executions; not financial workflow completion.</p>
      {runs.slice(0, 5).map((run) => <a className="recent-run" href={`#observatory/${run.id}`} key={run.id}><CheckCircle2 size={16} /><strong>{run.operation}</strong><span className={`execution-status state-${run.status}`}>{run.status}</span><time>{date(run.started_at)}</time><ArrowUpRight size={14} /></a>)}
      {!runs.length && <p className="empty-state">No execution history yet. Start in AI Workspace.</p>}</>}
  </section>;
}
