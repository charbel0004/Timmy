import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { executionSpans, mergeEvents, usageFromEvents } from '../src/execution-model.ts';
const event = (sequence, kind, payload = {}, rest = {}) => ({ sequence_number: sequence, event_type: kind,
  event_id: `e${sequence}`, run_id: 'run', trace_id: 'trace', span_id: 'model', parent_span_id: 'root',
  timestamp: `2026-11-15T10:00:0${sequence}Z`, status: 'completed', safe_payload: payload, ...rest });
test('reconnect and refresh merge by ordered sequence without double counting', () => {
  const usage = event(2, 'model.usage', { prompt_eval_count: 3, eval_count: 2, total_tokens: 5, eval_duration: 1e9 });
  const events = mergeEvents([usage], [event(1, 'span.started', { category: 'model', operation: 'ollama.chat' }, { status: 'running' }), usage]);
  assert.deepEqual(events.map(e => e.sequence_number), [1, 2]);
  assert.equal(usageFromEvents(events).total_tokens, 5);
  assert.equal(usageFromEvents(events).tokens_per_second, 2);
});
test('stored events restore graph and replay never completes a future operation', () => {
  const events = [event(1, 'span.started', { operation: 'ollama.chat', category: 'model' }, { status: 'running' }),
    event(2, 'span.ended', { duration_ms: 120 }, { status: 'failed' })];
  assert.equal(executionSpans(events.slice(0, 1))[0].status, 'running');
  const spans = executionSpans(JSON.parse(JSON.stringify(events)));
  assert.equal(spans[0].status, 'failed'); assert.equal(spans[0].duration, 120);
  assert.equal(spans[0].parent, 'root');
});
test('missing metadata and mixed measured/unmeasured calls remain unavailable', () => {
  assert.equal(usageFromEvents([]).input_tokens, null);
  assert.equal(usageFromEvents([event(1, 'model.usage', { total_tokens: 5 }), event(2, 'run.finished', { truncated: true })]).total_tokens, null);
  assert.equal(usageFromEvents([event(1, 'model.usage', { eval_count: 2 }), event(2, 'model.usage', {})]).output_tokens, null);
});
test('large traces and policy stages preserve authoritative topology', () => {
  const events = Array.from({ length: 2000 }, (_, i) => event(i + 1, 'policy.reference', { reference_id: `doc-${i}`, category: 'policy', stage: 'retrieved' }, { span_id: `s${i}` }));
  const spans = executionSpans(events);
  assert.equal(spans.length, 2000); assert.ok(spans.every(s => s.parent === 'root'));
});
test('terminal interrupted runs stop active path animation without invented timings', () => {
  const events = [event(1, 'span.started', { operation: 'request', category: 'request' }, { span_id: 'root', parent_span_id: null, status: 'running' }),
    event(2, 'span.started', { operation: 'ollama.chat', category: 'model' }, { status: 'running' }),
    event(3, 'run.finished', {}, { span_id: 'root', parent_span_id: null, status: 'interrupted' })];
  const model = executionSpans(events).find(s => s.id === 'model');
  assert.equal(model.status, 'interrupted'); assert.equal(model.duration, undefined);
});
test('critical path uses explicit dependencies instead of parent duration', async () => {
  const { criticalPath } = await import('../src/execution-model.ts');
  const base = { dependencies: [], parent: 'root', category: 'validation', operation: 'check', status: 'completed', started: '', payload: {} };
  const spans = [{ ...base, id: 'a', duration: 10 }, { ...base, id: 'b', duration: 20, dependencies: ['a'] }, { ...base, id: 'root', duration: 9999 }];
  assert.deepEqual([...criticalPath(spans)], ['a', 'b']);
});
