# ACT-09 — Detect discrepancies, route authorized review and preserve history

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
validation defect, competing claim, unresolved mapping, or authorized review response.

## Authorized actor / authority
backend issues engine; specifically permissioned human reviewer for decisions. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
stable issue ID/code, rule ID, original file/row/claim refs, affected state, prior issue event history, human decision evidence if any.

## Backend preconditions and permission checks
No AI issue dismissal; only authorized human can invalidate claim, approve an allowed planning-window exception or confirm mapping.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `validation.read_findings`
- `issues.read_timeline`

## Deterministic execution procedure / steps
Deduplicate recurring issue identity without losing event history; record detected state and affected financial exposure. Show restricted reviewer source trace and proposed choices (invalidate using original issue reason, optional note; request correction; authorize allowed planning exception when permitted). Human decision must be bound to issue/claim, reviewer permission, time and audit. Re-evaluate dependent completeness and credits after confirmed decision, preserving previous states and irreversible finance history. Do not silently discard invalidated rows or clear unresolved issues.

## What Qwen may do; expected structured output
Provide concise evidence-grounded issue summary/history in chronological order, a targeted clarification, and likely candidates only as nonbinding hints. Return `action_id=ACT-09`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Missing actor capability, conflicting evidence, invalid override type, irreversible settlement exposure or ambiguous reviewed claim.

## Required postconditions / independent output checks
Issue state and ordered event trail consistent with actual human decision; invalidation uses original issue code unless optional text; no unapproved state advancement.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
Human clicks invalidate with no note → code preserved; audit includes before/after and original source; AI-only reply causes no mutation.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-09** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
