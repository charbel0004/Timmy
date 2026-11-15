export interface ExecutionRun {
  id: string; trace_id: string; actor_id: number; conversation_id: string | null;
  project_ids: number[]; operation: string; status: string; started_at: string; ended_at: string | null;
}
export interface ExecutionEvent {
  schema_version: number; event_id: string; run_id: string; trace_id: string;
  span_id: string; parent_span_id: string | null; event_type: string;
  sequence_number: number; timestamp: string; status: string;
  safe_payload: Record<string, string | number | boolean | null>;
}
export interface ExecutionDetail {
  run: ExecutionRun; events: ExecutionEvent[];
  usage: { invocation_count: number; input_tokens: number | null; output_tokens: number | null;
    total_tokens: number | null; tokens_per_second: number | null };
}
export interface SpanView {
  dependencies: string[]; id: string; parent: string | null; category: string; operation: string; status: string;
  started: string; ended?: string; duration?: number; payload: ExecutionEvent['safe_payload'];
}
// Sequence keyed merge makes replay and EventSource reconnection idempotent.
export function mergeEvents(previous: ExecutionEvent[], incoming: ExecutionEvent[]) {
  const map = new Map(previous.map((event) => [event.sequence_number, event]));
  incoming.forEach((event) => map.set(event.sequence_number, event));
  return [...map.values()].sort((a, b) => a.sequence_number - b.sequence_number);
}
export function executionSpans(events: ExecutionEvent[]): SpanView[] {
  const map = new Map<string, SpanView>();
  for (const event of events) {
    const p = event.safe_payload;
    if (event.event_type === 'span.started') map.set(event.span_id, {
      dependencies: [], id: event.span_id, parent: event.parent_span_id, category: String(p.category),
      operation: String(p.operation), status: event.status, started: event.timestamp, payload: { ...p },
    });
    else if (event.event_type === 'span.ended' || event.event_type === 'run.finished') {
      const item = map.get(event.span_id);
      if (item) Object.assign(item, { status: event.status, ended: event.timestamp,
        duration: p.duration_ms ?? Date.parse(event.timestamp) - Date.parse(item.started),
        payload: { ...item.payload, ...p } });
      if (event.event_type === 'run.finished') for (const child of map.values()) {
        if (child.id !== event.span_id && child.status === 'running') child.status = event.status === 'interrupted' ? 'interrupted' : 'unobserved';
      }
    } else if (event.event_type === 'policy.reference' || event.event_type === 'http.result') {
      map.set(event.span_id, { dependencies: [], id: event.span_id, parent: event.parent_span_id,
        category: String(p.category), operation: String(p.reference_id ?? p.operation),
        status: event.status, started: event.timestamp, ended: event.timestamp, payload: { ...p } });
    } else if (event.event_type === 'span.link') {
      const item = map.get(event.span_id);
      if (item && p.reference_id) item.dependencies.push(String(p.reference_id));
    } else if (event.event_type === 'model.usage' || event.event_type === 'model.config') {
      const item = map.get(event.span_id);
      if (item) item.payload = { ...item.payload, ...p };
    }
  }
  return [...map.values()];
}
export function usageFromEvents(events: ExecutionEvent[]) {
  const calls = events.filter((event) => event.event_type === 'model.usage');
  const invocations = Math.max(calls.length, events.filter(e => e.event_type === 'span.started' && e.safe_payload.category === 'model').length);
  const truncated = events.some(e => e.event_type === 'run.finished' && e.safe_payload.truncated);
  const sum = (key: string) => !truncated && calls.length && calls.length === invocations && calls.every((c) => typeof c.safe_payload[key] === 'number')
    ? calls.reduce((n, c) => n + Number(c.safe_payload[key]), 0) : null;
  const output = sum('eval_count'), duration = sum('eval_duration');
  return { invocation_count: invocations, input_tokens: sum('prompt_eval_count'), output_tokens: output,
    total_tokens: sum('total_tokens'), tokens_per_second: output !== null && duration ? output / (duration / 1e9) : null };
}

// Longest measured chain is calculated only from explicit runtime dependency
// links, never from model prose or hierarchical parent durations.
export function criticalPath(spans: SpanView[]) {
  const measured = new Map(spans.filter(s => s.duration !== undefined).map(s => [s.id, s]));
  const scores = new Map<string, { duration: number; path: string[] }>();
  function visit(id: string, visiting = new Set<string>()): { duration: number; path: string[] } {
    if (scores.has(id)) return scores.get(id)!;
    const span = measured.get(id);
    if (!span || visiting.has(id)) return { duration: 0, path: [] };
    const next = new Set(visiting); next.add(id);
    const previous = span.dependencies.map(dep => visit(dep, next)).sort((a, b) => b.duration - a.duration)[0];
    const result = { duration: (previous?.duration ?? 0) + span.duration!, path: [...(previous?.path ?? []), id] };
    scores.set(id, result); return result;
  }
  const candidates = spans.filter(s => s.dependencies.length).map(s => visit(s.id)).sort((a, b) => b.duration-a.duration);
  return new Set(candidates[0]?.path ?? []);
}
