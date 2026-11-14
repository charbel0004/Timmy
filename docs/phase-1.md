# Phase 1 architecture

FastAPI routes delegate authorization and session handling to auth, project queries to repositories, and audit inserts to audit. Alembic owns schema creation. SQLite enables foreign keys on every application and migration connection. The browser holds an opaque HttpOnly session cookie. The database stores its hash, expiration, and a session-bound CSRF token. Login checks Origin, while logout checks Origin and the CSRF token. The API allows credentialed CORS for a single configured origin. Accounts are provisioned locally with Argon2id password hashing.

| Capability | Admin | Reviewer |
| --- | --- | --- |
| Read projects | Assigned only | Assigned only |
| Read app settings | Yes | Denied |

Unknown roles receive no permissions. Membership is explicit even for admins. These are provisional foundation roles. The React shell reads authenticated session capabilities and shows live dashboard and settings data. Imports, Timesheets, Discrepancies, and Payment Batches display their phase status.

Ollama proposes structured extraction for a single row. The adapter retains the original row and the model candidate. Use the result's server-derived review flag and field issue codes before consuming any candidate. The candidate-only flag on the extraction schema is a compatibility accessor and lacks row provenance. The adapter raises a typed error on transport, response, or schema failures.

Automatic verification uses a provisional Arabic/English header allowlist, requires volunteer, activity, date, and at least one verified quantity (hours or sessions), and flags duplicate recognized columns. Dates use Gregorian ISO or unambiguous numeric day/month order. Quantities use plain nonnegative decimals for hours and integers for sessions. Other column mappings, date conventions, and units require a confirmed import template. Extraction verification supplies no payment policy, calculation, or approval authority.

## Pending decisions

- Define roster identity, assignment, activity relationships, project years, Arabic/English date and number conventions, and import templates.
- Define upload limits and supported workbook features, parser sandboxing requirements, source retention, duplicate detection, and safe export format.
- Set discrepancy codes and materiality, review resolution rules, and project access and approval permissions.
- Set project-specific rates, currency, session/hour calculations, caps, rounding, and policy effective dates.
- Specify immutable calculation snapshots, approval invalidation, payment line provenance, and export eligibility. Use Python Decimal and keep approval human-only. Execute payments externally.
- Set audit retention, backup/restore procedures, and requirements for any deployment beyond loopback.

Domain tables are migration foundations. Expand them through revisions when these decisions are made.

## Stored workflows and remaining adapters

`workflow_knowledge.json` now defines brief-request procedures and their ordered
steps. Chat and the Monday runner share `workflows.run_workflow`, scoped durable
receipts, original-file integrity checks, and the same frozen report cutoffs.
Migration 0012 adds workflow runs and protected chat request context. No existing
database was migrated during implementation; apply the revision before starting
the updated app. Shortcuts do not require a running model; less explicit requests
can use a strictly typed model proposal. Unclear intent produces action choices.

The weekly schedule is Monday 04:00 Asia/Beirut. The app must be running; a restart
later on Monday catches up once. It does not backfill a missed Monday on Tuesday.
The sole active account and all its permitted projects are used by default. With
multiple active accounts an explicit actor is required. Rights are rechecked for
every project; no administrator bypass or extra membership is inferred. Disable
with TIMMY_WEEKLY_ENABLED=false. Multiple workers are deduplicated with SQLite
transactions and a unique per-account/project/ISO-week run key. Review-state runs
are recorded once; use a new explicit run request after correcting evidence.

This is not completed production financial orchestration. Approved planning/
staff-to-eligibility transitions, policy-resolution adapters, production credits,
exact-batch approval and payment-request file export are still missing. The runner
records each missing capability as a blocker, including the unperformed steps.
A structural pass cannot produce credits or a payment file. Returned-payment
reconciliation, mapping and archival need a trusted source and reviewed backend
adapters; there is no automatic source watcher/provider registered yet. A brief
reconciliation request starts the stored return workflow and records those
blockers. Original uploads remain preserved. No payment-request email, transfer
or external delivery is implemented or authorized; the coordinator sends files
manually once a valid exporter exists. No automatic invalidation or fuzzy staff
matching is introduced by these instructions.
