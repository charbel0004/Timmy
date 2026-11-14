# Agent Timmy

- Keep local-first defaults and enforce permissions and project scope in the API.
- Keep original import values alongside extraction candidates. Treat Ollama output as untrusted and require review for missing or uncertain fields.
- Keep financial rules deterministic, Decimal-based, and independent of the AI adapter. Require explicit human approval and preserve immutable calculation snapshots when the workflow is implemented.
- Document unresolved domain rules in docs/phase-1.md. Add Alembic revisions for schema changes.
- Run the backend test suite and frontend build using the README commands.
