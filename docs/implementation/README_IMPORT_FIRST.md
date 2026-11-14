# Agent Timmy — Implementation procedures bundle

This package is **not executable application code**. It is an implementation runbook, complete QA acceptance matrix, and developer handoff based on the Nov 14 progress report and previously designed KG authority specification. It does not include or mutate the GitHub repository.

Upload the three Markdown files to these repository paths **after NK approves the documentation**:

1. `docs/implementation/AGENT_TIMMY_KG_WORKFLOW_IMPLEMENTATION_RUNBOOK_v1.0.md`
2. `docs/implementation/AGENT_TIMMY_KG_WORKFLOW_ACCEPTANCE_MATRIX_v1.0.md`
3. `docs/implementation/AGENT_TIMMY_KG_WORKFLOW_CN_HANDOFF_v1.0.md`

Do NOT upload `README_IMPORT.md` unless useful. Do NOT overwrite existing code when extracting. Do NOT apply the earlier illustrative SQL against an operational database.

Suggested documentation commit: `docs(implementation): specify guarded KG workflow and acceptance tests`.

Implementation occurs through narrow reviewed PRs using a current repository snapshot. Real existing modules and migrations must be inspected before implementing suggested file names or API shapes.

`contracts/` additionally contains four **proposed JSON Schema 2020-12** boundary contracts: step receipts, review requests, claim provenance and fixed-depth graph query. They are schema drafts for backend integration, not proof of application implementation or substitutes for database/permission checks. Enforce cross-record business checks (for example: VERIFIED requires rule+source, allocation totals $25) in backend transactions; JSON Schema alone is insufficient.

`contracts/` contains four **proposed JSON Schema 2020-12** boundary contracts: step receipts, review requests, claim provenance and fixed-depth graph query. They are schema drafts for backend integration, not evidence of application implementation or substitutes for database/permission checks. Enforce cross-record business checks (for example: VERIFIED requires rule+source, allocation totals $25) in backend transactions; JSON Schema alone is insufficient.
