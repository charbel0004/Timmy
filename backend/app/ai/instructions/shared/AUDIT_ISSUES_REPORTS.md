# Audit, issue history, and report prose

**Agent Timmy prompt pack:** v1.0 (2026-11-14)  
**Classification:** PROMPT_READ_ONLY; editable by authorized code/prompt maintainers via reviewed Git commit, **not by the runtime AI**.

**Backend writes audits, not Qwen.** Every access to restricted staff name/payment destination, import, accepted human mapping, state transition, denied action, approval, export, external report source, reconciliation or privileged exception records: immutable event ID/sequence and UTC timestamp, user or system actor, role/project scope, trigger kind/ref, correlation/request ID, action, safe before/after state or field summary, accessed resource type/ID and mode, expected vs observed outcome, evidence refs, error/reason code, rule/policy version, and related issue ID. Do not include raw names, payment IDs, source rows, credentials or prompt payloads in logs.

The state-changing domain write and mandatory audit write should commit atomically. Denied action requires durable audit. Failure to persist a required audit record blocks protected state change.

Issue state is a summary; `issue_events` is an append-only chronological record: detected → reviewed → clarification → new evidence → authorized correction/invalidation → resolved/reopened. Human invalidation inherits issue's original reason code; an additional human free-text reason is optional. Preserve raw evidence, accepted revisions and effects.

Operational report: deterministic indicators and financial bridge; AI may fill a standard prose template from bounded, redacted issue history only. Each factual sentence/paragraph must have supplied event refs in chronological order; include origin, prior steps, changes, current state and requested action. If earlier events absent, state 'No earlier recorded events available.' If citation check fails/Qwen unavailable use deterministic event-list fallback, never invent data or miss a scheduled report.
