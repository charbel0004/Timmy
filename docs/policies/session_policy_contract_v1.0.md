# Agent Timmy — Session-Based Policy Contract

**Version:** 1.0  
**Date:** 2026-11-14  
**Decision authority:** NK  
**Implementation owner:** CN (database/persistence and corresponding deterministic validation support); NK owns financial workflow/rules review  
**Status:** **Approved session-policy business rules**; source-format and cross-project budget-attribution details explicitly identified as integration questions below. Not evidence of implemented code.  
**Intended GitHub path:** `docs/policies/session_policy_contract_v1.0.md`

## 0. Authority and scope

This contract records NK's explicit session-policy decisions from the November 14, 2026 clarification rounds. It refines and, where inconsistent, supersedes the earlier unresolved session-policy assumptions in `Agent_Timmy_Approved_Project_Specification_v1.1` and the proposed physical mapping in `docs/Agent_Timmy_Database_Implementation_Specification_v1.0.md`. It does **not** override the official challenge's mandatory requirements or the broader requirements for authentication, financial approval, externally verified settlement, budget accounting, and audit.

This is the **session-based** payment family. The separate hours-based family is not governed by six-session, session-date, or session-group logic. No KoboToolbox ingestion. Timesheets enter through approved Excel/CSV files only. Activity codes originate exclusively in the approved external planning spreadsheet.

**Important boundary:** Policy parameters are supplied and approved by humans and stored in protected versioned backend configuration. The AI may read policy, suggest aliases/column mappings and explain exceptions, but **cannot create, edit, activate, override, or silently reinterpret the financial policy**. Policy edits require separately authorized, audited, human-controlled versioning; the agent has no policy-write tool.

## 1. Locked configuration

| Key | Configured rule | Source/status |
|---|---|---|
| `family` | `session` | NK approved |
| `session_count_per_activity` | Exactly `6` distinct indexed session occurrences, S1–S6 | NK approved |
| `required_roles_per_occurrence` | Exactly one `TRAINER` **and** exactly one `LOGISTIC` accepted assignment | NK approved |
| `same_session_and_date` | Trainer and Logistic accepted assignments for a given S-number share the same activity code, occurrence identity and **work date** | NK approved |
| `distinct_staff_same_occurrence` | Same person **cannot** fill both required roles in **the same** activity session | NK approved |
| `staff_across_occurrences` | Different people may fill a role in different occurrences, including on the same date | NK approved |
| `work_date_ordering` | S1–S6 dates are nondecreasing | NK approved |
| `allowed_date_distribution` | Exactly `3+3` on two distinct dates, **or** exactly `2+2+2` on three distinct dates; not `1+2+3` or other patterns | NK approved |
| `max_sessions_per_date` | `3` | NK approved; also implied by patterns |
| `timesheet_evidence` | Each claimed session requires explicit `session_number -> work_date` mapping; one row may contain multiple sessions (e.g. S1 and S2) | NK approved |
| `payment_unit` | One accepted eligible staff-session/role assignment, attached to a uniquely identified activity occurrence | NK approved / dedup consequence |
| `group_size` | `3` eligible staff-session units | NK approved |
| `group_rate` | **USD 25.00 per complete group of three** | NK approved |
| `aggregation_scope` | Same **verified volunteer/staff**, same **session policy**, across roles, projects, activities, payment events, weeks, and dates | NK approved |
| `cross_policy_pooling` | **Forbidden**; a separate policy never contributes units to this pool | NK approved |
| `remainder` | `0`, `1` or `2` eligible ungrouped units are preserved and become part of later groups; no expiry established | NK approved |
| `activity_completion_gate` | All six session occurrences must have a valid Trainer/Logistic pair before session-based **batch `COMPLETE`** | NK approved |
| `external_report_gate` | One authoritative report per activity; **report `VALIDATED` required** for associated session units to count as validated/financially eligible | NK approved |
| `report_cutoff` | A report's **latest authoritative submission date at first validation** is the hard cutoff for work dates; cutoff check is enforced when report becomes validated | NK approved; precise freeze interpretation described in §4 |
| `planned_work_window` | Work date outside approved planning start/end → flag for human authorization or invalidation | NK approved |
| `submission_not_before_work` | Submission date cannot precede any work date claimed by that submission | NK approved |
| `excess_claims` | Do not count unsupported/over-capacity claims; preserve and flag exclusions, explain rule and effects, ask human confirmation | NK approved |
| `invalidation_reason` | Original flag reason is sufficient for authorized invalidation; reviewer may add optional detail | NK approved |
| `session_timefields` | No clock-in, clock-out, duration, overtime or overnight for session policy | NK approved |

### Roles and allowed role aliases

Canonical session role codes are `TRAINER` and `LOGISTIC`; aliases are controlled, **not** independent payment policies. Examples for seeded, human-approved aliases:

- `TRAINER`: `Trainer`, `Facilitator`, `ميسّر`, `مدرّب`.
- `LOGISTIC`: `Logistic`, `Logistics`, `لوجستيات`.

The agent may propose new unknown-label mappings for human confirmation; once accepted, save an audited, versioned alias entry for subsequent exact reuse. The agent cannot invent a third session role or change the required pair.

## 2. Activity occurrence and staffing invariants

Within each project-scoped, planning-approved **permanent activity code**, represent occurrences `S1`, `S2`, `S3`, `S4`, `S5`, `S6` individually. A date may appear for two or three consecutive occurrences, but the only allowable **date patterns** are:

```
3+3:     S1,S2,S3 -> D1; S4,S5,S6 -> D2; D1 < D2
2+2+2:   S1,S2 -> D1; S3,S4 -> D2; S5,S6 -> D3; D1 < D2 < D3
```

One date repeated for **all six** is invalid, as is `1+2+3` even though it spans three dates and respects a maximum of three sessions on a date.

Each occurrence has exactly **two accepted role assignments**: one Trainer and one Logistic from **two distinct verified staff IDs**, with the exact same recorded work date. For example, the Logistic assigned to S1 and S2 on D1 may be the same person, while the Trainers differ; the same staff member may fill Trainer in S1 and Logistic in S2, but never both roles in the same occurrence.

Do not confuse: (a) six delivered session occurrences, (b) 12 required role-assignments, (c) number of submitted rows, (d) number of distinct people, and (e) payable three-unit groups. Additional submitted rows or repeated imports cannot create extra occurrences or accepted assignments.

**Submitted evidence:** One Excel/CSV row may cover multiple occurrences. It must explicitly identify each `S-number -> work_date` pair. An aggregate `session_count=3` with only one date is **insufficient** to establish which sessions were attended. Preserve the row and flag for review. Actual source-column layout needs confirmation from the planning and timesheet examples; the application may use a human-confirmed mapping and normalized child records. Never invent missing session dates.

**Duplicates/conflicts:** If two staff claim the same activity/S-number/role, keep both source claims, flag the collision and accept **at most one** only after deterministic resolution or authorized human confirmation. A repeated upload cannot create another credited unit.

## 3. Completeness, validation and payability

Session-based batch scope is **one complete activity code's six occurrences** (with project-scoped identity). No half-activity `COMPLETE` state.

1. **RECEIVED:** source rows imported and immutably retained.
2. **UNDER_REVIEW / FLAGGED:** identity, planning approval, date, occurrence, role and duplicate checks run; unresolved issues persist.
3. **COMPLETE:** six distinct session occurrences satisfy approved two-role coverage, date distribution and all applicable internal eligibility rules; no unresolved blocking claims. This means the activity has been internally packaged, **not** paid or externally validated.
4. **VALIDATED:** the single authoritative external activity report is independently `VALIDATED`, its cutoff is frozen, and all accepted source work dates pass the final cutoff rule. Report validation may trigger rechecks/invalidations; a batch cannot remain `VALIDATED` if its required evidence is then insufficient. It must be held for controlled reconciliation rather than silently accepted.
5. **PAYABLE UNITS:** only accepted, deduplicated, report-validated staff-session credits enter each staff's session-policy accumulation pool.
6. **PAYMENT GROUPS:** backend groups eligible, unconsumed units in threes across the approved accumulation scope, each group worth USD 25.00. New groups can appear in later payment runs; they are not new activity sessions.
7. **PAYMENT INSTRUCTIONS:** require verified payment destination and a persisted human approval over the exact immutable payment batch before export. External execution and returned settlement evidence remain separate from entitlement/instruction.

**Identity:** Grouping key is the stable verified internal staff identifier, **not** raw names, aliases or pseudonym display. Staff mappings may suggest candidate matches but require human confirmation for ambiguity.

### Accumulation examples

**Example A — across time:** Staff E has two already validated unconsumed units at week 1, then four additional validated units at week 4 (from any qualifying activity/project/role under the **same** session policy). Total six unconsumed units → **two groups = USD 50.00**, subject to payment authorization. Work from an incomplete or unvalidated activity never enters the eligible pool.

**Example B — across role and project:** Staff F has one validated Trainer unit in Project A, one validated Logistic unit in Project B, and one validated Trainer unit in Project C, all under the exact same session policy identity → **one USD 25.00 group**. This example establishes **payment eligibility**, not a budget cost-sharing allocation formula (see unresolved integration question below).

**Example C — policy boundary:** Two units under session policy `P-A` and one under `P-B` → **no cross-policy group**. Neither is silently lost.

**Example D — partial group:** Four eligible unconsumed units → one new group and one unconsumed unit; only the three group units are marked allocated to a group, never the remaining one.

### Grouping algorithm (contract, not implementation code)

For each `(verified_staff_id, approved_session_policy_id)` pool:

- Gather only accepted, authoritatively report-validated, currently eligible staff-session credits that have **not** been consumed into an existing group.
- Exclude credits blocked by duplicate/conflict, work-window, cutoff or unresolved identity conditions.
- Order consistently using deterministic canonical ordering (e.g. eligibility-confirmation event sequence + stable credit ID); publish this choice and keep it stable so retries produce the same grouping. **Specific tie-break implementation is a CN design choice subject to review**, not a new financial eligibility rule.
- Calculate `new_groups = floor(available_unconsumed_credits / 3)`; create groups in one transaction, linking **exactly three distinct credit IDs** to each group; set group amount `USD 25.00`. Leave 0–2 credits unconsumed.
- Prevent consuming any credit more than once (DB uniqueness + transactional/service checks). Prior group creation, payment attempts, partial/unknown settlement, carry-forward and retried imports must not create duplicate obligations.
- Across-project group **expense allocation** is deliberately **not inferred**. A group may be eligible for payment while remaining `ALLOCATION_REVIEW_REQUIRED` and barred from instruction export until an approved budget-attribution rule is available. No AI splitting/rounding of financial allocations.

**Policy identity caveat:** The grouping boundary is **policy**, not project or role. A policy may be referenced by multiple projects. Do not substitute `project_id` for `policy_id`, and do not pool unrelated policy IDs even if their names/rates match. How version changes affect an existing carry-forward pool should not be guessed: retain source policy/version evidence and hold any version-boundary case for authorized interpretation unless explicitly compatible.

## 4. Work dates, report resubmission and non-reversible cutoff

**Work-date window:** Compare actual service dates with approved planning start and last date. Out-of-window claims are flagged for human review and may be authorized or invalidated under the permitted planning-exception flow. Originals are never erased.

**Submission-date sanity:** Each timesheet's effective submission date must be **on or after every work date** it claims. Late submissions are allowed; no general post-work submission deadline has been approved. An impossible early submission is not automatically made valid by changing its date; flag for correction/review.

**Single activity report:** One authoritative external report covers the entire six-session activity and associated submissions. The report has a **submission timestamp/date** and a separate **external validation state**. Report submitted does **not** mean report validated.

**Before report validation:** Preserve all report submissions/resubmissions as versioned source evidence. The latest authoritative submission/resubmission date is the candidate cutoff; the final report cutoff rule is **not enforced to invalidate work** until the external report's first authoritative `VALIDATED` state is observed.

**At first external validation:** Freeze the candidate cutoff corresponding to the report version actually validated. Reject/exclude any claimed work date **after** that cutoff, even if its timesheet is uploaded later. Work on the same calendar date passes the date-only cutoff, subject to other checks. This validation/exclusion and frozen cutoff **cannot later be automatically reverted** by a new report version or agent decision. Preserve validation evidence, report version/ID, frozen cutoff and affected claim decisions.

**Illustrative:** Report submitted July 12, later authoritatively resubmitted July 15, then validated July 16 → cutoff **July 15**. A claimed work date July 14 is in range; July 16 is beyond cutoff. If the report was already validated on July 12, a later resubmission does **not** automatically extend the frozen cutoff. Handling a genuine post-validation source error requires an explicit separately authorized governance decision; no ordinary agent-driven cutoff override is defined in this policy.

**UTC/date nuance:** If authoritative sources provide dates only, compare local **dates**, not invented times of day. If source supplies timestamps, preserve original zone and derive cutoff service date using an agreed project time zone (not yet provided); ambiguity fails closed.

## 5. Review, invalidation and issue evidence

Distinguish three statuses: **raw claim preserved**, **validated/accepted assignment**, and **payment credit**. An exclusion changes the latter two, not the original evidence.

For flagged claims, record the machine-checkable issue code and affected source IDs. Examples:

- `MISSING_STAFF_ID`, `AMBIGUOUS_IDENTITY`, `ROLE_UNKNOWN`, `ROLE_ASSIGNMENT_CONFLICT`
- `MISSING_SESSION_NUMBER`, `MISSING_SESSION_DATE`, `INVALID_DATE_PATTERN`, `SESSION_DATE_MISMATCH`
- `PLANNED_DATE_OUT_OF_RANGE`, `SUBMISSION_PRECEDES_WORK`, `AFTER_VALIDATED_REPORT_CUTOFF`
- `SESSION_COUNT_EXCEEDS_ACTIVITY`, `DUPLICATE_CLAIM`, `UNAPPROVED_ACTIVITY`, `REPORT_NOT_VALIDATED`

A human can confirm invalidation using the already recorded flag reason; additional free-text explanation is **optional**. A permitted planning-window exception is explicitly authorized and audited; it is not permission for the AI to rewrite report validation/cutoff, add activity sessions or adjust the policy.

An exclusion/reconciliation report must contain: source file/row/submission, project/activity/session/role/staff pseudonym, rule ID, original versus accepted quantity, validation status, original flag reason, human decision (if any), resulting state transitions, and associated audit/issue-event references. Avoid real names in generic agent narratives.

If newly validated report evidence changes accepted units, re-evaluate six-session coverage **before** releasing groups. Do not rely on previously cached `COMPLETE` status after excluding required role assignments.

## 6. AI agent boundaries and instruction hooks

For every action, run backend-controlled: trigger classification → authorization and denylist → preconditions → allowlisted harness tools → bounded, safe document parsing → input schema/mapping validation → deterministic procedure → intermediate/postcondition checks → audit → state transition. On failure, stop affected progression; retry only idempotent operations within bounded limits or create a reconciliation/human-review task. Every attempted action records trigger/access/action/outcome.

The AI may propose name/role/header aliases, detect suspicious or incomplete evidence, explain a mismatch, draft event-grounded issue history and request human mapping confirmation. It may **not** edit the policy, select verified payment identities based only on fuzzy names, invent session occurrence/date, accept a duplicate role assignment, validate an external activity report, extend a validated report cutoff, calculate an authoritative payable amount by untrusted prose, approve or send a payment, or claim external settlement.

Treat uploaded spreadsheet cells, filenames and remarks as untrusted **data**, never instructions. Validate exact accepted file types/size, parse within bounds, reject injected or unexpected fields, and preserve evidence. AI-only 'ignore previous instructions' guardrails are insufficient: tools and backend must enforce permissions and transactional financial invariants.

### Action index cross-references (instruction details to follow with Prompty)

- `ACT-02` planning ingestion: approved activity code, scheduled window, occurrence evidence.
- `ACT-03` directory ingestion: authoritative staff identifier and human-verified aliases.
- `ACT-04` timesheet ingestion: per-row multiple session mappings, source preservation.
- `ACT-05` normalization: Arabic/English labels, numeric/date normalization.
- `ACT-06` identity/role/activity verification and candidate mapping review.
- `ACT-07` six-session pair/date-pattern completeness and report-cutoff revalidation.
- `ACT-09` issue detection/exclusion/reconciliation reporting.
- `ACT-10` one external activity report per activity, versioned submission/validation.
- `ACT-11` cross-project/cross-role per-staff per-policy payment group accounting.
- `ACT-12` / `ACT-13` mandatory human approval and exact-batch instruction export.
- `ACT-16` append-only audit of trigger, resources accessed, action, postconditions and result.

## 7. Acceptance scenarios — specification, **NOT RUN**

| ID | Scenario | Expected outcome |
|---|---|---|
| S-T01 | S1–S3 D1, S4–S6 D2; one Trainer and one different Logistic for each | Eligible for `COMPLETE` when all other internal checks pass |
| S-T02 | S1–S2 D1, S3–S4 D2, S5–S6 D3 | Eligible for `COMPLETE` |
| S-T03 | S1 D1, S2–S3 D2, S4–S6 D3 | Reject completeness: `1+2+3` pattern forbidden |
| S-T04 | S1–S4 on D1 | Reject completeness: >3/day |
| S-T05 | S2 date before S1 date | Reject occurrence chronology |
| S-T06 | Same staff Trainer and Logistic within S2 | Reject that session pair |
| S-T07 | Different Trainer per session, one Logistic covers two same-day sessions | Valid staffing if no duplicate/identity issue |
| S-T08 | Two different Trainer claims for same activity S2 | Flag conflict; no auto selection |
| S-T09 | Row claims S1+S2+S3 with explicit dates | Expand into three evidence-backed staff-session claims |
| S-T10 | Row claims `session_count=3`, no session IDs/dates | Flag incomplete evidence; do not synthesize session occurrences |
| S-T11 | Only first three occurrences pass | No session batch `COMPLETE`; no eligible credit release |
| S-T12 | All six occurrences covered; report `UNDER_REVIEW` | `COMPLETE` possible, `VALIDATED`/payability blocked |
| S-T13 | Report July 12, resubmitted July 15 **before** July 16 validation | Freeze July 15 cutoff at validation |
| S-T14 | Report validated July 12; later resubmitted July 15 | July 12 cutoff remains frozen; no automatic reversal |
| S-T15 | Work date after frozen report cutoff | Exclude/flag with preserved original and original reason |
| S-T16 | Timesheet submission before claimed work date | Flag; not automatically accepted |
| S-T17 | Two eligible credits week 1, four eligible credits week 4, same staff/policy | Create exactly two USD 25 groups, once; no duplicate on retry |
| S-T18 | Staff has 1 Trainer A-project, 1 Logistic B-project, 1 Trainer C-project, same policy | One USD 25 **eligible group**; budget allocation may block export until approved |
| S-T19 | Staff has two credits policy A + one policy B | Do not pool; no complete group |
| S-T20 | Four eligible credits, one previous 3-credit group | Exactly one leftover unconsumed credit |
| S-T21 | Reimport same file or repeat payment group calculation | No repeated group/obligation; attempts audited |
| S-T22 | Confirm invalidation without human note | Valid decision uses original flag code; audit persists |
| S-T23 | Name spelling variant with no verified exact ID mapping | Propose candidates; no authoritative staff/payee until human confirmation |
| S-T24 | AI attempts policy mutation/retrospective cutoff relaxation | Denied by backend; access/action attempt audited |
| S-T25 | 3-credit group generated but payment batch not approved | No payment export; settlement not assumed |

## 8. Remaining **integration-only** decisions (not permissions for the agent to guess)

The session **eligibility and USD $25/group policy above is closed**. These are adjacent technical/accounting questions needed to finish reliable payment export:

1. **Cross-project budget allocation:** How should one USD 25 group built from credits across several projects/budget lines be attributed? No automatic pro-rata or last-project attribution until NK approves. Keep group in allocation-review state if needed; do not lose it or pay twice.
2. **Policy version compatibility:** When the same policy ID receives a new version, can older unconsumed credits pool with the new version's credits? Keep policy identity, effective version and terms on each credit; do not silently blend changed terms.
3. **Authoritative report version/clock:** External report source file/registry columns, project time zone, and immutable validated-version reference remain source-contract questions.
4. **Source spreadsheet layout:** Real planning and timesheet column paths (including `session_number -> date` lists), role alias seeds and staff mapping fields need source-confirmed mapping, not fabricated sample schemas.
5. **Approved budget line and destination mappings:** Credit/project origin tracking and verified payout identity must be settled before payment export; external financial processing and settlement remain governed by the master specification.

These do not authorize AI policy configuration. Unknown financial allocation and mapping data must block unsafe disbursement, **not** prevent safe ingestion, rule checking or backlog display.

## 9. Deliverable instructions

- **GitHub:** Upload this Markdown file to `docs/policies/session_policy_contract_v1.0.md` in `N9o-Codes/Agent-Timmy` (`main` unless your team is actively using an agreed feature branch).
- **Paired CN handoff:** Also upload `docs/architecture/session_policy_database_delta_v1.0.md`; read both together.
- **Suggested commit title:** `docs(policy): lock session payment and validation contract`
- **Suggested commit description:** `Record NK-approved six-session activity, 3+3 or 2+2+2 scheduling, staffing, frozen report cutoff, cross-role/project staff pooling at USD 25 per 3 credits, human review and backend guards. Document remaining cross-project budget attribution and report-source integration questions; no implementation or testing claimed.`
