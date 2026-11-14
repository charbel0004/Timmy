# ACT-10 — Consume authoritative report validation and freeze cutoff

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
verified external report submission/resubmission/validation evidence imported or refreshed.

## Authorized actor / authority
backend authoritative report adapter; not Qwen or timesheet submitter. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
activity/report authoritative ID, submitted version ID(s), local submission date, actual version receiving external VALIDATED status, source proof/time-zone, recorded current frozen cutoff.

## Backend preconditions and permission checks
One report per session activity, verified source and version/order, project-local calendar convention confirmed; mutation of external authority status forbidden.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `reports.read_authority_status`
- `activity.read_sessions`
- `validation.read_findings`

## Deterministic execution procedure / steps
Record each authenticated report submission version immutably. Before first VALIDATED: allow later authentic submission to replace candidate date but do NOT permanently invalidate post-candidate work. At first independently verified VALIDATED: pick specifically validated version, freeze its submitted local date once using atomic compare-and-set; preserve event ID. Recheck all activity work dates against cutoff, exclude post-cutoff claims with flag for human disposition, recompute 6/12 coverage, then VALIDATED only if still COMPLETE with no blockers. Subsequent report versions never automatically shift frozen cutoff; reconciliation/human governance required for errors. For hours-based external report contract do not assume identical gate before AJ confirmation.

## What Qwen may do; expected structured output
Explain source-backed report history, candidate vs frozen cutoff, excluded claims with exact version/event refs; no status edit or cutoff rewrite. Return `action_id=ACT-10`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Missing report authority/version/time-zone, validation from untrusted sheet, already frozen cutoff conflict, post-cutoff invalid source requiring review.

## Required postconditions / independent output checks
At most one first-freeze event per activity, exact validated version linked, post-cutoff claims not eligible, batch validated only if recomputed checks pass.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
Submitted Jul12 resubmitted Jul15 validated Jul16 → cutoff Jul15; later Jul20 resubmission cannot autoextend.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-10** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
