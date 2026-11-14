# Agent Timmy — Session Policy Database Implementation Delta

**Version:** 1.0  
**Date:** 2026-11-14  
**Audience:** CN (database implementation owner), NK (business/financial review)  
**Status:** Required database design handoff for approved session-policy business rules. Recommended physical details need CN/NK technical review; no migrations run.  
**Intended GitHub path:** `docs/architecture/session_policy_database_delta_v1.0.md`  
**Read together with:** `docs/policies/session_policy_contract_v1.0.md` and `docs/Agent_Timmy_Database_Implementation_Specification_v1.0.md`.

## 1. What changed; precedence

The base DB specification remains authoritative for SQLite + SQLAlchemy + Alembic, private file storage, source provenance, audits, human-approved payment batches, payment-return reconciliation and chronological operational reports. **This delta supersedes incompatible earlier proposed fields/relationships** for the session-policy domain. Do not silently reconcile these changes by preserving outdated per-project/per-role pay aggregation.

| Previous incomplete or illustrative assumption | NK-approved updated rule | DB implication |
|---|---|---|
| Sessions could be represented only by aggregate quantities | Six identified S1–S6; explicit `session_number -> date` even when one row covers several | One occurrence table and **one claim/assignment per claimed session** with source row lineage |
| One distinct date per session implied by example | Exactly `3+3` or `2+2+2` on 2 or 3 distinct dates | Allow date repeats; enforce pattern across whole activity |
| Unresolved role cardinality | Exactly 1 Trainer + 1 Logistic accepted per occurrence; different verified staff | Role/occurrence uniqueness for **accepted** assignments; preserve conflicting raw claims |
| Entitlement proposed as `staff + project + activity + role + policy version` | **Group** for one staff across projects, activities, weeks, roles, dates; same session-policy identity only | Separate **source credits** from **three-credit payment groups**, with group→credit links; group may have many project origins |
| Demo rates unverified | USD **25.00 per 3-unit group** for both Trainer and Logistic, pooled | Persist human-approved locked policy version and exact USD amount; no model edits |
| External report status only | One report per activity, versioned submissions, frozen cutoff on **first authoritative validation** | Store report submission versions, validation event and frozen cutoff; no automatic retroactive extension |
| Planned work date and timesheet upload timing ambiguous | Work date within plan; submission date ≥ all claimed work dates | Separate original submission datetime/date from actual work dates; review as needed |
| Exception invalidation might require new human note | Existing flag reason sufficient; additional explanation optional | Invalidation decision FK to issue, optional note, event/audit trail |

**Potential inconsistency to fix in base spec:** its invariant that every **entitlement** belongs to the same project as its source activity is too narrow for an aggregate $25 group containing credits from multiple projects. **Each source credit** remains project-scoped, but a **payment group** has one staff/policy identity and **many source-credit/project references**. Accounting allocations are a separate child relationship; the database must not falsely assign the entire group to a single source project.

## 2. Minimal relational design (proposed physical mapping)

Retain base tables: `projects`, `staff`, `staff_source_mappings`, `payment_destinations`, `policy_versions`, `planned_activities`, `stored_files`, `import_runs`, `source_rows`, `work_entries`, `timesheet_batches`, `validation_issues`, `issue_events`, `audit_events`, `audit_accesses`, `payment_batches`, `payment_instructions`, `payment_approvals`, `external_payment_records`, `settlement_allocations`, `operational_reports`.

Modify/add these structures; names are proposed. CN may adapt naming if keys/constraints/behaviors remain equivalent, recording a schema deviation note.

### 2.1 `session_policy_definitions` or equivalent protected parent policy record

| Field | Purpose |
|---|---|
| `id` | Stable **policy identity** used to partition pooling |
| `policy_family` | `session` |
| `approved_config_version_id` | Approved immutable policy-version reference |
| `required_session_count` | `6` |
| `required_role_codes` | Trainer + Logistic, enforced by protected code/config |
| `allowed_day_distributions` | `[[3,3], [2,2,2]]` |
| `group_size` | `3` |
| `group_amount_decimal` | exact `25.00` |
| `currency_code` | `USD` |
| `status`, `approved_by`, `approved_at` | Activation/security evidence |

**Alternative:** Reuse the existing `policy_versions` table but add a **stable shared policy identity** referenced by all participating projects. Do **not** make `project_id` the policy pool's implicit partition. Do **not** make session rate editable from the AI adapter. If project-policy assignments refer to different policy IDs, pooling across those IDs is forbidden even if rates match. Retain the version of configuration applied to each credit.

### 2.2 `activity_occurrences` (extend)

| Field | Purpose / constraint |
|---|---|
| `id` | Stable unique occurrence ID |
| `planned_activity_id` | FK to external-approved planning activity |
| `session_number` | Integer `1..6`, unique per activity |
| `work_date` | Explicit local service date |
| `planning_evidence_ref` | Source row/reference for expected schedule where available |

**Integrity:** exactly six occurrences for `COMPLETE`; sequence 1–6; whole-activity date pattern `3+3` or `2+2+2`, nondecreasing. SQLite can't enforce all cross-row/count constraints with a simple CHECK; enforce in deterministic domain service within a transaction, with DB uniqueness/check supporting it. Planned activity codes stay project-scoped and are never invented by the agent.

### 2.3 `session_role_claims` (recommended new staging table) and `session_assignments` (accepted)

**Claims** preserve the many-to-many shape between `source_rows` and occurrences, including duplicates or unresolved entries. Proposed columns:

- `id`, `source_row_id`, `staff_id?`, `planned_activity_id?`, `occurrence_id?`, `claimed_session_number?`, `claimed_work_date?`, `claimed_role_raw`, `canonical_role_code?`, `normalized_status`, `validation_issue_id?`, `created_at`.

**Accepted assignments** represent no more than one Trainer and one Logistic per occurrence:

- `id`, `occurrence_id`, `role_code`, `staff_id`, `accepted_claim_id`, `accepted_at`, `validation_state`, `audit_event_id`.
- Unique accepted `(occurrence_id, role_code)`; two accepted records for the same session must have **different `staff_id`**. Backend checks cross-role staff inequality atomically.
- Immutable source claim retained; manual correction/invalidation creates a recorded revision/event rather than overwriting original evidence.

**If CN keeps only `work_entries` instead of adding tables:** each work entry must represent one source-backed session/role claim, a separate accepted-assignment concept/state is required, and DB uniqueness must apply only to accepted claims (not all raw conflict records). Preserve source-to-many-session relationships.

### 2.4 `activity_report_submissions` + `activity_report_validation` (or equivalent)

One authoritative report identity per activity, but multiple versions of submissions before validation.

| Data | Requirement |
|---|---|
| `activity_report_id` | Project-scoped FK/unique activity-to-report association |
| `submission_version_id` | Immutable external version ID or deterministic source version reference |
| `submitted_at`, `submitted_local_date` | Authoritative submission timestamp/date and derived local date |
| `evidence_file_id`, `evidence_row_id` | Restricted source lineage |
| `externally_validated_at`, `validation_evidence_ref` | Authoritative external validation evidence |
| `validated_submission_version_id` | Explicit version actually validated |
| `frozen_work_cutoff_date` | Candidate report date frozen at first authoritative validation |
| `cutoff_locked_at`, `cutoff_locked_by_event_id` | Idempotent freeze/audit event |

**State rule:** before validation, incoming official resubmissions may change the *candidate* cutoff. **At first validation**, freeze the submitted date belonging to the validated version (e.g., July 15 after a July 12 version was resubmitted before validation). After freeze, no newer report auto-increases cutoff or reverses previously invalidated claims. Ambiguous external identity/version order → flag and require human/source confirmation. The app may **read** authoritative external statuses, not edit/approve them.

**Validation sequence:** freeze cutoff → re-evaluate all included work-date claims → exclude/flag late claims → recompute role/date coverage → transition to `VALIDATED` only if the complete six-session activity remains fully valid. A report is not sufficient to override missing work evidence.

### 2.5 `session_eligible_credits` (new, recommended)

This separates **individual verified service credits** from cross-project payment group units.

| Field | Purpose |
|---|---|
| `id` | Stable single credit identity (never reused) |
| `staff_id` | Verified identity (pool partition) |
| `policy_id` | Stable shared session policy identity (pool partition) |
| `source_policy_version_id` | Immutable terms used to validate originating work |
| `accepted_assignment_id` | Unique FK to one accepted role assignment |
| `planned_activity_id` | FK activity; project recovered from activity FK |
| `project_id` | Optional explicit FK for efficient origin/accounting check; must equal activity's project |
| `role_code` | Original role, used for provenance, **not** payment-group partition |
| `session_number`, `work_date` | Evidence snapshot, not authority over original |
| `report_validation_id` | FK to authoritative report validation/frozen cutoff |
| `eligibility_state`, `eligible_at`, `excluded_at?` | Lifecycle/evidence |

**Uniqueness:** one economic session credit per accepted assignment. Never create a credit before all activity `COMPLETE` and report `VALIDATED` rules have passed. A source correction after credit creation must trigger controlled adjustment/reconciliation, not silent deletion of approved financial history.

### 2.6 `session_payment_groups` and `session_payment_group_credits` (new, recommended)

One staff may earn a USD 25 group from any 3 eligible credits with the same `policy_id`, even when they originate from different roles, activities, projects, dates or weeks.

`session_payment_groups`:

- `id`, `staff_id`, `policy_id`, `policy_config_version_id`, `currency_code='USD'`, `amount_decimal='25.00'`, `group_sequence`, `group_state`, `created_at`, `eligible_at`, `origin_key`, `accounting_allocation_state`.
- Group identity is stable and tied to one eventual entitlement; multiple payment attempts may reference the same underlying obligation, never duplicate it.

`session_payment_group_credits`:

- `payment_group_id`, `credit_id`.
- **Unique `credit_id` across all group links**; exactly three distinct credit IDs required per finalized group.
- Transactional guards ensure all three credits belong to the group `staff_id`, same `policy_id`, report-validated and unconsumed.

**Remainder representation:** Credits with no group link remain available across payment events/weeks/activities/projects/roles under same policy. Do not issue partial USD amounts from one or two credits.

**Determinism:** Choose one stable source-credit ordering and unique group origin key, save the consumed-credit list, use SQLite single-writer transactions/idempotency guards; retries and concurrent workers must yield same finalized groups. Do not recompute/reassign an already approved/exported group because a later import changes available credit order.

**Version boundary guard:** Pool only when the policy identity and approved terms are compatible. A later version that changes rate/grouping or other payout semantics creates an unresolved compatibility issue unless NK explicitly approves transition rules; do not silently mix.

### 2.7 Payment entitlement and accounting allocation bridge

The existing `entitlements` table may serve as one record per `session_payment_group` or group may point to one entitlement; ensure **one-to-one uniqueness** and exact `USD 25.00` value. Preserve all three credited source assignments and their owning projects.

**Cross-project budget challenge (OPEN FIN-ALLOC-01):** One group can have three credits from distinct projects/budget lines. A single `entitlements.project_id` or `entitlements.budget_allocation_id` is **not enough to express such an obligation correctly**.

Proposed bridge:

`payment_group_accounting_allocations`: `id`, `payment_group_id`, `project_id`, `budget_line_id`, `amount_decimal`, `currency_code`, `allocation_rule_version`, `authorized_by`, `authorized_at`, `audit_event_id`.

- Child amounts must sum **exactly USD 25.00** before export, never double-count. How to distribute $25 for splits like 1/1/1 is a **financial rule NK has not approved**. Do not invent a per-credit or proportional method; keep group `ALLOCATION_REVIEW_REQUIRED` when attribution is ambiguous.
- Source credits remain eligible and grouped even while export is blocked for allocation review. Do not silently ungroup or lose the credits.
- Separate from `settlement_allocations` (which allocate externally confirmed settled funds). Avoid confusing budget attribution with proof of payment.
- Keep original entitlement stable if instructed payment later fails; carry-forward outstanding remains tied to same group/entitlement ID.

### 2.8 Invalidation/review and audit enhancements

Existing `validation_issues` + `issue_events` + `audit_events`/`audit_accesses` should carry:

- One machine-assigned `issue_code`, `source_row_id`, `session_claim_id?`, `planned_activity_id?`, `rule_id`, original/accepted values, evidence, severity and status.
- Human decision with `decision_kind` (`invalidate` / `authorize_allowed_exception` / `request_correction`), `reviewed_by`, `reviewed_at`, `original_flag_issue_id`, `optional_reason_text NULL`, `audit_event_id`.
- On invalidation `effective_reason_code = original_flag.issue_code` when no new free-text reason is supplied. Never require an extra narrative reason for the same issue.
- Historical issue-event sequence captures first detection, attempts, who accessed which restricted resources, mapping proposals, external report versions/validation and eventual outcome.
- All accepted alias changes / fuzzy name candidate confirmations are auditable; confirmed mapping is stored as a verified mapping record for future reuse; fuzzy candidates themselves are **not** accepted staff IDs.

## 3. Validation execution order (service-level, not LLM authority)

1. **Safe ingestion:** extension/MIME/magic, size, bounds, content validation; private immutable source bytes and row lineage; disallow unapproved file types and embedded document commands.
2. **Normalize candidate data:** approved field aliases, Unicode/Arabic digits, explicit S-number/date pairs; preserve raw source. Unknown columns/roles => confirm mapping; no date invention.
3. **Resolve identity:** verified ID mapping or authorized name-alias confirmation; redact actual names in all AI-facing payloads. No fuzzy self-approval.
4. **Planning checks:** approved activity code, project, effective policy identity, work-date plan window and exception decisions. Validate `timesheet_submitted_date >= each work_date`.
5. **Occurrence checks:** 1..6, allowed 3+3 / 2+2+2, chronology, exactly one accepted Trainer and Logistic per occurrence, distinct staff within same occurrence, no duplicate claims accepted.
6. **Activity `COMPLETE`:** all six occurrences and twelve required accepted role-assignment slots valid, no blocking unresolved issues.
7. **Report reconciliation:** one authoritative activity report; preserve each submission version; only on independent external `VALIDATED` freeze validated submission's cutoff and exclude post-cutoff work claims. Recompute completeness and fail closed on mismatches; no automatic cutoff reversal.
8. **Eligible credits:** issue exactly one verified session credit per accepted assignment **after** all gates. Preserve project, activity, role, session and report provenance.
9. **Pooling:** group any **three** available credits for same staff/policy, across project/activity/role/date/week; amount exact USD 25.00; retain 1–2 remainder units.
10. **Accounting bridge:** cross-project attribution must be approved before payment export. No AI guessed allocation.
11. **Financial authorization/export:** immutable grouped obligations → verified destination → exact human approved batch → authorized export; later external processing/reconciliation/settlement remain separate.
12. **Auditing/reporting:** record action trigger, resources accessed, rule applied, before/after state and outcome; chronological issue histories used for AI narrative with verified event citations.

On failure: stop affected advancement, preserve evidence, create/reconcile issue, allow only safe idempotent bounded retries or authorized human review. Do not rerun financial side effects blindly.

## 4. Checks and test cases CN should add — **not run**

| Test | Result required |
|---|---|
| DB-S01 | Six occurrences S1–S6 unique per activity; duplicate S-number rejected |
| DB-S02 | Accepted `(occurrence,role)` unique; conflicting raw claims still stored |
| DB-S03 | Trainer and Logistic for same occurrence cannot be same staff |
| DB-S04 | Valid `3+3` and `2+2+2`; invalid `1+2+3`, `4+2`, `6` on one day |
| DB-S05 | One source row expanded into several occurrence claims, retaining row provenance |
| DB-S06 | No session credits until entire activity COMPLETE plus report VALIDATED and cutoff pass |
| DB-S07 | Report resubmitted before validation uses validated version's later cutoff; report resubmitted after validation cannot auto-extend frozen cutoff |
| DB-S08 | Work date after frozen cutoff invalidated; pre-validation work preserved/staged, no premature final cutoff exclusion |
| DB-S09 | Planned date out of range flag review; submission date before work date flagged |
| DB-S10 | Exactly three validated credits → one USD25 group; 2 → 0; 4 → 1 with 1 remainder; 6 → 2 |
| DB-S11 | Pool same staff/policy credits across projects and **roles**; never across different policies |
| DB-S12 | One credit cannot link to two groups; repeated import/group calculation does not double count |
| DB-S13 | Human invalidation uses original issue reason with optional free-text detail |
| DB-S14 | Cross-project group retains each project/budget lineage; no export with unapproved cost attribution |
| DB-S15 | Wrong permission, prompt-injection attempt or AI policy-update request denied, audited |
| DB-S16 | Post-settlement retry creates no new entitlement; pending outcome never auto retried or deemed settled |
| DB-S17 | Fake name-spelling variants require human confirmation; approved aliases subsequently reused via verified mapping |
| DB-S18 | Source-data corruption, unexpected file types and extra fields flagged with no silent truncation/AI side effects |

These are proposed acceptance test cases, not evidence of successful tests. CN should return migration IDs, schema diff, code-level invariant enforcement, executed test commands and actual pass/fail results to NK.

## 5. CN handoff priorities / implementation notes

**First:** Confirm CN's current Alembic/models against this delta before building financial calculations, especially how `policy_versions` is project-scoped, how a group spans multiple projects, and whether `work_entries` can represent individual S-number evidence. Preserve compatibility with CN's already-started work; choose forward migrations, not destructive resets.

**Then:** Model occurrence+accepted assignment, report version/cutoff and source credits. Add group/credit links and budget allocation bridge before activation of authoritative financial flows. Use application transactions to enforce cross-row constraints and frozen event invariants; apply DB FKs, unique and CHECK constraints wherever meaningful. Protect audit writes as part of privileged transitions.

**No implementation claim:** Neither this handoff nor the test table indicates the database, migrations, UI integration or financial system has been implemented/verified. CN remains the code owner.

## 6. Unresolved integration decisions requiring NK before payment export

- `FIN-ALLOC-01`: How to attribute a USD25 pooled group when credits originate from more than one project or budget line. The grouping itself is fully approved; allocation to budgets is **not**.
- `FIN-VERSION-01`: Pooling credits across a **new version of the same policy ID** if terms differ. Do not mix changed rates or grouping semantics without approval.
- `SRC-REPORT-01`: Which authoritative external report submission version and validation evidence fields identify the version validated and the relevant project-local date/time zone.
- `SRC-FILES-01`: Source-real planning and timesheet columns for S-number/date pairs and staff IDs; no assumed real column schema.

These are **integration/accounting questions**, not grounds for reopening the approved six-session or USD 25/group policy. Unanswered high-risk fields must produce explicit review-block states rather than invented defaults.

## 7. Delivery instructions

- **GitHub:** Upload this file to `docs/architecture/session_policy_database_delta_v1.0.md` in `N9o-Codes/Agent-Timmy` (`main` or team's agreed branch).
- **Paired contract:** Also upload `docs/policies/session_policy_contract_v1.0.md`.
- **Suggested commit title:** `docs(policy): lock session payment and validation contract`
- **Suggested commit description:** `Add approved session policy and CN database delta: six occurrences with exact staffing and valid day patterns, versioned external report cutoff, cross-role/project per-staff payment grouping at USD25/three, leftover credits, provenance, audit, and transactional anti-duplication. Flag open cross-project budget allocation; no code or tests claimed.`
