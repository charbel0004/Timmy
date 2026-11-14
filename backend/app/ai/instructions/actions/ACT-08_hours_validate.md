# ACT-08 — Validate hours-based individual claims without guessing rates

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
hours-based normalized work record entered and role/identity/plan verified.

## Authorized actor / authority
backend hours rules engine, human reviewer for unresolved sources/policy settings. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
staff+approved activity/role, explicit start/end datetime or approved duration, source time-zone, planned window, role-specific approved policy configuration and report gate when required.

## Backend preconditions and permission checks
One of DRIVER/TRAINER/LOGISTIC/ADMINISTRATOR/DATA_ENTRY/FIELD_TEAM; record verified independently per staff; no session group or six-session requirement.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `hours.read_entries`
- `validation.read_findings`
- `reports.read_authority_status`

## Deterministic execution procedure / steps
Validate time representation, positive duration, explicit date on overnight crossing, overlapping entries as potential conflict, in-window work portion, submission not before work. Record raw and verified duration precisely (integer seconds/minutes) and any flagged overtime/overnight eligibility questions. Apply overtime/premium/caps/rounding **only if fully human-approved locked hours policy parameters**; until then preserve validated time evidence but block monetary entitlement. Never apply a guessed threshold or $25 session rule.

## What Qwen may do; expected structured output
Explain ambiguous overnight or overlapping work, ask for required time-zone/duration or missing policy parameter; may narrate, not compute final money. Return `action_id=ACT-08`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
HOURS_POLICY_UNCONFIGURED, ambiguous midnight, missing break rule if material, unsupported overtime premium, invalid duration or unknown zone.

## Required postconditions / independent output checks
Individually verified or flagged hour record with provenance; no authoritative payment amount without complete approved hours policy and required report authority.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
22:00–06:00 without next-day date not auto-inferred; no session policy applied to hours.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-08** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
