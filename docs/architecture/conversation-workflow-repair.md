# Conversation workflow repair — implementation and verification

2026-11-14 · NK assignment · review branch `codex/fix-conversation-mapping-workflow`.

## A. Executive summary

The repaired conversation persists the pending action, exact source scope, mapping proposal/version, human confirmation, and structural-validation outcome. `Analyze these files` → `Yes` → `Confirmed` now advances without model inference. Status questions read committed backend state and identify the synchronous run/result or precise blocker. No queue or background processing is invented.

A mapping editor lets the reviewer choose actual source columns for missing/unknown headers. Confirmed interpretations are immutable; `Revise column mappings` creates a new review version and reuses the prior interpretation only for its exact scope. Mapping confirmation does not verify staff, approve planning/reports or authorize payments.

Final verification: **102 backend tests passed**, frontend typecheck/production build passed, and the actual browser conversation and mapping editor passed. Original operational data was neither migrated nor changed. No production service was restarted or deployed.

## B. Baseline and root causes

The original working tree was clean on `work` at `6862872216297988ff1f21071381737690096fd4`. CN had subsequently pushed `adf7037f03b384222c00426dff550b0e62499d42` to main, requiring explicit scheduler scope. The dedicated repair branch starts from that latest main and retains all five files from CN's change. AGENTS.md was read. No uncommitted CN work was present. At final verification, remote main still matched `adf7037`.

| Finding | Code evidence and independent observation | Repair |
|---|---|---|
| Pending processing action was absent | Old `render_run` asked whether to process, but Conversation had no persisted pending decision. `choose_workflow` did not recognize Yes/yess/Confirmed. | Conversation.workflow_state binds pending action, scope, proposal and results; deterministic control handler runs before Qwen. |
| Unsupported progress prose could reach chat | Old `chat.respond` returned arbitrary `Proposal.answer` when tool was null; no run lookup was required. In a controlled adapter reproduction, Yes/status/where returned “active queue” while WorkflowRun count remained exactly one intake run. | Status/control messages bypass inference; unbound model prose claiming operational progress is rejected. No queue was added. |
| Mapping confirmation had no operation to invoke | No mapping-proposal table, confirm endpoint, decision receipt or transition existed. A model-selected document reader merely repeated “Confirm column mappings”. | Versioned proposals and strict confirmation endpoint; human authority, freshness, coverage and source indices checked; exact decision persisted before structural checks. |
| File scope could change across messages | Project-aware resolver could see old owned project uploads, while absent project context saw only this conversation. Frontend project selection was local component state. | Persist original selector separately from inferred project, exact file IDs/digest/parsed-evidence fingerprint and counts. Restored project selection cannot silently broaden conversation scope. |
| Profile display was timesheet-specific | `spreadsheet_profile` displayed a small timesheet allowlist; projects.csv could show no candidates even though project-reference parsing existed. Planning date bounds and directory status were omitted. | Deterministic category-aware proposals recognize claims, planning, directory and project references; display full relevant fields. Partial timesheets retain their category and expose missing fields. |
| Fresh chat UUIDs produced new intake receipts | Old runner deduplicated request key only; repeated Analyze with unchanged evidence could create another WorkflowRun. | Reuse the same intake evidence fingerprint without duplicating imported rows, mapping decisions or financial records. New file versions or deliberate mapping corrections remain distinct. |

**Historical limits:** The original affected operational database, Qwen trace and four approved CSVs were not supplied. Therefore the exact first Yes/run #2, the actual #3 numbering and the original 20-versus-four source selection cannot be reconstructed as historical facts. A run ID is a global database sequence, not an import/file counter. The code executes these procedures synchronously; no persistent queue/worker for the claimed ongoing cycle existed. The controlled model reproduction establishes that the old boundary permitted unsupported status claims; it is not a real-Qwen accuracy benchmark.

The count discrepancy was reproduced with synthetic versions of the four canonical layouts: 4 files/60 source rows in one conversation, versus 20 files/300 source rows with four older copies in the same owned project. Both sets remained available. This demonstrates a scope explanation, not file loss. New state explicitly records which scope was chosen.

## C. Changes by file

| File | Purpose |
|---|---|
| `backend/timmy/conversation_workflow.py` | Scoped conversation transitions, legacy intake recovery, confirmation intent, freshness checks, synchronous result/failure status and mapping revision. |
| `backend/timmy/column_mappings.py` | Non-authoritative header/category proposals; complete required-field/index validation; normalized validation views retaining original evidence and row numbers. |
| `backend/timmy/models.py` | Conversation.workflow_state JSON; MappingProposal with owner/project, fingerprint, version, exact sheet maps and reviewer/timestamps. |
| `backend/migrations/versions/0013_conversation_mapping.py` | Additive migration for those records. |
| `backend/timmy/chat_routes.py` | Workflow-state and mapping-confirmation endpoints; deterministic control dispatch; stable scope inheritance; protected history; mapping-editor confirmations persisted as chat turns. |
| `backend/timmy/chat.py` | Reject unbound model-generated processing/queue/completion/payment claims. |
| `backend/timmy/documents.py` | Explicit document selection stays exact; category-aware field display. |
| `backend/timmy/workflows.py` | Intake fingerprint reuse; confirmed normalized views and mapping references in validation fingerprints; synchronous completion metadata. |
| `backend/timmy/routes.py` | Health requires revision 0013. |
| `frontend/src/api.ts` | Typed workflow-state/confirmation API. |
| `frontend/src/assistant.tsx` | Restore persisted project/state; show actual scope, structural result and confirmed mapping labels; exact mapping editor and revision request; request-wait text does not imply a background job. |
| `backend/tests/test_conversation_workflow.py` | 15 chat/API regression scenarios, including synthetic four-file fixtures, errors, staleness, corrections, authority and zero financial side effects. |
| `backend/tests/test_workflows.py` | Existing cutoff assertion now passes through the required mapping confirmation first; cutoff exclusion assertion retained. |
| README, phase-1 and this report | Operator/deployment instructions and limitations. |

CN's scheduler/configuration and logging implementation were not changed. Instrumentation uses the existing `audit()` interface with actor/proposal/resource/outcome metadata. No competing logger or raw-cell telemetry was introduced.

## D. Workflow state and progression

Before: intake receipt text → unconstrained model inference for Yes/status → generic profile text → repeated confirmation request with no persisted decision.

After:

1. Upload preserves original bytes and parsed rows. Analyze verifies those bytes and saves `INTAKE_VERIFIED`, intake run ID, file IDs/counts and `pending=process`.
2. Yes/yess resolves that pending action and creates `MAPPING_UNDER_REVIEW` with a versioned proposal. Direct Process creates the same review gate.
3. Confirmed or Column mappings confirmed. proceed resolves the active proposal, checks current owner/permissions, exact file scope/digests/parsed evidence, version and required coverage, and persists reviewer/time/exact source-column choices.
4. Valid confirmation advances through mapping-confirmed, identity-verification-required and structural-validation-ready/running milestones. The synchronous operation returns a completed structural result or a recorded failure. Final stage remains `HUMAN_REVIEW_REQUIRED` while authority is unresolved.
5. Status returns stage, exact scope, run IDs, recorded timestamps, result and blockers. No processing run means “has not started”; failure means failed, not ongoing. Synchronous running state is not advertised as a durable background queue.
6. Repeated confirmation reuses the result for the same mapping/report evidence. New frozen report evidence causes a new structural result. Repeated intake with unchanged evidence reuses its receipt.
7. A deliberate Revise column mappings request creates a new proposal version; earlier decisions stay immutable. Unsupported or incomplete mappings identify the exact file/field. Stale input requires a fresh Process proposal rather than silently accepting a different scope.

For existing published conversations, only a real completed intake receipt can restore the pending processing offer. Model prose is never used as authority to resume a run. Confirmed interpretations are reused only within their exact reviewed actor/file scope; no fuzzy global identity/alias approval is introduced.

New API endpoints:

- `GET /api/chat/conversations/{id}/workflow`
- `POST /api/chat/conversations/{id}/mappings/{proposal_id}/confirm` with proposal version, fingerprint and optional explicit per-sheet column selections.

GET conversation also includes protected workflow state. Permission loss redacts protected result text and state rather than leaking source metadata.

## E. Execution evidence

All databases/uploads/accounts below are disposable synthetic test state. No production migration, real entitlement, payment instruction or settlement was created.

| Check | Command or interaction | Result |
|---|---|---|
| Baseline acceptance regressions | pytest against the first six new chat tests, before repair | 6 failed; missing state endpoint/confirmation path reproduced. |
| Baseline unsupported-status reproduction | Controlled Ollama adapter at actual chat API; analyze → Yes → Is it done → where → confirmations | 1 diagnostic test passed: unsupported queue text with unchanged run count, then repeated profile prompt. |
| Final complete backend suite | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests -p no:cacheprovider --basetemp=/tmp/timmy-conversation-final --junitxml=/tmp/timmy-conversation-final.xml` | **102 passed**, zero failed/skipped; one existing Starlette HTTPX deprecation warning. |
| Schema/migration | Repository fixture upgrades each fresh SQLite DB and calls Alembic check | Passed throughout final suite. |
| Frontend | `npm run build --prefix frontend` | Typecheck/build passed; dependency use-client directives ignored by Vite. |
| Browser | Headless Chromium/CDP, real Vite frontend and FastAPI; upload four files; Analyze → Yes → status → confirmation → status → repeat → refresh | Passed, including 4 files/60 source rows, three activity structures and persisted state/labels. |
| Browser editor | New conversation, Process, confirm through column editor, reload and reopen that exact conversation | Passed; result persisted into chat and contains 12/12 role-slot results. |
| Scope/idempotency | Project-wide 20/300 versus local 4/60; refresh/inferred-project stability; repeated Analyze/confirm; new revision | Passed; stable chosen scope and expected new-versus-reused records. |
| Negative cases | Missing field, explicit wrong columns, stale version/scope, foreign/revoked account, missing CSRF, injected cells, failed validator, ungrounded model text | Passed with specific blockers/rejection and no financial rows. |

The final browser flow verified text and editor paths. Browser harness attempts initially needed corrected reload synchronization and selection of the same conversation rather than assuming UUID ordering. Those harness failures are not reported as application passes; the final complete run passed. The later revision button has backend API regression coverage; its separate click was not part of the recorded browser flow.

Local evidence: `/workspace/diagnostics/conversation-workflow-repair/` contains final JUnit XML/logs, baseline reproduction, browser result JSON, script and screenshot. Synthetic runtime is `/tmp/timmy-conversation-browser`; its scheduler was disabled. The API used port 18100, frontend 15180, and an isolated browser profile. Test services were stopped after verification. Ordinary conversational model generation was not evaluated against a running Qwen model; the repaired control path requires no model.

## F. Security and business controls

Confirmation requires session ownership, CSRF/origin, workspace-management authority and current project timesheet access. Exact scope and original bytes are rechecked; candidate mappings cannot omit proposal sheets, invent out-of-range columns or duplicate field indices. Existing confirmations cannot be rewritten. Mapping choices create normalized views only; original cells/bytes/row lineage remain unchanged. Filenames/cells never choose a workflow or authorize a mapping.

The actual deterministic coverage service still enforces S1–S6, required distinct staff roles, matching dates and approved date patterns. Structural results remain explicitly nonfinancial, with staff/planning/report authority blockers. Frozen report cutoffs still reach validation. Tests confirmed that repeated intake, mapping decisions and validation created zero trial credits/groups/payment batches. Financial policies, one-off grouping authority, exact-batch approvals and payment/settlement state were not weakened or implemented by this repair.

## G. Remaining blockers and uncertainty

- Staff identity and planning approvals, authoritative external-report provider integration and production eligibility transitions remain separately required. A column named staff_id is not verified identity.
- Production payment preparation/export and return-payment reconciliation remain blocked adapters; this repair does not supply them.
- Only the known canonical/header-alias layouts are proposed deterministically. Other layouts require explicit reviewer column choices; no model invents them.
- The historical affected user's files/database were unavailable; no claim is made about their exact run numbering, elapsed time or missing-file history.
- CN's ongoing private/unpushed logging work cannot be inspected; visible main did not change during final review. Existing audit interfaces were retained.

## H. Review instructions

Review `codex/fix-conversation-mapping-workflow` against `main` (`adf7037`). Focus on the persisted pending-decision handler, immutable mapping confirmation and fresh scope checks, followed by API tests and browser evidence. The branch is intended for NK/CN approval; do not merge or deploy automatically. Commit SHA and remote branch URL are supplied in the delivery message.

## I. Deployment considerations

Migration **0013** is required before starting this branch. It is additive and was applied only to isolated databases during this task. An authorized deployment should back up its operational database/documents, apply `alembic -c backend/alembic.ini upgrade head`, build the frontend and restart the API/frontend using the normal process. No new credentials, dependencies or queue service are required. CN's explicit scheduler identity/project configuration remains unchanged. No production deployment, merge or environment publication was performed.
