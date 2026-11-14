# ACT-15 — Generate weekly/manual historical operational report

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
authorized weekly scheduler or manual project/month report request.

## Authorized actor / authority
backend reporting service; Qwen may draft narratives using bounded events. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
authorized scope/time cutoff, versioned report template, deterministic reconciled financial metrics, ordered redacted issue events and approved source refs.

## Backend preconditions and permission checks
No future forecasting; currency segregated; no raw staff/payee details in model; source freshness/cutoff recorded; approved requester scopes.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `issues.read_timeline`
- `validation.read_findings`
- `audit.read_scoped`
- `finance.read_group_proposals`

## Deterministic execution procedure / steps
Backend calculates counts, balances and financial bridge from persisted tables and authoritative statuses, never from LLM. For each issue provide model bounded ordered redacted timeline. AI drafts origin/history/interventions/current state/action and cites event IDs per statement. Backend rejects unsupported or out-of-order claims, substitutes deterministic timeline when necessary, and stores a versioned snapshot. Separate action-required vs information-only, explain what changed and which rule triggered exceptions.

## What Qwen may do; expected structured output
Write bilingual evidence-grounded narrative; summarize meaningful issues and actions without inventing events, amounts or payment statuses. Return `action_id=ACT-15`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Unsupported narrative, missing financial metric source, unauthorized project read, unverified payment evidence; fallback not false success.

## Required postconditions / independent output checks
Report metrics independently verified; every narrative claim cites allowed event IDs; missing history explicit; fallback available; source evidence and report version saved.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
LLM fabricates extra incident → narrative rejected; Ollama down → deterministic report still generated.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-15** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
