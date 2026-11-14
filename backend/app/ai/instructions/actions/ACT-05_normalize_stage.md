# ACT-05 — Normalize source fields without rewriting evidence

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
parsed staging rows ready; authorized confirmed source field mapping.

## Authorized actor / authority
backend normalization service and human mapping reviewer. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
immutable source row refs, confirmed mapping version, permitted normalization transforms, original vs proposed values and timestamps.

## Backend preconditions and permission checks
Confirmed canonical mapping version; source rows immutable; no semantic guess about dates, staff, rates or quantities.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `source.read_redacted_rows`
- `mapping.propose`

## Deterministic execution procedure / steps
Trim control whitespace where safe, normalize approved Unicode forms, Arabic digits, role/header aliases; convert unambiguous explicit dates with declared source locale. Attach before/after and transform IDs for every material change. Unknown labels/date order/extra columns → human mapping. No silent discard, zeroing, data reordering, or conversion of 9 claimed sessions into valid 6; preserve exclusion evidence. Prevent arbitrary untrusted free-text forwarding to LLM.

## What Qwen may do; expected structured output
Produce candidate mappings or concise ambiguity explanation with row refs; cannot mark row valid. Return `action_id=ACT-05`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Unknown locale for slash dates, unexpected schema, lossy transform, missing mapping approval, output-vs-input count discrepancy.

## Required postconditions / independent output checks
Every normalized record retains original value, source row and version; unsafe data still flagged; no silent count changes.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
Arabic ٦→6 with raw retained; 07/08 ambiguous remains flagged; oversized row never silently shortened.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-05** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
