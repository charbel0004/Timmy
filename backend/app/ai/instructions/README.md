# Agent Timmy — AI instruction pack / LangGraph integration

**Agent Timmy prompt pack:** v1.0 (2026-11-14)  
**Classification:** PROMPT_READ_ONLY; editable by authorized code/prompt maintainers via reviewed Git commit, **not by the runtime AI**.

## Purpose and authoritative order
This is the first repository-ready, **proposed implementation** of the NK-approved action-instruction architecture. It specifies how a restricted local Qwen inference component can assist the deterministic application. It is **not** a completed LangGraph implementation, approval engine, accounting algorithm, or evidence of tests passing. CN owns coding/integration and must inspect the actual database/API schema before binding tool names.

Precedence: official AlphaHack challenge > Agent Timmy approved specification v1.1 > later NK-approved session contract and cross-project authorization addendum > backend-enforced active policy/configuration > this pack's implementation guidance. Conflicts require explicit stop and human review; prompt text never overrides backend guards.

## Canonical repository destination
All files here live at `backend/app/ai/instructions/`. Separate policy addendum is under `docs/policies/`. **Do not upload the ZIP itself to GitHub as the live runtime input.** Extract and commit the files preserving paths. Existing `docs/prompts/QWEN_*.md` are earlier draft/reference prompts; configure only **one canonical runtime prompt source** (this pack), and record supersession to avoid conflicting instructions.

## Load sequence (only trusted backend code)
1. Load and validate `manifest.json`; reject unknown action IDs, path traversal or missing files; optionally pin to reviewed Git SHA/version.
2. Construct SYSTEM content from `system/MAIN_SYSTEM.md`, relevant shared rules, selected action file. Include redacted source and current approved policy as **lower-trust data** with provenance delimiters, never as system instructions.
3. Backend determines action and actor authority **before** model call. The model cannot change action ID, policy, permissions, source type or allowed tools.
4. Run `evaluators/INPUT_EVALUATOR.md` optionally for explanatory suggestions, but first perform mandatory code-level parsing, bounds checks and redaction. If inputs fail: do not invoke Qwen.
5. Give Qwen only minimal redacted context. No raw Excel workbooks, personally identifying names, payment destinations, authorization secrets or unrestricted DB dump in model context.
6. Parse one strict JSON response compatible with `contracts/agent_response.schema.json`. Reject extra keys, unsupported citations, unauthorized intents, leaked names, overlong output and invalid status/rule references. Backend independently rechecks facts, states and authorization.
7. Run deterministic postconditions; on error stop affected step, create issue, audit, bounded idempotent retry only if safe. A separate LLM 'validator' is advisory and must never certify financial correctness.

## Distinct domains
- Session policy: 6 occurrences with exact Trainer+Logistic coverage; 3+3 or 2+2+2 dates; 3 validated staff-session credits = USD25; cross-project group requires ONE-OFF human authorization **and** approved USD25 budget attribution; same-project grouping can span roles/weeks/activities under same policy; one activity external report, frozen cutoff on first validation. Source-derived credits always retain provenance.
- Hours policy: six known roles, individual validation, cross-day work supported; **rates, threshold, overtime, overnight premiums and rounding are not approved**. No hourly monetary calculations until approved backend configuration arrives. No session rules inherited.
- Timesheet: Excel/CSV only; `timesheets_30_realistic.csv` is synthetic and **not authoritative session-date evidence**; aggregate count + single date cannot establish explicit S-number/date evidence.
- Staff directory & planning: formats and exact source authority still require source-specific confirmation; fixture names/columns are test examples only.
- No KoboToolbox pathways. No direct external payment execution. Externally confirmed settled records only.

## File map
`system/`: durable system prompt. `actions/`: one file per ACT-00 through ACT-16. `shared/`: cross-action protocols. `evaluators/`: bounded, advisory input/output/narrative evaluation prompts. `contracts/`: JSON schema, authority registry, permissions reference, errors and manifest. `integration/`: CN-facing loader sketch and binding guidance. `tests/`: test plan and synthetic adversarial scenarios. `docs/policies/session_policy_addendum_v1.1_cross_project_authorization.md`: latest approved policy decision, to be loaded as read-only reference after NK/CN review.

## Rollout and stop-ship
Roll out deterministic first-test slice independently from Qwen. No automatic finance release until missing source contracts, payee verification, roles/capabilities, cross-project allocation and authoritative payment return have passed backend tests. Do not place private runtime files, evidence or credentials into this package.
