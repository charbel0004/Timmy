# Stored workflow triggers

Updated 2026-11-15. Business wording confirmed by NK in the working session.
The live knowledge base is `backend/timmy/workflow_knowledge.json`; backend code
owns capabilities and authorization. These instructions do not change policy.

| Brief request | Stored workflow |
|---|---|
| Analyze / import / حلل | Verify stored intake evidence, then offer processing |
| Process / validate / عالج | Check planning, reports, select planned/reported timesheets, validate and review discrepancies |
| Run weekly | Run the complete ordered Monday procedure |
| Reconcile / payment report / طابق | Receive trusted return, reconcile, map, archive evidence, raise issues |
| Prepare a payment request | Prepare and export an approved request file for manual sending |
| Show flags | Read scoped discrepancies; do not resolve |
| Resolve discrepancies | Apply only explicitly policy-permitted resolutions; otherwise recommend human review |

An explicit request names the goal, not every step. The model selects a stored
workflow ID; it cannot write a new procedure or manufacture an adapter. Ambiguous
“process payments” offers preparation versus reconciliation choices. Negation,
quoted instructions and conflicting goals do not shortcut into writes. Shortcut
vocabulary is conservative; non-matching ordinary conversation stays on the
existing conversational path. Available model schemas bound the workflow IDs.

Weekly order: check planning → check reports → select planned/reported timesheets
→ validate/flag/invalidate via deterministic authorized services → resolve explicit
policy cases or raise recommended human resolutions → prepare payment request →
export approved request file. Every step has a status; blocked steps are not
reported as done. The shared-chat Excel path now connects confirmed mappings,
source-code contracts, planning registration, declared official register evidence,
human planning/staff reviews, deterministic session/hour findings and immutable
payment snapshots. Exact destination/allocation verification and exact-snapshot
human approval precede file-only export. A combined processing/payment request
selects the complete weekly goal. Every step's prerequisites, outcome and next
action are exposed at `/api/workflows/definitions`.

See [the Excel workflow contract](../excel-reporting-workflow.md) for the source
trust boundary and supported execution path. Legacy project/scheduled runners
retain their earlier adapters and explicit blockers. The catalog describes the
shared-chat path; it does not upgrade a legacy schedule's financial authority.
Finance-return reconciliation remains gated by an approved return-source contract.

Return order: preserve trusted return → reconcile exact batch → map verified
references → archive evidence → raise unmatched/partial/pending/duplicate items.
Pending is not settled. Archiving never means deleting the original upload.
Receiving a payment file alone cannot grant report authority. The eventual
provider must invoke the same runner after trusted intake; no source watcher is
currently configured. Coordinator manually sends exported request files.

Monday at 04:00 uses Asia/Beirut and its DST rules. The sole active account is the
main account; automation covers only its existing project permissions. Multiple
active accounts require explicit configuration. The same ISO week/project/actor
has one automatic receipt. Changed evidence requires a deliberate new run, not a
silent replay. Rights and original-file integrity are refreshed before execution.

Receipts are saved with actor, project, source IDs, knowledge version, full-input
fingerprint, timestamp, step statuses and review recommendations. History checks
current document access. Request replay rejects changed context. Full procedure
knowledge contributes to the run fingerprint; editing instructions cannot silently
reuse a run keyed to an older procedure. Blockers and review states are retained.

The six proposed report templates remain in the separate workflow-v2 draft
package; a production report renderer and approved template catalog have not
been activated. No report-generation or real-model accuracy claim follows from
these routing tests.
