# Agent Timmy — Fixed Hours-Based Policy Contract

**Authority:** NK explicit decisions, 2026-11-15.  
**Status:** Approved rates, rounding examples, limit and cap; identified boundary conditions remain blocked pending approval.  
**Scope:** One coordinator across many projects; projects select `SESSION` or `HOURS`. No project-specific policy editor or AI policy mutation.

## 1. Fixed hourly payment rules

| Rule | Fixed interpretation |
| --- | --- |
| Rate | USD 5.00 per *payable whole hour*. |
| Overtime | No overtime multiplier; all accepted hours use USD 5.00/h. |
| Overnight shifts | Allowed across midnight, with no premium; explicit clock-in/out and dates required. |
| Breaks | Not deducted. |
| Rolling 24h limit | At most 16 **actual non-overlapping clocked hours** in any rolling 24h window for a verified person, before rounding. Violations are flagged for authorized review; raw input preserved. |
| Individual shift rounding | Nearest 30 minutes, based on accepted elapsed shift duration after same-role overlap normalization. Examples: 4h10→4h, 4h20→4h30, 4h40→4h30, 4h50→5h. |
| Monthly aggregation | Sum individually rounded, accepted shift durations for one verified staff ID / hours-based project / calendar month; **floor** remaining 30-minute fraction to a full payable hour. |
| Residual | Any unpaid 30-minute fraction expires at month-end; no carry-forward. |
| Monthly cap | Max 120 payable hours / USD 600 for each verified staff ID **per hours-based project** per calendar month; not a blanket cap across all hourly projects. |
| Same person, same role overlap | Count overlapping actual time once; preserve original source rows. Ambiguous project/activity budget attribution requires human review, not silent allocation. |
| Same person, different role overlap | Flag for human decision; do not automatically choose or pay both. |
| Session interactions | No time-overlap checks for session-based inputs; they contain service dates, not clock-in/out. |
| Eligibility/financial authority | Same planning/staff/report-validation/human exact-batch approval and external-settlement gates as session policy. |

Calculations are deterministic, not LLM-produced. Applicant data, source aliases or Qwen output cannot change these constants or authorize payments.

### Example: per-shift rounding then monthly flooring

- Shift 1 = 4h20m -> 4h30m.
- Shift 2 = 4h10m -> 4h00m.
- Monthly sum = 8h30m -> **8 payable hours**, USD **40.00**; remaining 30 minutes expire.
- A month with sixteen approved 8-hour shifts = 128 rounded hours -> **120 payable hours = USD 600**, with eight hours above cap retained as traceable non-payable quantity.
- Two claims for same verified staff, same role/activity/project, 09:00–13:00 and 11:00–15:00 -> union 09:00–15:00 = **six** actual hours, no double counting.
- A cross-midnight 20:00–04:00 shift is eight hours at normal rate if in the same payment month and otherwise eligible.

## 2. Explicitly blocked or unresolved edge cases

1. **Exact half-way rounding tie:** For 4h15m, nearest half-hour has two equally close outcomes. NK examples establish non-tie cases only. Until separately confirmed, deterministic calculation flags `HALF_HOUR_TIE_RULE_UNCONFIRMED`.
2. **Cross-month shift:** Attribution of an overnight shift spanning month-end is not defined. Preserve and flag `CROSS_MONTH_SHIFT_ATTRIBUTION_REQUIRED`. Do not invent which month receives hours or apply a synthetic split.
3. **Overlapping work across different projects or activities:** Staff/role overlap may be deduplicated as actual time, but which project/activity bears it requires confirmed attribution. Flag cross-project or cross-activity allocation.
4. **Different-role overlap:** Human chooses which claims to invalidate/retain. Record original and reviewer decision.
5. **Rolling-limit violation disposition:** Whether an entire offending row is rejected or an explicitly authorized corrected split is permitted requires a human decision; automatic cap/truncation is forbidden.
6. **External report and payment schema:** Trusted external approval, allocation, payment instruction, return-file and settlement adapters remain separate. This pure calculation module cannot assert eligibility.
7. **Historical projects:** Old per-project policy JSON must not be interpreted automatically as the new fixed policy family.

The pure `backend/timmy/fixed_hours_policy.py` computes only *non-authoritative candidate summaries*. It does **not** activate an hourly payment ledger, validate staff identity, read a trusted external report, create instructions or settle transfers. Its own blockers yield `amount_usd=None`; an amount from an unblocked synthetic candidate is still not an export authorization.

## 3. Global coordinator and multi-project source handling — approved target, not implemented by this document

- Exactly **one operating coordinator/admin**, with secure login and audit.
- A conversation can discuss and process **one, several, or all projects** and must not be confined to a single project's workspace.
- One planning workbook may contain **multiple projects** and approved source-issued activity codes; source authority remains with the planning sheet.
- One timesheet workbook may contain rows for **one or many projects**; multiple timesheet workbooks/sources can be supplied together.
- Project identity is resolved for *each source row* from trusted codes/authority; no ambiguous alias guesses, cross-project identity collisions or retroactive mutation.
- A project is created by name, acronym and exactly one fixed policy family. Project families are application-level policy definitions, not user-edited JSON.
- Live display must show **real** chronological workflow steps, source/file/sheet/row references, action/alias resolution, actual backend service or MCP tool calls, graph node names if used, pinned rule IDs, outcomes, pause/review and audit receipt. Never expose hidden model chain-of-thought, fabricate unused MCP calls, or leak secrets/PII in logs.
- Validate workflow aliases, negations and bilingual triggers before adding an evidence-backed inspector.
- Next test sprint: three independent folders each holding `planning.xlsx`, `reporting.xlsx`, `timesheets_session.xlsx`, `timesheets_hours.xlsx`, and `EXPECTED_RESULTS.md`: happy path; mixed discrepancies; boundary/financial controls. External report workbook values are test fixture *claims*, not trusted authority unless approved adapter independently verifies them.
- Until multi-project upload/workflow and trusted reporting adapters are implemented, the app must clearly block and state missing capabilities instead of claiming successful operations.

## 4. Acceptance tests and review

- Pure tests: `PYTHONPATH=backend python -m pytest backend/tests/test_fixed_hours_policy.py -q`.
- Full suite and frontend build before merge: `PYTHONPATH=backend python -m pytest backend/tests -q`, `npm run build --prefix frontend`, `npm test --prefix frontend`.
- Validate the correct migration head and copied populated DB before any schema-changing PR merge/deploy.
- Coordinate with **PR #7** (`feature/fixed-policy-families-mvp`) for removing editable policy UI/API. This contract and the pure hourly candidate module do **not** alter that PR.
- Preserve original audit rows, document evidence, human review and financial authorization boundaries. No production migration or deployment is authorized by this document.
