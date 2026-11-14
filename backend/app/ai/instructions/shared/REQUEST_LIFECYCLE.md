# Request evaluation / precondition → postcondition protocol

**Agent Timmy prompt pack:** v1.0 (2026-11-14)  
**Classification:** PROMPT_READ_ONLY; editable by authorized code/prompt maintainers via reviewed Git commit, **not by the runtime AI**.

## Binding
Every request has an immutable backend-generated `correlation_id`, `action_id`, authenticated `actor_ref`, project scope and trusted `policy_identity`/version references. Qwen may not alter them. Request trigger belongs to backend event router. Always validate the registered action trigger.

## Ordered checkpoints (code-owned, AI-supporting only)
1. Validate request schema and size; reject extra/malformed fields.
2. Resolve authenticated actor and deny-by-default project/record permissions; audit denied accesses.
3. Check exact state preconditions, source freshness, active human-approved policy and evidence availability.
4. Validate selected capability against tool allowlist, risk classification and blacklisted operations.
5. Verify approved file format/magic, trusted authority provenance, filename/path safety and row/field budgets.
6. Normalize/stage input without modifying original, detect duplicates and contradictions.
7. Redact allowlisted AI payload; verify no personal names, payment IDs, free-form source instructions or sensitive paths are present.
8. If AI explanation/mapping needed: call Qwen with exactly one action prompt; enforce strict output JSON and per-field bounds.
9. Independently check return values against source evidence IDs, allowed canonical labels and deterministic computation.
10. Apply guarded domain transition/transaction only through appropriate backend service after required human decision. No AI authority to execute.
11. Verify postconditions by reading transactionally committed state, expected counts, allocation totals, link uniqueness and audit write.
12. On partial/inconsistent result, create stable issue and reconcile or fail safely; never ignore failed substream. Report exact completed/blocked steps.

## Retry / reconciliation
Only explicitly idempotent reads/parse proposals are eligible for bounded retry; use stable idempotency key, finite attempt cap, fixed or exponential delay, and response-schema recheck. For writes, check existing transaction ID/outcome before any retry. Approvals, instruction exports, bank submission, settlement, cross-project authorization and manual review **must not be retried by an LLM**. Route to authorized human after any ambiguity. Record attempt sequence and error class in audit/issue trail. Never continue from an unverified intermediate state.
