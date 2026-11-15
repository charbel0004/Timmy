# Execution Observatory implementation

## Changes and file map

| Area | Files | Behavior |
|---|---|---|
| Persistence/config | `backend/timmy/models.py`, `backend/migrations/versions/0019_execution_observability.py`, `backend/timmy/config.py`, `.env.example` | Additive execution runs and ordered JSON events; bounded collection and retention |
| Collection/API | `backend/timmy/observability.py`, `main.py`, `routes.py` | Actor-private run history, live SSE, replay, permission rechecks, health readiness, host/API/Ollama samples |
| Runtime boundaries | `ai.py`, `chat.py`, `chat_routes.py`, `documents.py`, `conversation_workflow.py`, `workflows.py`, `workflow_graph.py`, `workflow_scheduler.py`, `session_preview.py`, `instruction_pack.py` | Actual model, retrieval, upload, tool, validation, dependency, database commit, approval and instruction-reference events |
| Client | `frontend/src/observatory.tsx`, `execution-model.ts`, `execution-graph.tsx` | History selector, graph, pan/zoom/minimap, filters, grouping, inspection dialog, replay, token/resource analytics, activity timeline |
| Existing UI | `main.tsx`, `features.tsx`, `assistant.tsx`, `design.tsx`, `styles.css`, `workspace.tsx`, `workspace-location.ts`, `api.ts`, `chat.ts` | Shared light/dark tokens, navigation, reduced motion, overview data, project drill-down, persistent per-message execution links, Markdown tables |
| Verification | `backend/tests/test_observability.py`, `test_registry_upgrade.py`, `frontend/tests/execution-model.test.mjs`, `workspace-location.test.mjs` | Usage math, missing metadata, redaction, RBAC/revocation including live SSE batches, replay/restart, lock isolation, guarded end-to-end workflow and graph reconstruction |

New dependencies: `psutil` for measured CPU/RSS and host memory; `@xyflow/react`
for the interactive graph; `motion` for restrained page/activity transitions;
`remark-gfm` for Markdown tables. Graph code and its stylesheet load only when
the graph is opened. No new background service, external telemetry sink or
framework replaces the existing application.

The graph follows the [React Flow component API](https://reactflow.dev/api-reference/react-flow).
Motion uses the [documented reduced-motion policy](https://motion.dev/docs/react-accessibility)
and a CSS reduced-motion override for transitions, skeletons and graph paths.

## Schema and event contract

0019 adds `execution_runs` (actor, conversation, conservative project/access
snapshot, trace ID, operation, status, timestamps and collector heartbeat) and
`execution_events` (event UUID, run FK, unique ordered sequence and JSON payload).
Actor deletion cascades through telemetry; retention cascades run events.
Business tables are not rewritten. Trace IDs use 32 hex characters, spans 16.

Every event contains:

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "run_id": "uuid",
  "trace_id": "32 hex characters",
  "span_id": "16 hex characters",
  "parent_span_id": null,
  "event_type": "span.started",
  "sequence_number": 1,
  "timestamp": "ISO 8601 UTC",
  "status": "running",
  "safe_payload": {"category": "request", "operation": "POST chat"}
}
```

Types: `span.started`, `span.ended`, `span.link`, `model.config`, `model.usage`,
`policy.reference`, `resource.sample`, `http.result`, `run.finished`.
A `span.link` carries a predecessor span ID in `safe_payload.reference_id` and
means an actual workflow dependency. Dashed graph edges represent hierarchy;
solid edges represent explicit dependencies. The critical-path highlight is the
longest measured explicit dependency chain, not a speculative path through model
reasoning or the sum of nested parent durations. An independent outline marks
the longest measured non-request operation. No complete distributed critical
path is claimed for boundaries without explicit dependency links.

Resource samples and model usage remain event payloads rather than redundant
additional tables. Truncated traces advertise `truncated=true` in the terminal
event. Missing span endings after interruption/truncation are labeled rather than
rendered as active forever or assigned invented durations.

## Endpoints

All monitoring endpoints require the existing cookie session.

| Method/path | Result |
|---|---|
| `GET /api/overview` | Scoped counts, current mapping review links and seven-day stored workflow outcomes; financial summaries unavailable |
| `GET /api/executions?conversation_id=…` | Latest 100 accessible actor-owned runs |
| `GET /api/executions/{run_id}` | Run, ordered events, authoritative aggregated usage |
| `GET /api/executions/{run_id}/events?after=N` | SSE with sequence IDs; honors `Last-Event-ID` |
| `GET /api/executions/instructions` | Settings-authorized instruction-set/version metadata; no confidential prompt text |

Instrumented operational responses include `X-Execution-ID`. New assistant
messages retain their execution ID in existing chat context and restore links on
history reload. The older string-activity endpoint remains compatible.

SSE events use `event: execution`; `event: complete` terminates finished runs,
and `event: access-ended` closes a revoked/expired session. The server reads at
most 100 events per batch, with one-second pacing and heartbeat comments. There
is no unbounded subscriber queue. The client merges by sequence number, uses the
native reconnect cursor and reloads persisted history on opening a run. An
initial run list refresh is every four seconds; run events use SSE, not frequent
full-trace polling. Only runs that execute on the current API worker have a live
memory tail. Other workers can replay that run's last flushed history.

## Privacy, authority and availability

Only allowlisted server operation names, IDs, counts, durations, version hashes,
resource measurements and safe failure codes are retained. Raw tool arguments,
results, prompts, replies, spreadsheet cells, exception messages, process command
lines, credentials and model reasoning are excluded. This is intentionally
minimal metadata, not unrestricted input/output logging. Ordinary users cannot
read other actors' traces, including administrators. Instruction metadata has a
separate `settings:read` gate. All contributing project assignments and their
captured grants are rechecked per detail request and SSE batch. Revoking any
captured grant hides that trace; this conservative rule can hide a trace after
an unrelated assignment changes. File identifiers refer to evidence already
retrieved through existing permission checks; they do not grant downloads.

Policy provenance separates available, retrieved, supplied, explicitly cited and
executed stages. Available pack metadata does not claim pack content was supplied.
Retrieved document IDs do not imply document text entered model context. Actual
system-context and response-schema hashes identify supplied context. Tool enum
schemas are recorded from the schema actually sent to Ollama. The current model
schema does not report explicit document citations; the UI labels this limit.
Deterministic rule outcomes come from the service result, not model text.

Prompt/output/total counters remain unavailable if omitted or invalid. Aggregate
counts remain unavailable if any invocation lacks the relevant measurement.
Truncated traces invalidate aggregate tokens and show an explicit warning; their
invocation count is only the observed prefix. Invocation count includes failed attempts; throughput uses output tokens divided
by actual `eval_duration / 1e9`, not request wall time. GPU metrics are unavailable.
API/host/Ollama utilization is shared usage observed during execution, not a
per-request cost or exclusive resource attribution. Ollama process CPU needs a
second observation. Missing/permission-denied Ollama process data stays unavailable.
The current configuration intentionally rejects remote Ollama origins; a loopback
proxy to a different host cannot provide trustworthy remote process attribution.
Set `TIMMY_TELEMETRY_MODEL_PROCESS_SOURCE=unavailable` for loopback proxies or
containers that do not expose the actual model processes. Local discovery
aggregates accessible processes named Ollama, not an isolated request or model.

Up to 64 unfinished/unflushed runs and 2,000 events/run by default are buffered.
A terminal slot is reserved. Event appends are synchronized across threadpool
and workflow execution. A separate SQLAlchemy pool uses a 20 ms SQLite lock
wait; business pool settings and transactions remain untouched. SQLite contention
defers collection; telemetry failures never approve, retry or commit business
operations. Persistent storage may lose an unflushed tail on a hard crash.
Collector heartbeats that expire after 15 minutes become `interrupted`; healthy
other-slot heartbeats prevent immediate restart misclassification. Long write
locks or worker pauses exceeding that lease can require operator investigation.
No OTLP exporter, durable external queue, or cross-process live event broker is
introduced. CLI-only scripts without an execution context do not create traces;
configured weekly scheduling does create actor-scoped runs.

## Verification and evidence

Automated coverage includes real FastAPI uploads and confirmations through the
existing representative synthetic fixture: project selection, original CSV
intake, Analyze, mapping review, Confirmed, structural validation, actual
policy/tool/dependency events, human-review handoff, persisted graph, and replay.
Existing tests assert no financial rows are created by that path. Ollama HTTP
response-contract tests use `httpx.MockTransport` with explicit usage metadata;
those fixture counts are test inputs, never demo metrics exposed in the UI.
CPU/RAM collectors are also tested against the running test process and host.
Stored history is tested across new FastAPI application instances.

A real local Ollama endpoint was unavailable during this implementation. Live
Qwen output, a full browser-driven end-to-end test, screenshots, screen-reader
behavior, actual mobile/tablet rendering, visual contrast across every legacy
screen and reduced-motion behavior in a browser remain unverified. The browser
access host was unavailable and the native Chrome fallback was not approved.
Responsive CSS, keyboard-accessible graph controls, a native focus-trapped dialog,
explicit text statuses and reduced-motion handling are implemented; full WCAG AA
conformance is not claimed without the remaining browser audit.

Run the README checks:

```sh
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests
.venv/bin/alembic -c backend/alembic.ini check
npm test --prefix frontend
npm run build --prefix frontend
curl -fsS http://localhost:8000/api/health
```

For safe local migration verification use a disposable database or apply 0019
with the normal local startup script. Do not point test migrations at production.
Final automated verification: 279 backend tests, eight frontend tests, a production
build, and Alembic schema check on a disposable migrated database. A temporary
actual Uvicorn server passed the README health curl. Its authenticated smoke test
returned a failed unavailable-model trace with 20 events, one real invocation
attempt, unavailable token counts, and a terminal SSE event; anonymous trace
access returned 401. The server was stopped after verification. No production
services or the normal workspace database were restarted or migrated.

Build warnings about upstream `use client` directives are nonfatal in Vite.

## Safe rollout and rollback

1. Keep production on its current release while verifying this commit in CI and
   an isolated staging database. No deployment/restart has been performed here.
2. Confirm the production revision. If it predates 0018, separately review the
   intervening domain migrations. This change does not authorize the existing
   deployer to skip its migration-tree checks or expand its pinned allowlist.
3. Take a consistent SQLite backup and verify its integrity. Review 0019 as an
   additive migration against 0018; test the old release against the expanded
   schema. No business rows or columns are changed by 0019.
4. An authorized operator applies the reviewed migration in the existing schema
   rollout process. When enabled, readiness now checks telemetry tables. Build
   with the existing production `VITE_API_URL=/api` configuration. Use the
   existing SHA-verified CI/systemd-slot/Nginx switch only after its schema gate
   has been satisfied through the documented reviewed process.
5. Preserve Nginx auth/cookie behavior; disable SSE buffering and keep an adequate
   proxy read timeout for `/api/executions/*/events`. The API returns
   `X-Accel-Buffering: no` and heartbeat comments. Monitoring stays authenticated;
   no new public unauthenticated metrics endpoint is added.
6. Inspect one authorized run, one denied actor/project, SSE reconnect and final
   usage. Confirm source, review and payment controls before routing traffic.

Environment defaults:

```dotenv
TIMMY_TELEMETRY_ENABLED=true
TIMMY_TELEMETRY_SAMPLE_SECONDS=3
TIMMY_TELEMETRY_RETENTION_DAYS=14
TIMMY_TELEMETRY_MAX_EVENTS=2000
TIMMY_TELEMETRY_MODEL_PROCESS_SOURCE=local
```

Sampling accepts 1–60 seconds, retention 1–365 days and the event cap 100–10,000.
Retention deletes expired terminal telemetry hourly; it never deletes financial
receipts or original evidence. Disabling telemetry stops new collection; retained
history can still be inspected. Disable collection first if it causes operational
pressure, using the existing controlled environment rollout. Roll back application
code and frontend assets using the current release-switch runbook. Leave the
additive telemetry tables in place: the 0018 application ignores them. Do not
restore a pre-migration database over live business writes. If permanently
removing telemetry, first stop/drain every telemetry writer, back up history, and
review `alembic downgrade 0018`; that drops only the two telemetry tables and
loses diagnostic history. Later domain migrations may make that downgrade
inappropriate, so prefer leaving the harmless additive tables intact.
