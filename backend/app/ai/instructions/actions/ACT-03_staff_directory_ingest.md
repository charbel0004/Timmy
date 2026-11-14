# ACT-03 — Ingest verified staff directory / identity mappings

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
authorized upload of verified staff source or approved human alias correction.

## Authorized actor / authority
authorized directory owner and mapping reviewer through backend UI. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
trusted directory source, verified stable staff IDs, original restricted bilingual names, active state, prior mappings with validity/audit refs.

## Backend preconditions and permission checks
Source authority authenticated; staff ID unique in verified scope; AI receives no raw names, payment references or mapping secrets; human alias confirmation required.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `source.describe_file`
- `source.read_redacted_rows`
- `staff.read_masked_directory`
- `mapping.propose`

## Deterministic execution procedure / steps
Backend parses original staff directory in restricted process and verifies stable staff IDs. Normalize Unicode for comparison while preserving original spelling. Generate candidate alias matches deterministically for authorized reviewers (e.g. Mohammed/Mohamad, El Khoury/Khoury, middle name differences); show AI only opaque tokens/difference descriptions. Reviewer confirms mapping, which becomes audited scoped alias; never create payment identity based only on similarity.

## What Qwen may do; expected structured output
Describe candidate ambiguity using opaque IDs, ask reviewer to select/reject; never output an actual person name from a protected mapping. Return `action_id=ACT-03`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Duplicate IDs tied to different people, missing verified identity, unauthorized identity reveal, name-only unconfirmed payment lookup.

## Required postconditions / independent output checks
Verified staff records and aliases attached to original source and human approval evidence; ambiguous identities stay unresolved; no name leak to model.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
Mohammad/Mohammed fuzzy candidate remains pending until signed human approval; repeated accepted alias reused and audited.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-03** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
