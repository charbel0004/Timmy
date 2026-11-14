# ACT-07 — Validate six-session activity and exact two-role coverage

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
session-based claims normalized, staff/activity/role mapping checks complete.

## Authorized actor / authority
backend session rules engine; human for duplicate/invalid claim decisions only. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
approved activity, S1–S6 indexed occurrences+dates, accepted Trainer/Logistic claim IDs, staff IDs, resolved issues, planned windows, report state (read only).

## Backend preconditions and permission checks
Approved SESSION policy identity/version and activity; explicit S-number→work date for each claimed assignment; no unreviewed duplicate/exception.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `activity.read_sessions`
- `validation.read_findings`
- `reports.read_authority_status`

## Deterministic execution procedure / steps
Build six occurrence slots from explicit evidence, validate S# unique 1..6, date order and only 3+3 or 2+2+2. For each S# verify exactly one accepted Trainer and one accepted Logistic; same date and different staff IDs. Keep raw duplicate claims and require authorized resolution; at most one accepted per role slot. Compare submitted_at with work dates and plan window. Only if all twelve required accepted assignments valid may backend set activity batch COMPLETE. No partial COMPLETE, no eligible session credit before external report VALIDATED and frozen cutoff recheck.

## What Qwen may do; expected structured output
Explain missing S#/role/date mismatches with exact evidence refs and rule ID; never certify or transition activity. Return `action_id=ACT-07`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Missing explicit dates, role collision, one person dual role same occurrence, 1+2+3, incomplete role coverage, unresolved source conflict.

## Required postconditions / independent output checks
COMPLETE only if 6 distinct occurrences/12 valid assignments and no blocking issue; otherwise UNDER_REVIEW/FLAGGED with detailed missing slots.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
3+3 and 2+2+2 pass when full; 1+2+3 and same person as both roles fail; one-row multiple S entries can be valid.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-07** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
