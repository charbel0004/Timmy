# ACT-13 — Export approved payment instructions to finance (not transfer)

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
authorized export action referencing exact approved immutable batch.

## Authorized actor / authority
backend export service after valid stored human approval; not Qwen. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
approved batch ID/hash, export file contract/version, verified recipient destination records, allocations, audit event and export idempotency key.

## Backend preconditions and permission checks
Hash/version unchanged; authorized human approval; all exact group budgets sum and payee verified; approved export format known and finance-only delivery.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `finance.read_batch_digest`

## Deterministic execution procedure / steps
Under transaction/checkpoint re-read current batch digest and persisted human approval. Compare exact hash, enforce one export per idempotency key and financial state lock. Render approved CSV/XLSX payment instruction **only from canonical approved rows**, protect formula-like cells on export, store in private generated path and record SHA-256. Deliver file for separate finance processing; never execute bank transfer. Verify count/hash and audit export event.

## What Qwen may do; expected structured output
Explain which prerequisite blocks export; never create an approval, alter destination or execute export by tool call. Return `action_id=ACT-13`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Unknown export schema, missing/stale approval, unallocated multi-project group, pending duplicate export state, access denied, failed audit transaction.

## Required postconditions / independent output checks
Export evidence links exact immutable approved batch, file hash and authorized user; no financial settlement status is inferred.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
Missing human approval or allocation → no export bytes; same idempotency key does not duplicate export.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-13** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
