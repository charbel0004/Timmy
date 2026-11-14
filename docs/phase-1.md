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

## Conversation mapping repair (revision 0013)

Conversation control now persists pending processing, exact file scope, mapping
proposal/version, reviewer decisions and structural-validation status. Yes/yess,
Confirmed, and status questions use backend state before model inference. The
mapping editor supports explicit source-column choices. Revise column mappings
creates a new immutable decision version; invalid or stale confirmations return
specific blockers. Source counts are tied to saved scope, distinguishing owned
project evidence from conversation-local attachment lists. Existing audit helpers
are reused; CN's logging and explicit scheduler-scope settings are unchanged.

Mapping confirmation is not staff, planning, report or payment approval. After
structural checks the workflow remains held for those authorities. Only isolated
databases were migrated during implementation. See
[implementation and verification](architecture/conversation-workflow-repair.md)
for reproduction, tests, limits and deployment considerations.

## MVP readiness and unresolved payment inputs

| Phase | Repository status |
| --- | --- |
| 1. Intake and human review | Operational locally. Chat links to an exact, permission-checked structural snapshot. Planning and staff decisions are independently scoped and append-only. |
| 2. Authoritative activity and report sources | Planning has a typed provider boundary. Report synchronization preserves trusted provider evidence and freezes the first validated cutoff. No live planning or report MCP binding has been approved and configured. |
| 3. Calculation | The approved session rule is exactly USD 25.00 per three eligible credits. Zero to two credits carry forward without prorating or rounding. The trial pool uses the shared Decimal rule. Production credit issuance and hours-based compensation are blocked. |
| 4. Authorization and reconciliation | Exact batch approval, payment destination mapping, authoritative returns and settlement are blocked. There is no transfer execution. |
| 5. Dashboard and chat | Persisted project, intake, and review records are available. Financial dashboard totals and management reports require the missing financial stages. |
| 6. Evaluation | Synthetic fixture coverage exists. The authorized historical cases, expected results, and unseen judging cases have not been provided. |

Before enabling production calculations, obtain the signed hours policy covering
project and effective dates, hourly rate and currency, eligible time and
overnight handling, caps, and the rounding mode and stage (quantity, line,
or total). Also obtain the approved payment-return source and its scoped MCP
contract, including stable confirmation IDs, the reference that joins each
return to an approved obligation, amount and currency, settlement status, and
correction/reversal semantics. No chat statement, spreadsheet upload, or test
fixture supplies this authority. Cross-project session cost allocation and
policy-version compatibility still require explicit approval.

### Configurable project payment rules (revision 0014)

The existing policy table now holds immutable configuration versions. Existing
rows retain their IDs and are unconfigured drafts. Creating a project can save
an initial draft; existing projects can add drafts from Projects → Payment
policies. Activation requires scoped administrator access and explicit
confirmation, forbids overlapping active date ranges, and can explicitly
supersede a previous version without changing its configuration. Draft and
superseded versions can be archived. Audit events identify each transition.

The example calculator applies duration rounding, then caps, then monetary
rounding to a single example line. It does not evaluate multiple work intervals
or persisted claims. A configured per-session policy is separate from the
existing three-credit pooling contract. No project is silently assigned a rate
or switched between these rules. Chat can read active policy versions for a
selected project using the same scoped records.

Outstanding implementation includes eligibility and overlap checks for actual
claims, batch and approval persistence, isolated demo confirmation imports and
reconciliation, financial reporting, and registration with an approved MCP
server. Demo CSV support is requested but is not yet operational. The policy
example does not create a payment obligation.

The isolated workbook runner covers the synthetic per-session and hourly
demo policies, with an evaluation-only reconciliation projection before
human authorization. See [Workbook demonstration](architecture/demo-workbook.md).
