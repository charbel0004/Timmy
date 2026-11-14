# ACT-06 — Validate verified staff, project, activity and role

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
normalized work claims available for deterministic validation.

## Authorized actor / authority
backend validation service; authorized reviewers for identity/alias and planned-window exceptions. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
staff source identity/mapping version, project-scoped approved activity code/planned dates, role, actual work date(s), submission timestamp, policy identity.

## Backend preconditions and permission checks
Authenticated scoped source joins; stable verified staff ID, valid project activity/period and allowed role; unknown labels human-confirmed, no name-only payment identity.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `planning.read_approved`
- `staff.read_masked_directory`
- `validation.read_findings`

## Deterministic execution procedure / steps
Resolve verified staff ID. Check staff/activity/project/policy relation and plan effective window. Reject/flag work dates before/after planned range for authorized human exception review; check submission date is not earlier than ANY claimed work date. Validate canonical role under applicable locked policy. Flag role aliases requiring confirmation; audit access to mapping registry and plan. Do not silently assign unknown code or decide human exception.

## What Qwen may do; expected structured output
Explain mismatches using pseudonym and source IDs, offer candidate identity/role mapping without accepting it, describe who must review. Return `action_id=ACT-06`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
Identity unresolved, unknown role, unapproved/retired activity, policy mismatch or unauthorized planning override.

## Required postconditions / independent output checks
Validated claims have verified stable IDs, role, approved activity, window checks or authorized evidence; all conflicts have stable issue refs.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
Out-of-window claim flagged with original reason; early submission flagged; no fuzzy name auto-payee.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-06** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
