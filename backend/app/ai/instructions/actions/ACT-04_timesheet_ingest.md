# ACT-04 — Ingest session/hour timesheets (Excel/CSV)

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
authorized timesheet upload or acknowledged reimport after correction.

## Authorized actor / authority
authorized importer, deterministic parser; human header reviewer as needed. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
file/hash/import run/sheet/row refs; declared project/policy family; original dates, staff ID, role labels, S-number→date pairs or hour-time fields; submitted_at.

## Backend preconditions and permission checks
CSV or XLSX only; correct project and policy family; no formula evaluation; strict input limits; original rows preserved; approved mapping exists or pending reviewer.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `source.describe_file`
- `source.read_redacted_rows`
- `mapping.propose`

## Deterministic execution procedure / steps
Read exact row count and original values. Map approved fields; normalize Arabic-Indic digits and unambiguous ISO/local dates; preserve raw strings. Session: require explicit each S# 1..6 → actual work date; a single row may claim S1,S2,etc. Aggregate session_count with one date is insufficient and flagged. Hours: preserve explicit start/end datetime or approved duration fields; do not manufacture missing end day. Expand normalized child claims without duplicating source. Flag duplicate/replayed rows, invalid integers, missing staff ID or unexpected role; do not calculate payment in ingestion.

## What Qwen may do; expected structured output
Suggest canonical header/role mapping from redacted snippets, explain concrete row issue and ask exact follow-up. Arabic and English okay. Return `action_id=ACT-04`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Unconfirmed mapping, malformed date, unsupported file, input truncation, ambiguous session occurrence, unsupported/negative value → flagged/blocked per row.

## Required postconditions / independent output checks
All rows represented in staging (including errors); accepted child claims reference original row; row totals reconcile; no pay or validation state asserted.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
CN synthetic 30-row fixture aggregate count and one date MUST NOT pass six-occurrence evidence; no false COMPLETE.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-04** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
