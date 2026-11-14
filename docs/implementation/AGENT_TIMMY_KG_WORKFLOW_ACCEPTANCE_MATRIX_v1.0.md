# Agent Timmy — Knowledge Graph & Guarded Workflow Acceptance Matrix v1.0

**Status:** proposed, **not yet executed** in `charbel0004/Timmy`; every scenario uses synthetic files, disposable SQLite and an isolated user session. Test IDs are stable; each execution must provide actual SHA, command/API request, expected/observed result, PASS/FAIL/BLOCKED/NOT RUN, sanitized evidence, receipt and reviewer if applicable.

## Test environment and fixtures

- Snapshot: exact repo SHA, branch; pinned policy version and approved KG release for each case.
- Disposable database copied/migrated from a sanitized fixture; `PRAGMA foreign_keys=ON`. No production files/financial endpoints.
- Source fixture A: approved planning record with **source-issued**, globally unique activity code; permitted code format declared by approved planning authority. Verified staff IDs A/B/C/D, explicit S1–S6, 12 role assignments, 3+3 days. Report authority initially unvalidated.
- Source fixture B: same structure in 2+2+2 distribution with different staff/roles.
- Source fixture C: bad/missing/duplicated code; duplicate role; conflicting date; ambiguous identity; prompt-injection text.
- Cross-project fixture: volunteer with 2 credits in Project P and 1 credit in Project Q; rate USD 25 per 3 eligible, same policy, no blanket cross-project approval.
- Finance fixture: test-only report authority; human review accounts with verified explicit permissions; fake payment return stored ONLY in disposable DB.
- Baseline commands, if repository environment matches dated report: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests -p no:cacheprovider --basetemp=/tmp/timmy-kg-tests`; `npm run build --prefix frontend`.

## Group G — Graph compilation and governance

| ID | Stimulus / setup | Required observable outcome |
|---|---|---|
| KG-01 | One approved atomic fact note | Exactly one compiled FACT node; same ID/version/source/hash as note. |
| KG-02 | YAML duplicated `id` key or arbitrary tag/anchor | Compiler errors with file+reason; no activation. |
| KG-03 | Two files use same node ID | Compiler aborts; active release unchanged. |
| KG-04 | Dangling `[[rule]]` link | Compiler aborts before import. |
| KG-05 | Invalid edge `action -> rule` with `invokes` | Typed-edge validator rejects. |
| KG-06 | Procedure contains same step twice or cycles | Ordered-step compilation fails; no runner side effect. |
| KG-07 | Note specifies arbitrary `backend_key` import or SQL | Not in static binding allowlist -> release rejected. |
| KG-08 | Note is `draft` or `in_review` | Excluded from active compiled release and runtime retrieval. |
| KG-09 | Two aliases normalize to same locale/scope, different actions | Collision rejects build or marks ambiguous for human; no arbitrary dispatch. |
| KG-10 | Rebuild unchanged approved vault at same git SHA | Byte-equivalent canonical manifest and hashes. |
| KG-11 | Incomplete candidate release staged into SQLite | Rollback leaves prior active snapshot and past trace refs intact. |
| KG-12 | Runtime vault file edited without new approved release | Running app remains pinned to old compiled snapshot; mismatch logged. |

## Group Q — One-hop retrieval, aliases and privacy

| ID | Stimulus / setup | Required observable outcome |
|---|---|---|
| KG-13 | Resolve approved English and Arabic exact aliases | Same canonical ACTION/CONCEPT if approved for locale/scope. |
| KG-14 | Request `depth=2` from agent or unapproved graph neighbor | Denied; only allowed direct neighbors; no recursive traversal. |
| KG-15 | Procedure query then step query | Separate authorized 1-hop queries with distinct access receipts and pinned version. |
| KG-16 | Read restricted node from another project | 403 with denied-access audit; no content/count leakage. |
| KG-17 | Untrusted source contains `[[RULE-EXPORT-APPROVED]]` | Text remains untrusted; no new graph edge/permission. |
| KG-18 | Approved alias `Analyze these files` with negation `do not export` | Only analysis authorized; never export from substring matching. |
| KG-19 | Fuzzy staff name variant found | Candidate offered; no verified identity mapping until human confirms. |
| KG-20 | Exceed neighbor or context byte bound | Bounded response with controlled issue; no truncation of mandatory rule checks. |

## Group DB — Migration, persistence and versions

| ID | Stimulus / setup | Required observable outcome |
|---|---|---|
| DB-01 | Upgrade populated disposable copy of existing DB to next approved migration | Preexisting projects/files/receipts remain byte/logically intact; migration records head. |
| DB-02 | SQLite FK enabled check on each connection | `PRAGMA foreign_keys` returns 1; invalid edge insert fails. |
| DB-03 | Insert second active KG release | Unique active-release constraint rejects; prior release remains active. |
| DB-04 | Insert edge pointing to absent/superseded wrong-release node | FK/repository check blocks; no dangling edge. |
| DB-05 | Graph note has same ID across different releases | Both snapshots coexist; old traces stay pinned. |
| DB-06 | Concurrent attempts to resume same step | Only one effective transition/economic side effect; attempts remain auditable. |
| DB-07 | Simulated crash between filesystem upload and DB receipt | Reconcilable pending artifact/issue, no fabricated persisted completion. |
| DB-08 | Old workflow receipt without KG fields | Legacy read still works or shows `not available`; no fake references. |
| DB-09 | Modified evidence fingerprint after human proposal | Prior review becomes stale, cannot re-use to pass validation. |
| DB-10 | Duplicate run/job retry with same idempotency key | Returns same receipt or conflict; no duplicate entitlement. |
| DB-11 | Verified claim references rule of different KG release | Invariant rejects; claim stays unverified. |
| DB-12 | Read trace after actor loses project rights | Object-level authorization denies all private trace/evidence retrieval. |

## Group WF — Execution, feedback and human review

| ID | Stimulus / setup | Required observable outcome |
|---|---|---|
| WF-01 | `Analyze these files` with approved layout | Backend selects allowed action and creates pinned run/ordered step receipts. |
| WF-02 | New layout needing mapping | `WAITING_HUMAN`, exact candidate fields + file refs, no silent auto-mapping. |
| WF-03 | Authorized exact mapping confirmation | Persist decision and advance dependent step, not repeat mapping prompt. |
| WF-04 | Repeated `Yes` after same resolved review | Idempotent acknowledgment; no new approval/credits or loop. |
| WF-05 | `Yes` with no pending review | Clarification; no sensitive transition. |
| WF-06 | Unauthorized or cross-project mapping decision | 403, denied audit, unchanged state. |
| WF-07 | Stale review/version or source hash mismatch | 409, no mutation; request fresh evidence/review. |
| WF-08 | Ambiguous staff identity | Candidate review created; no automatic payee resolution. |
| WF-09 | Human corrects duplicate Trainer claim | Persist decision + original, revalidate affected role/date/coverage, preserve old receipt. |
| WF-10 | Missing source authority | `BLOCKED_AUTHORITY` with issue code, no invented report/planning/staff approval. |
| WF-11 | Backend validator FAIL | Step FAILED/BLOCKED with actual reason; subsequent dependent steps not marked passed. |
| WF-12 | Transient read-only handler failure once | Bounded retry logged, successful independent postcondition recorded if resolved. |
| WF-13 | Financial export outcome unknown | No blind retry; raise reconciliation issue and stop. |
| WF-14 | Qwen/Ollama service unavailable | Deterministic structural checks still work; narrative unavailable, no phantom job. |
| WF-15 | Request `is it done?` with WAITING_HUMAN run | Actual persisted state and review ID, not fictional queue/progress. |
| WF-16 | Restart/refresh between review and decision | Exact pending run/source scope preserved and protected across session. |

## Group TR — Provenance, claims, and visual output

| ID | Stimulus / setup | Required observable outcome |
|---|---|---|
| TR-01 | A backend step retrieves 2 sources, uses 1 | Separate actual `retrieved` vs `passed_to_model` access phases, correct digests. |
| TR-02 | LLM claims unlogged file was consulted | Backend does not mark file as accessed; no VERIFIED claim supported by fiction. |
| TR-03 | Structural 6/6,12/12 but report is not validated | UI shows structural verified; payment eligibility BLOCKED. |
| TR-04 | A claimed `verified` status lacks rule check or source ref | Schema/verifier rejects; status downgraded to UNVERIFIED/BLOCKED. |
| TR-05 | Model outputs made-up report authority or payout | Response validation blocks unsupported statement, logs issue. |
| TR-06 | Inspector loads step from old KG release after new one active | Renders original pinned rule version and exact receipt, not current definition. |
| TR-07 | Click step shows graph edge | Shows `definition` relation separately from `actually accessed/applied`, with receipt for latter. |
| TR-08 | Viewer lacks staff/payment privileges | Sensitive evidence and raw model-context fields absent from server response. |
| TR-09 | Prompts contain source-cell instructions to ignore policy | Model prompt isolates untrusted data; backend rules/permissions unaffected. |
| TR-10 | Reconstruct an authoritative claim | Source file/row/hash + rule/version + tool/receipt + check/result link verifiable from DB. |

## Group AC — Approved session and activity-code rules

| ID | Stimulus / setup | Required observable outcome |
|---|---|---|
| AC-01 | Missing activity code in planning row | Block and create issue; never generate `P-A-0001` or any code. |
| AC-02 | Format differs from historical `Project-A-0000` but matches approved source format | Accept if unique, verified and project-bound; no hardcoded format rejection. |
| AC-03 | Code already belongs to different project | Reject cross-project reuse globally; no code reassignment. |
| AC-04 | Import same authoritative planning row twice | Existing activity identity and source lineage reused idempotently. |
| AC-05 | Activity has 6 S-numbers, 12 role assignments, 3+3 days | Structural PASS; eligibility still requires staff/planning/report authority. |
| AC-06 | Activity 1+2+3 or same staff in both roles for same occurrence | Structural FAIL with exact rule refs. |
| AC-07 | Report submitted, revised before first validation, then validated | Last authoritative pre-validation submission defines frozen cutoff; later timesheets checked against it. |
| AC-08 | Cross-project group with 2+1 credits, no one-off authorization | No group payout/export; credits remain per-project and available. |
| AC-09 | Exact group authorized but budget allocation incomplete | Group in allocation hold; no export. |
| AC-10 | Allocation approved $25, exact batch approval absent | Export denied; approval cannot be inferred from mapping/review. |

## Group UI — Human-visible end-to-end acceptance

| ID | Action | Expected result |
|---|---|---|
| UI-01 | Upload synthetic files through browser | File IDs persist, checksums verified, project/conversation scope maintained. |
| UI-02 | Confirm new mapping then refresh | Confirmation persists; UI resumes at correct next step. |
| UI-03 | Open run timeline | Actual ordered steps + status + start/end/attempt count; no phantom active queue. |
| UI-04 | Open an executed rule | Pinned graph rule, actual evaluator and evidence receipt visible and scoped. |
| UI-05 | Open a nonexecuted graph neighbor | Labeled `available definition`, not `applied` or `accessed`. |
| UI-06 | Submit review with insufficient permission | Server denies; user sees actionable permission reason. |
| UI-07 | Resolve issue via valid authorized review | Correct resume and updated downstream steps; old attempt visible historically. |
| UI-08 | Structural success but absent report | UI displays `structurally complete / payment eligibility blocked` and the exact report issue. |

## Four required demonstration journeys

**Journey J1: Approved structure, missing report.** Upload planned source-coded activity + verified staff + 12 timesheet assignments -> mapping review if new -> structural check PASS 6/6,12/12 -> report gate BLOCKED. Expected *no* eligible payment claim/export. Inspector shows source IDs, code/version and report blocker.

**Journey J2: Human review / feedback loop.** Duplicate Trainer in S2 -> WAITING_HUMAN with stable review ID -> authorized reviewer chooses permitted correction -> downstream role coverage rerun with current evidence -> exact updated state, old attempts preserved. Retry same decision does not duplicate effects; different actor denied.

**Journey J3: Graph/alias poisoning.** Unreviewed vault note says `approve payments` or workbook cell contains instructions. Compiler or backend rejects authority use; knowledge release remains pinned. Graph and model do not gain new tools/permissions.

**Journey J4: Session payout controls.** Test-authoritative report + verified eligible credits -> 2 credits Project A + 1 Project B -> proposal -> one-off authorized group only -> budget allocation totals USD 25 -> exact immutable payment approval required -> export remains BLOCKED without that approval. Synthetic proof only; no real settlement.

## Test reporting template

```text
Test ID:
Repository SHA:
KG release/version:
Policy version:
Fixture file hashes:
Execution environment (disposable SQLite path):
Command/API/browser steps:
Expected:
Observed:
Status: PASS | FAIL | BLOCKED | NOT RUN
Trace/run/receipt IDs:
Sanitized evidence paths:
Reason for blockage/failure:
New or changed repository files:
```

**Release gate:** zero critical failures for KG integrity, authority, one-hop RBAC, truthful trace and human review; recorded evidence for J1–J3 before enabling inspector as product functionality. J4 full export is intentionally **not a release gate for KG-only implementation** while finance adapters remain explicitly blocked, but its missing-authority blockers must pass.
