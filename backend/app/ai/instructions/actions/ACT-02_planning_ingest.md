# ACT-02 — Ingest authoritative planning sheet

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
authorized upload/sync of designated planning spreadsheet source.

## Authorized actor / authority
authorized planning importer/backend; mapping reviewer for unknown headers. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
original planning file+row refs, trusted planning authority label, project code, source approval state, activity codes, planned work dates, version/signature.

## Backend preconditions and permission checks
Planning source explicitly registered and authorized; real header mapping approved; no invented source columns or activity codes; project scope verified.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `source.describe_file`
- `source.read_redacted_rows`
- `planning.read_approved`
- `mapping.propose`

## Deterministic execution procedure / steps
Preserve original planning rows and version. Resolve approved header aliases. Propose unknown mappings for authorized human confirmation. Validate externally approved activity codes, project/date, duplicates, retired history and version transitions. Persist only source-backed approved values; retain retired codes and historical references. Update eligible activity lookup without creating/reassigning business activity codes. If planned session dates are not present, do not synthesize S-number→date schedules; wait for authoritative work evidence and approved mapping.

## What Qwen may do; expected structured output
Explain missing header, unclear approval column or ambiguous activity row with source-row citations; suggest but never approve a mapping. Return `action_id=ACT-02`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Unknown planning authority, unconfirmed header, duplicate conflicting code, invalid interval, no approval evidence, tampered source.

## Required postconditions / independent output checks
Every accepted activity has real source row + code + project/approval evidence; missing/retired rows flagged and preserved; no fabricated codes; audit of source version.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
Unknown code in timesheet cannot be backfilled from timesheet; later retired code retains historical link.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-02** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
