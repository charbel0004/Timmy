# ACT-01 — Receive / classify uploaded evidence

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
file upload accepted at protected FastAPI upload endpoint.

## Authorized actor / authority
authenticated importer, backend storage service. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
server-computed file SHA-256, content type/magic, length, scoped importer, declared source kind, expected format contract.

## Backend preconditions and permission checks
Only approved formats; timesheets .csv/.xlsx only; planning/staff only preconfigured approved spreadsheet types; bounded bytes/rows/cells; no macros or encoded executable; restrictive filesystem permissions.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `source.describe_file`

## Deterministic execution procedure / steps
Backend streams to private temporary path with size bounds, computes checksum, validates actual file content and parser; rejects or quarantines unapproved data. Preserve original bytes once, create import attempt metadata and immutable source refs; classify as planning/staff/timesheet/report_return ONLY using trusted declared source and human-confirmed mapping—not model guess alone. Do not treat the filename as the authority.

## What Qwen may do; expected structured output
Summarize sanitized document metadata and propose source kind only when authority is ambiguous; ask human to select recognized class. Return `action_id=ACT-01`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
MIME/extension mismatch, path traversal, checksum/storage error, file too large, malicious formula/unsupported parser → quarantine/reject.

## Required postconditions / independent output checks
Original file immutable and indexed, source kind matches authorized registry; unsupported type not parsed; audit contains upload and accesses.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
CSV renamed .exe or Excel macro: reject. Same bytes twice: two attempt records do not duplicate work.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-01** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
