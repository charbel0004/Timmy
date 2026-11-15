# Agent Timmy — NK scope correction (2026-11-15)

**Authority:** explicit NK instruction; supersedes older per-project policy-configuration and compartmentalized-workspace proposals.  
**Status:** Approved product direction; implementation phases tracked separately. This document does NOT establish an approved hours-based calculation contract.

## Fixed policy choice, not configurable rules (Sprint: in progress)

Create a project with exactly:
- Project name.
- Project acronym / `project_code` (distinct from authority-generated activity codes).
- Required choice: `session` or `hours`.

The project may retain its existing lifecycle/status controls, but there is **no** per-project editor for hourly/session rates, currency, policy effective date, monetary rounding, caps, overnight policy or policy version. A coordinator cannot create/activate/supersede arbitrary monetary policies. Both policy definitions are fixed, reviewed application-level code/contracts, **not project data**. Selecting a family must not imply that a missing rule has an approved amount.

**Session:** governed by the approved `docs/policies/session_policy_contract_v1.0.md` plus `session_policy_addendum_v1.1_cross_project_authorization.md`; NK will re-upload the authoritative Word edge-case contract for cross-check before locking final implementation. Don't silently reinterpret that contract.  
**Hours:** awaits NK's explicit numeric rules, overtime/overnight definitions, rounding, role treatment and acceptance cases; no guessed financial authority.

Current new API/DB draft stores only the selected family in `projects.policy_family`. Historical project `payment_policies` rows remain preserved for audit and historical references; the previous mutating payment-policy endpoints are removed. Previously created projects have `NULL` family until a separate explicit human migration/reconciliation; never infer their family from old draft JSON or rate.

## Coordinator and cross-project scope (next sprint; not implemented by the policy change)

- **One coordinator / one application administrator** handles all projects; do not design separate end-user workspaces or independent project-specific chats.
- **Chats are global across all projects**. The coordinator can refer to one project, several projects or all projects in the same conversation. Explicit scope and provenance are retained for each action; do not cross-apply a role, policy or activity code from one project to another.
- **Planning workbooks may contain multiple project rows/sheets.**
- **One timesheet file may contain rows from one or many projects; multiple timesheet files/sources can be imported in one work cycle.**
- Source rows must resolve project identity/code deterministically and remain linked to their original file/sheet/row. Unknown project/ambiguous aliases must be flagged, not guessed.
- Remove multi-tenant account/workspace experiences only through a reviewed migration of routes, authentication, permission checks, data ownership and tests; retain secure authentication and audit even though there is one admin.

## Execution transparency (next sprint / acceptance requirements)

- While processing, show the coordinator **chronological, truthful, backend-owned progress**: detected intent, selected workflow/alias, scope/files, tool identity, step start/end, result/issue, blocks and human-review pause/resume.
- Never reveal model hidden chain-of-thought or pretend to expose internal model reasoning. The planned inspector displays **observable actions and provenance**, including which actual LangGraph node, approved policy definition/revision, retrieved graph node and actual MCP tool were executed/accessed. No phantom calls.
- Trace data must be bounded, redacted and scoped; no secrets, payroll identities or raw uploaded data in public event streams.
- Existing audit/workflow step receipts and chat activity trails are the foundation; a live MCP transport / full graph inspector must be independently verified, not inferred from specifications.

## Confirmed sprint sequence

1. Remove per-project policy configuration, select one fixed family; finalize hours contract through NK Q&A and check uploaded session Word before declaring payment logic locked.
2. Review global conversation scope, aliases, triggers, orchestration and safe multi-project/multi-source imports.
3. Generate realistic **synthetic Excel fixtures** (planning, multiple timesheet exports, staff directory and trusted report records as needed) with independent expected results and negative cases; execute automated and browser tests.
4. Build a small truthful workflow/knowledge/tool inspector after these behavior tests.

## Deployment note

Migration `0018` adds a nullable column to projects. The deployment contract and one-time readiness bridge for the currently active release are documented in [the deployment runbook](../../ops/deploy/README.md).
