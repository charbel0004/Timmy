# ACT-14 — Ingest returned payment evidence and reconcile settlement

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
authorized, verified external payment return file arrives/refreshes.

## Authorized actor / authority
backend returns/reconciliation engine; finance reviewer for unresolved exceptions. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
trusted return authority, file hash/version, external transaction reference, exact instruction ID/payee, status mapping, amount/currency, time and prior settlement allocations.

## Backend preconditions and permission checks
Only approved external format and status semantics; settlement requires authoritative settled evidence and no duplicate external reference; source IDs and payee match verified instruction.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `payments.read_returns`
- `finance.read_batch_digest`
- `validation.read_findings`

## Deterministic execution procedure / steps
Preserve original return file/rows; resolve by approved transaction/instruction refs; compare payee and currency. Pending, unknown, failed, partial, unmatched or duplicate responses remain explicit separate states. Allocate ONLY confirmed externally settled amounts, atomically with uniqueness and audit; never over-credit entitlement. Compute remaining obligation from original entitlement minus confirmed settlements. Do not reissue unknown/pending attempts automatically. Failed payments do not create second obligation; new attempt requires authorized human-approved batch.

## What Qwen may do; expected structured output
Explain exact reconciliation discrepancy with redacted ID and cited status; do not change settled state or initiate retry. Return `action_id=ACT-14`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Unapproved return schema, forged status, payee mismatch, ambiguous reference, pending/unknown status, settlement exceeding obligation, missing audit.

## Required postconditions / independent output checks
Settled total derives only from authoritative evidence; returns and credits are nonduplicative, residual linked to original; mismatches in issues.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
Matching amount + pending state not paid; duplicate external transaction not double settled; confirmed partial retains remainder.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-14** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
