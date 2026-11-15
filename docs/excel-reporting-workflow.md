# Shared-chat Excel reporting and guarded payment preparation

The official reporting process exports an Excel register. An administrator
explicitly designates its name and project scopes. A coordinator reviews its
column mapping and declares each original an official export. This establishes
**coordinator-declared provenance, not independent reporting-team authentication**.
SHA-256 verifies stored bytes; it does not authenticate who issued them.

The original file, upload time, sheet/physical rows, mapping, normalized report
values and status history are retained. Unknown projects, ambiguous mappings,
unknown statuses, missing submission or validation evidence, duplicate versions,
contradictory statuses and changed accepted history stop the affected evidence
from establishing eligibility. NOT_SUBMITTED, AWAITING_VALIDATION, VALIDATED,
REJECTED and REQUIRES_CORRECTION are preserved as register states; Timmy never
approves or edits the source report status.

The first accepted validation freezes the submission date of that validated
version in Asia/Beirut. An initial export is ordered by validation event time,
not worksheet order; tied first validations require review. Later versions never
extend a frozen cutoff. Historical conflicts remain in append-only evaluation
receipts and block financial use. Repeated identical bytes/mapping confirmations
are idempotent; reinterpreting an already confirmed original is rejected.

## Workflow and human checkpoints

1. Upload planning, report and timesheet workbooks in the shared chat. Project
   acronyms/activity codes determine scopes. No per-project trigger is needed.
2. Request processing, or processing plus payment preparation. The latter selects
   the full weekly goal. Analyze remains intake-only.
3. Review unknown column mappings once for all matched projects. Exact previously
   confirmed formats can be reused. Source dates are normalized as candidates;
   originals are not rewritten. Shared staff references are retained. HOURS and
   reports have distinct schemas, including the supplied Arabic clock headers.
4. If absent, an administrator approves the bounded planning source-code format
   using an original example and evidence reference. Codes are never generated.
5. Declare the report export from the approved register in the chat panel. The
   recorded assurance remains coordinator-declared. A VALIDATED row additionally
   needs identifiable project/activity/report/version, consistent timestamps and
   validation evidence. Missing activities must first be registered from planning.
6. Authorized humans review planning and staff evidence in the linked saved
   structural validation. Upload labels alone grant no approval. Reviews and
   register/mapping confirmations automatically resume the original goal for the
   same authenticated, authorized conversation owner.
7. Deterministic session/hour rules run; unresolved source, policy, planning-window,
   report-cutoff or overlap/rounding findings block payment preparation. No
   rule-authorized correction is invented. Original findings remain reviewable.
8. A payment draft is an immutable calculation/source/review snapshot. Session
   groups stay within their project; hourly months retain the fixed deterministic
   rounding/cap/rolling rules. Dates outside the approved plan or frozen report
   cutoff, policy/source-type mismatches and missing authority cannot be skipped
   by directly requesting preparation.
9. An explicitly authorized human verifies payee/allocation references and their
   evidence; this creates a new immutable snapshot. Another exact approval action
   must bind the final hash. Source scope, report authority, review decisions and
   snapshot integrity are rechecked. Unique credit/month reservations prevent a
   second approval consuming the same units. Monthly amendments require review,
   not automatic incremental payments.
10. Download only the approved exact CSV for manual sending. Export verifies the
    approval hash and current evidence again, escapes spreadsheet formula strings,
    and records the file digest. It sends no payment and establishes no settlement.

`payments.allocate` and `payments.approve` are distinct scoped grants. No reserved
role, including administrator, receives them automatically. An administrator
must explicitly assign them through existing IAM. Planning/staff review grants
also retain their existing separate checks. This implementation intentionally
keeps drafts actor-private rather than exposing private-chat evidence to another
project member. Production approval records are never synthesized by tests.

## Storage, endpoints and rollout

Migration 0020 adds reporting source designations, immutable confirmed imports,
append-only decision snapshots, immutable payment drafts, exact approvals,
unique credit reservations and export digests. Existing source/financial rows
are preserved. Deploy through the reviewed 0019 → 0020 blob-pinned additive
migration path after CI and compatibility checks. Roll back application code
while leaving expanded tables in place; never restore a stale database over
live writes. Do not downgrade after financial approvals without an operator
retention/reconciliation plan.

New API groups use existing session cookies, CSRF, current permissions and scope:
`/api/reporting-register` (designation, candidates, confirmation),
`/api/global-mappings` (one global mapping review and approved code contracts),
`/api/workflow-payments` (drafts, allocations, exact approval, file export).
`/api/workflows/definitions` describes the actual prerequisites and completion
paths. No raw confidential prompt or hidden model reasoning is introduced.

Tests copy the three delivered synthetic Excel suites unchanged into
`backend/tests/fixtures/excel_acceptance`. A deterministic fixture export uses
the same register upload/confirmation/evaluation boundary. The happy path checks
USD 100 SESSION plus USD 160 HOURS, human gates and inert file-only exports.
Mixed/boundary suites preserve findings and never auto-approve financial records.
Additional tests cover chronology, missing/rejected/unvalidated evidence,
conflicting history, idempotence, RBAC, exact hashes and stale-source rejection.

External bank settlement/reconciliation authority is unchanged. A report register
is not a payment-return register and cannot mark obligations settled. Those
legacy reconciliation adapters remain explicitly gated pending an approved
finance-return contract; they are not represented as completed by this work.

## Automatic high-confidence header mapping

The agent classifies each sheet as planning, report, claim, hourly claim, staff
directory or project list from its own header signature. When the document type
is identified by distinctive headers (or an exact, unique required-header fit),
every required column is recognized exactly once and no field matches twice, the
mapping is applied automatically and the conversation continues without asking.
Only ambiguous, duplicated, missing or unsupported header mappings are presented
for human confirmation. Automatic matches are audited
(`global_mapping_auto_confirmed`) and remain correctable by an authorized human;
a correction re-records the mapping before any calculation uses it.
