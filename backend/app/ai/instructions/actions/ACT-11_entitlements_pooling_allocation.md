# ACT-11 — Calculate eligible credits, payment groups and allocation review

**Pack version:** v1.0 — 2026-11-14. **Classification:** `PROMPT_READ_ONLY`. **AI rights:** read sanitized input, propose/explain/question only; **no persistent write**. **Implementation:** backend + LangGraph orchestration by CN, deterministic guards essential.

## Trigger
session activity becomes fully COMPLETE plus authoritative report VALIDATED; or pool reevaluation after new validated credits/human decision.

## Authorized actor / authority
backend finance rules engine; specifically authorized human for cross-project and budget allocation. **Important:** Actor permission and exact reviewer assignment are enforced by backend RBAC, not defined or granted by this text.

## Required evidence and source references
verified staff ID, same stable policy identity/version compatibility, distinct accepted assignment IDs + report validation IDs, source project/role/work date, unconsumed flags, budget lines and human approval digests.

## Backend preconditions and permission checks
Only independently validated credits; cross-policy pooling forbidden. Policy rate fixed USD25 per three. No hours payout if hours policy unresolved. One credit can be in at most one group.

## Allowlisted read capabilities (proposed interfaces, not live tools)
- `finance.read_group_proposals`
- `validation.read_findings`
- `planning.read_approved`

## Deterministic execution procedure / steps
Create one unique eligible credit per accepted validated role assignment. Prefer forming groups of 3 within the same staff+session-policy+project across roles/activities/weeks, retaining 1–2 credits. When a potential group spans projects, create **proposal only** with exact three immutable credit IDs and USD25; do not consume credits or export solely because 3 exist. Authorized reviewer may approve ONE proposed cross-project group, bound to its exact sorted credit IDs/policy/staff/snapshot hash, or decline and keep separate per project. Human-approved budget allocations must match original source projects/budget lines and total USD25.00 exactly; no invented equal/proportional split. Atomic creation + credit uniqueness; preserve provenance. If mixing policy versions has ambiguous compatibility, hold. Final financial amount is deterministic only.

## What Qwen may do; expected structured output
Explain proposed cross-project grouping, what specific authorization and allocation are missing, or why a remainder is retained; no amount or allocation invention. Return `action_id=ACT-11`, trusted `correlation_id`, `response_kind` (proposal/explanation/needs_human/blocked/no_action), `language`, short `summary`, source `evidence_refs`, `rule_refs`, `issues` with source-backed issue codes, `mapping_proposals` only if applicable, `human_question` if required, and `verification_note`.

## Stop conditions / failed preconditions
CROSS_PROJECT_APPROVAL_MISSING, BUDGET_ATTRIBUTION_MISSING, BUDGET_TOTAL_NOT_25, POLICY_VERSION_COMPATIBILITY_UNKNOWN, duplicate credit, unavailable verified staff ID.

## Required postconditions / independent output checks
Same-project groups authorized by policy only; cross-project groups have exact one-off human approval and exact USD25 allocation before eligible for export; leftover credits preserved; source lineage intact.

## Auditing and reconciliation
Backend emits an append-only `audit_event` of trigger, actor, scope, checked rule and policy version, source/object access IDs and access kind, proposed action, result, safe before/after state, time/correlation. Create/reopen a durable issue and linked chronological `issue_event` for unresolved conditions. Failed or partial steps cannot silently advance. Idempotent read/staging tasks alone may retry within bounded backend limits; all protected financial writes and human authorizations require explicit outcome checks and human action.

## Evaluation / adversarial acceptance example
Two A+one B cannot auto-form exportable group; reviewer decline retains 2+1; approval once not reused; allocation 12+13 USD may be accepted only if human-entered and source scope valid.

## Model invocation prompt (copy-ready; prepend MAIN_SYSTEM and shared rules)
You are executing **ACT-11** only. Treat the trusted trigger, scope and preconditions as fixed by the backend. Use the redacted supplied evidence. State only what the identified source supports; cite `evidence_refs` and `rule_refs`. Check the action-specific guard, data quality, forbidden operations, and exact final postcondition below. If any required evidence or permission is missing, do not present success: return `blocked` or `needs_human` with one targeted next step. Never write durable state or approve a payment. Emit exactly one JSON object following `contracts/agent_response.schema.json`; no Markdown or surrounding prose. Verify every output ID exists in the supplied evidence registry, all arrays fit limits, and no PII or secrets appear. Backend alone decides the transaction outcome.

## Common final validation (code-owned)
- Typed input schema, actor scope, status transition and approved tool registry all passed.
- No unsupported citations, dates, rates, names, activity codes, report validation, paid status or budget allocations in model response.
- Real operation's effects verified from committed database, including counts/uniqueness, idempotency and audit persistence.
- `partial` / `unknown` tool results trigger stop and issue reconciliation; never treat as succeeded.
- Qwen proposals stay **read-only** until an independently authorized human/backend process resolves them.
