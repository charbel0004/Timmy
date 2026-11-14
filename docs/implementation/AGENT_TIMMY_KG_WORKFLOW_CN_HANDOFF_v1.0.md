# Agent Timmy — CN Implementation Handoff: KG-Backed Guarded Agent

**Date:** November 14, 2026 | **Repository:** `charbel0004/Timmy` | **Owners:** NK (approved business semantics), CN (integration / database), Codex (separate scoped implementation or independent QA only upon NK authorization) | **Status:** Implementation request/specification; no GitHub modifications carried out by Lil Robert.

## Read before coding

1. `docs/implementation/AGENT_TIMMY_KG_WORKFLOW_IMPLEMENTATION_RUNBOOK_v1.0.md` — exact procedure, state/SQL/API contracts and safety gates.
2. `docs/implementation/AGENT_TIMMY_KG_WORKFLOW_ACCEPTANCE_MATRIX_v1.0.md` — 76 case-level acceptance tests and four staged journeys (use actual current count in matrix; labels unchanged).
3. `docs/architecture/Agent_Timmy_KG_Schema_Authority_v1.0.md` and associated Obsidian draft vault and SQL references — **draft technical design**; does not authorize policy activation or direct SQL migration.
4. The current repository's `AGENTS.md`, policy contracts, migrations, workflow knowledge and receipts, plus the Nov 14 progress report for historical baseline. Do not assume the report's SHA is still HEAD.

## Critical product change

**Activity codes must come from the authoritative planning spreadsheet.** The app may NOT generate `P-A-0001`, `ProjectCode-A-0000` or any other fallback. Format comes from approved source configuration, not a global hardcoded pattern. Code unique across projects; each code belongs to one project. Existing generated legacy codes must be inventoried and reconciled by humans, not automatically rewritten.

## Work assignment and PR breakdown

| PR | Focus | Concrete change | Minimum acceptance |
|---|---|---|---|
| PR-0 | Baseline/conflict | Map existing handler/models/tests, inspect current branch/migrations; locate and block codeless-code generator while protecting historical rows | AC-01/02/03, existing suite |
| PR-1 | Approved Obsidian build | Add vault linter/compiler, typed edges, release manifest/hashes, alias checks, safe static tool binding allowlist | KG-01…12 |
| PR-2 | SQLite projection | Add additive approved KG snapshot/links and bind to existing workflow receipts; pin versions; prove populated-copy upgrade | DB-01…12 |
| PR-3 | Backend graph service | Implement read-only 1-hop scoped graph neighbors and approved canonical aliases; enforce RBAC and bounds | KG-13…20 |
| PR-4 | Guarded workflow | Extend existing synchronous workflow runner with step guards, exactly recorded access, validated transitions, paused review/resume and safe retry | WF-01…16; J1/J2 |
| PR-5 | Claim proof | Record actual context supplied/used, rule-check outcomes, evidence and claims with verification status | TR-01…10 |
| PR-6 | Inspector UI | Read-only run timeline, selected step's immediate graph, source/rule evidence and reviewer action UI | UI-01…08; J3 |
| PR-7 (separate authorization) | Authority/finance adapters | Approved planning/staff/report to accepted state, production credits, one-off group approvals, allocation, exact export and reconciliation | AC-05…10; J4; human finance signoff |

**Do not merge PR-7 into this knowledge-graph tranche without explicit NK authority.** The current report states that real financial services are incomplete; the graph must not pretend otherwise. Preserve CN's current logging; extend it, do not fork a rival audit subsystem.

## Backend procedure to use in each actual step

1. Authenticate actor; authorize exact action/project/evidence; audit denial.
2. Resolve intent through approved canonical alias or request clarification.
3. Find current persisted run or create a new idempotent run with pinned KG/policy/binding versions and source fingerprint.
4. For current ordered step: load only step's one-hop direct rules/sources from pinned approved snapshot; check guard, tool allowlist and permissions.
5. If missing human review: persist exact proposed decision/evidence version, set WAITING_HUMAN, return actionable request, **stop**.
6. If external authority missing: set BLOCKED_AUTHORITY with stable issue code, **stop**.
7. Else run backend handler and independent result/postcondition validator; log actual accesses, tool execution, rule checks, source hashes, output and state transactionally.
8. If transient read-only error: bounded idempotent retry; if uncertain sensitive side effect: stop + reconciliation issue.
9. On human decision: validate CSRF/RBAC/scope/version/fingerprint; persist decision; revalidate and resume affected step; never use generic chat `Yes` as payment approval.
10. Respond using actual receipts; every user-facing `verified` claim links to source/rule/tool/check, and a missing step/authority is never described as completed.

## API contracts (recommended; map to existing routing conventions)

- `GET /api/knowledge/releases/active` (restricted): pinned release metadata.
- `GET /api/knowledge/nodes/{node_id}/neighbors?depth=1` (explicit project/RBAC; fixed first hop).
- `GET /api/workflow-runs/{run_id}/trace` (permission-filtered step, rule-check and evidence summary).
- `GET /api/workflow-runs/{run_id}/steps/{receipt_id}` (access and verification detail).
- `GET /api/workflow-runs/{run_id}/review-requests` (server-authorized choices).
- `POST /api/workflow-runs/{run_id}/reviews/{review_id}/decisions` (idempotency, optimistic version, reviewer action).

Graph/trace API responses must never include raw staff PII/payment destinations for unauthorized viewers. AI does not have mutation endpoints for policies/releases/finance/audit.

## QA commands (only on isolated development snapshot; verify repo instructions)

```bash
git rev-parse HEAD && git status --short
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests -p no:cacheprovider --basetemp=/tmp/timmy-kg-validation
npm run build --prefix frontend
```

Please create targeted `backend/tests/test_kg_compiler.py`, `test_kg_authority.py`, `test_kg_workflow.py`, `test_kg_trace.py` or follow actual test naming. Run existing suite before and after each PR. Capture exact SHA, fixture digests, trace IDs and PASS/FAIL outcomes; do not equate mocked-model pass with actual Qwen performance. Test migrations only on disposable populated-copy DB with documented backup/recovery procedures.

## Definition of Done for initial KG / workflow tranche

- Approved graph release compiles and activates only through controlled review; unapproved notes and bindings cannot execute.
- Existing run/receipt engine processes a multi-step policy-validating task in order with persistent statuses and verified rule/source accesses.
- A human review pauses at the exact step, creates a scoped review ID, authorizes one specific resolution, then resumes with fresh evidence; duplicates/stale decisions do not bypass rules.
- Missing authoritative source blocks downstream entitlement, with transparent status and no hallucinated work or queue.
- Every consequential answer links to real evidence/step checks and is shown in a read-only permission-filtered inspector; old runs use pinned old releases.
- Activity codes are exclusively planning-supplied, format-configured and globally unique/project-bound; legacy generated records are preserved pending review.
- Tests are actually executed and reported. No real data loss, unauthorized financial effects, or silent main merge/deploy.

**Return to NK:** (1) current repo/branch/SHA; (2) component map; (3) PR/change list with changed files; (4) migration/backup strategy; (5) executed tests and observed results; (6) four demonstration traces; (7) blocked authority/financial adapters; (8) explicit residual risks; (9) review links. Obtain NK approval for actual activation/release decisions.

## Classification and upload

- **This document:** human/engineer implementation handoff; **AI can read** relevant excerpts, **AI cannot mutate authoritative policy or run approval**.
- **The runbook/test matrix:** read-only implementation/test references, change only through code review and NK approval.
- **Vault notes:** Git reviewable source; only approved compiled release is exposed read-only at runtime.
- **Operational evidence and traces:** SQLite/private source storage, access-controlled; not committed to Git.
- **Deployment:** no automatic repo push, migration or restart authorized by this documentation alone.

**Proposed documentation commit:** `docs(implementation): specify guarded KG workflow and acceptance tests`.
