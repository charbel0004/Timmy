# ACT-16 — Record and inspect audit trail / postcondition evidence

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
all sensitive reads, writes, blocked actions, model suggestions, human decisions and reconciliation events.

## Authorized actor / authority
backend audit layer; Qwen no direct audit writes. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
trusted actor/trigger/correlation, resource access types/IDs, allowed action, before/after states, result, issue refs and transaction ID.

## Backend preconditions and permission checks
Immutable append-only events; protected state transitions coupled with audit in transaction; private values minimized; reader access scoped.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `audit.read_scoped`
- `issues.read_timeline`

## Deterministic execution procedure / steps
Backend preauthorizes; captures trigger (human click/import/schedule/external report), who and which project, what resource IDs were read/written/exported/denied, exact action and old/new safe states, rule and permission ref, timestamp/correlation, outcome/error. Verify recorded audit after operation. On denial record durable attempted access. For financial writes, audit failure fails closed. Feed redacted ordered events to report node; do not let AI invent or update audit entries. During returned-payment reconciliation call this action for every authoritative/denied state decision.

## What Qwen may do; expected structured output
Explain cited audit trail to authorized reviewer and point to missing evidence; no edit/delete/audit fabrication. Return `action_id=ACT-16`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Audit persistence unavailable, missing trigger/resource, permission violation or tamper signal; block protected financial action.

## Required postconditions / independent output checks
Every relevant protected transition has committed audit and resource access refs; forbidden access has denial audit; audit immutable.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
Permission denial logged without revealing names; reconciliation change and audit commit together; LLM cannot append audit.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-16** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
