# Proposed compiler contract v0.1

This implemented internal note/release contract is derived from the runbook. It
does not replace the four supplied wire schemas or approve operational knowledge.
An approved vault, original KG authority/schema document, trusted reviewer roster
and source-format contract remain unavailable. Tests use synthetic approvals only.

## Source and approval boundary

Input: real Git root, vault subdirectory, external operator approval JSON. Approval
pins the full Git commit, SHA256 of the canonical path-to-source-hash map, exact
approved node IDs, release ID, reviewer IDs/time, privacy review, policy version
and static binding revision. Every vault file must match that commit byte for
byte. Extra/missing files, symlinks, traversal, executable files and unsupported
names fail closed. Files outside the vault need not be clean.

Reviewer strings and hashes do not authenticate a human or prove Git review. The
operator must obtain approval and the expected manifest pin through a trusted
review/deployment channel. There is no model/API approval, allowlist-edit or
activation endpoint. The application does not consume artifacts yet. NK's content
signoff and CN's binding signoff remain prerequisites to actual activation.

## Atomic notes

One YAML mapping and bounded UTF-8 Markdown body per note. Type folders: facts,
rules, steps, procedures, actions, concepts, sources. Root README.md is ignored as
a node but is still Git/hash pinned. Names use ASCII letters/digits/underscores/
hyphens and .md extension. Required metadata: id, type, version, status,
classification, source_ref, approved_by, approved_at, aliases, title, description.
ID prefixes: FACT/RULE/STEP/PROC/ACTION/CONCEPT/SOURCE. Unknown fields are rejected.
Classifications: public/internal/restricted. Approved timestamps need a timezone
and release-review coverage. contains_personal_data can only be false. Draft,
in_review and deprecated notes are validated but excluded; approved links to them
fail. Frontmatter approval alone does not authorize a release.

Links explicitly specify relation, target (ID or [[ID]]), and position only for
ordered steps. ACTION invokes exactly one PROCEDURE. PROCEDURE has unique,
contiguous ordered STEP links. STEP needs direct rule (uses_rule/validated_by) and
uses_source links; RULE needs a uses_source link. STEP/RULE require backend_key;
other types cannot have it. compiler.RELATIONS enumerates typed edge pairs;
duplicates, dangling targets and execution dependency cycles fail.

SafeLoader additionally rejects duplicate keys, anchors, aliases and tags. Only
metadata defines edges; Markdown text/wikilinks are inert. Limits: 512 files/
directories, 32 KiB/file, 16 KiB frontmatter, 2 MiB vault, 4,096 edges, 64 links/node,
16 aliases/node. Privacy patterns reject common credential/address/staff/payment
payloads; this is a linter, not comprehensive PII detection. Privacy and atomicity
still need human review. Invalid notes are errors, never silently auto-approved.

## Aliases and static bindings

Only ACTION/CONCEPT may declare aliases with text, locale and scope. Versioned
normalization: NFKC, casefold, Arabic diacritic/tatweel removal, whitespace
normalization. Cross-target collisions in the same locale/scope abort. S1 does not
dispatch chat intents, interpret negation, map staff names or grant permissions.

Static inventory: existing session.coverage and source.integrity evaluators.
Bindings record contract version, registry revision and direct handler source
SHA256. They are definitions, not invocation receipts or proof of execution.
Dependency changes require registry revision/code review; function-source digests
are not complete environment fingerprints. No finance/export/approval handler is
registered. Note text cannot supply Python imports, SQL, shell or URL execution.

## Artifacts, import and reads

Canonical sorted UTF-8 JSON includes full metadata/body, source and payload hashes,
typed edges, aliases, bindings and approval. Manifest SHA256 covers all fields
except its own digest. SQLite stores the complete payload and same-release
composite FKs. Import revalidates approvals/projections/current bindings, writes
one transaction, verifies FK/integrity/full payload equality, fsyncs and atomically
renames the staged directory. An existing release ID cannot be overwritten.

GraphRelease requires a trusted expected manifest hash and opens SQLite using
mode=ro&immutable=1, foreign_keys/query_only enabled and a restrictive authorizer.
It verifies the full projection and never reads live vault text. Old artifacts
remain readable after pointer changes. An OS owner can change permissions;
hash/projection checks detect edits on next open. Obtain pins from a trusted
channel, not from an untrusted manifest packaged with an arbitrary database.

The private reader allows exactly one outgoing hop, 1–20 neighbors, at most
12,288 response bytes; overflow fails rather than dropping mandatory links.
Actor/project RBAC, classification filtering, access auditing and query receipts
are Sprint 2 work. Never expose this raw local reader as an unauthenticated API
or model tool.

An operator-only library helper tests atomic active-pointer replacement in
disposable stores. Invalid candidates preserve the prior pointer. The CLI only
compiles/publishes and returns COMPILED_NOT_ACTIVATED. No app setting, scheduler,
workflow or policy consumes the pointer in S1. No competing runner is created.

```bash
PYTHONPATH=backend .venv/bin/python -m timmy.knowledge \
  --git-root /path/to/reviewed/repository \
  --vault docs/knowledge-vault \
  --approval /path/to/trusted-release-approval.json \
  --output /path/to/separate/knowledge-artifacts
```

Output must be outside the vault. The placeholder README cannot produce a valid
release. Import does not alter the operational database or run Alembic migrations.
S2 adds authorized retrieval; S3 pins existing WorkflowRun/receipts through additive
migrations; S4 extends the existing runner and decisions with guarded review/resume.
Claims verification and the evidence-backed Inspector follow. None is claimed
complete by S1, and the full 76-case matrix has not passed.
