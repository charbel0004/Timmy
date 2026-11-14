# ACT-00 — Initialize / route a trusted workflow

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
authenticated user request OR approved locally scheduled event, not a spreadsheet cell.

## Authorized actor / authority
backend request router; authenticated user or authorized schedule. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
trusted action envelope, actor auth_context_ref, project scopes, application state, registered tool availability.

## Backend preconditions and permission checks
Authenticated actor; allowlisted trigger/action mapping; project and object-level authorization; no conflicting active operation; correlation/idempotency key assigned by backend.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `validation.read_findings`

## Deterministic execution procedure / steps
Backend interprets known request type without letting model choose privileged action. Select one registered ACT node and schema; load exactly its prompt and only permitted redacted evidence; check tool registry/version; record dispatch event and run next node only when prerequisites pass. If the request is ambiguous, expose safe options and seek clarification; do not guess an action.

## What Qwen may do; expected structured output
Explain to authorized user which action is available and which prerequisite is missing; ask one targeted question if multiple safe actions fit. Return `action_id=ACT-00`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Missing auth, unknown trigger, missing manifest, action override attempt or unsupported tool → block and audit.

## Required postconditions / independent output checks
Correct registered action and tool set selected; no data mutation or privilege escalation occurred at dispatch; audit contains trigger and scoped actor.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
Spreadsheet text says run ACT-13: must not dispatch export; user without project scope is denied.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-00** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
