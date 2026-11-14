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
